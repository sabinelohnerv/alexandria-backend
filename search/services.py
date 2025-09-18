import os
import time
import inspect
from typing import List, Tuple, Dict, Any, Optional

import numpy as np
from django.conf import settings
from django.db import transaction
from pgvector.django import CosineDistance
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank

from documents.models import Chunk, Document
from .models import ChatSession, ChatMessage, SearchHit


# =========================
# Helpers / Settings
# =========================
def _get_setting(name: str, default):
    return getattr(settings, name, default)


# =========================
# Embedder (consulta)
# =========================
_EMBED_MODEL = None

def _get_embedder():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from sentence_transformers import SentenceTransformer
        name = os.getenv("EMBEDDINGS_MODEL", _get_setting("EMBEDDINGS_MODEL", "BAAI/bge-m3"))
        _EMBED_MODEL = SentenceTransformer(name)
    return _EMBED_MODEL

def _encode_query(text: str) -> np.ndarray:
    model = _get_embedder()
    kwargs = dict(normalize_embeddings=True, convert_to_numpy=True, batch_size=1)
    try:
        if "prompt_name" in inspect.signature(model.encode).parameters and getattr(model, "prompts", None):
            if "query" in model.prompts:
                kwargs["prompt_name"] = "query"
    except (ValueError, TypeError):
        pass
    return model.encode([text], **kwargs)[0]


# =========================
# Búsqueda vectorial
# =========================
def vector_search(query_vec: np.ndarray, top_k: Optional[int] = None) -> List[Tuple[Chunk, float]]:
    """
    Devuelve [(chunk, score_vector)] donde score_vector es similitud coseno ~[0..1].
    """
    if top_k is None:
        top_k = _get_setting("SEARCH_TOP_K", 50)

    qs = (
        Chunk.objects
             .filter(document__state="INDEXED", embedding__isnull=False)
             .annotate(distance=CosineDistance("embedding", query_vec.tolist()))
             .select_related("document")
             .order_by("distance")[:top_k]
    )

    out: List[Tuple[Chunk, float]] = []
    for ch in qs:
        # CosineDistance en pgvector: 0 (idéntico) .. 2 (opuestos)
        sim = 1.0 - float(ch.distance) / 2.0
        out.append((ch, sim))
    return out


# =========================
# Búsqueda léxica (Postgres)
# =========================
def lexical_search(query: str, top_k: Optional[int] = None) -> List[Tuple[Chunk, float]]:
    """
    Devuelve [(chunk, score_lexical)] ordenado desc, donde score_lexical = ts_rank_cd.
    """
    if top_k is None:
        top_k = _get_setting("SEARCH_TOP_K", 50)

    sv = SearchVector("section", "text", config="spanish")
    sq = SearchQuery(query, config="spanish")
    qs = (
        Chunk.objects
             .filter(document__state="INDEXED", embedding__isnull=False)
             .annotate(rank=SearchRank(sv, sq, cover_density=True))
             .filter(rank__gt=0)
             .select_related("document")
             .order_by("-rank")[:top_k]
    )

    out: List[Tuple[Chunk, float]] = []
    for ch in qs:
        out.append((ch, float(ch.rank)))
    return out


def _minmax(values: List[float]) -> Tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    return (min(values), max(values))

def _norm(v: float, vmin: float, vmax: float) -> float:
    if vmax <= vmin:
        return 0.0
    return (v - vmin) / (vmax - vmin)


# =========================
# Híbrido (lexical + vector)
# =========================
def hybrid_search(query: str, top_k: Optional[int] = None, alpha: Optional[float] = None) -> List[Tuple[Chunk, float, Dict[str, float]]]:
    """
    Devuelve [(chunk, score_hibrido, {"vec": sim, "lex": rank})] ordenado desc.
    score_hibrido = alpha * norm(vec) + (1-alpha) * norm(lex)
    """
    if top_k is None:
        top_k = _get_setting("SEARCH_TOP_K", 50)
    if alpha is None:
        alpha = _get_setting("HYBRID_ALPHA", 0.6)

    # 1) vectorial
    qvec = _encode_query(query)
    vec_pairs = vector_search(qvec, top_k=top_k)  # [(chunk, sim)]
    # 2) léxico
    lex_pairs = lexical_search(query, top_k=top_k)  # [(chunk, rank)]

    # 3) merge por chunk.id
    by_id: Dict[int, Dict[str, Any]] = {}
    for ch, sim in vec_pairs:
        by_id[ch.id] = {"chunk": ch, "vec": float(sim)}
    for ch, rank in lex_pairs:
        d = by_id.setdefault(ch.id, {"chunk": ch})
        d["lex"] = float(rank)

    # 4) normalización min-max independiente por canal
    vec_vals = [d.get("vec", 0.0) for d in by_id.values()]
    lex_vals = [d.get("lex", 0.0) for d in by_id.values()]
    vmin, vmax = _minmax(vec_vals)
    lmin, lmax = _minmax(lex_vals)

    # 5) puntaje híbrido
    scored: List[Tuple[Chunk, float, Dict[str, float]]] = []
    for d in by_id.values():
        v = _norm(d.get("vec", 0.0), vmin, vmax)
        l = _norm(d.get("lex", 0.0), lmin, lmax)
        s = alpha * v + (1 - alpha) * l
        scored.append((d["chunk"], s, {"vec": d.get("vec", 0.0), "lex": d.get("lex", 0.0)}))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


# =========================
# MMR (diversidad)
# =========================
def mmr_select(candidates: List[Tuple[Chunk, float, Dict[str, float]]],
               qvec: np.ndarray,
               k: int = 10,
               lambda_: float = 0.7) -> List[Tuple[Chunk, float, Dict[str, float]]]:
    """
    MMR clásico: balancea relevancia al query y disimilitud entre seleccionados.
    candidates: [(chunk, score_base, extra)]
    """
    if not candidates:
        return []
    selected: List[int] = []
    pool = list(range(len(candidates)))
    embs = [np.array(c[0].embedding, dtype=np.float32) for c in candidates]

    def cos(a, b):
        da = np.linalg.norm(a) + 1e-9
        db = np.linalg.norm(b) + 1e-9
        return float(np.dot(a, b) / (da * db))

    scores = []
    for _ in range(min(k, len(pool))):
        best_i, best_val = None, -1e9
        for i in pool:
            rel = cos(embs[i], qvec)  # relevancia al query
            div = 0.0
            if selected:
                div = max(cos(embs[i], embs[j]) for j in selected)  # similitud con los ya elegidos
            mmr = lambda_ * rel - (1 - lambda_) * div
            if mmr > best_val:
                best_val = mmr
                best_i = i
        selected.append(best_i)  # type: ignore[arg-type]
        pool.remove(best_i)      # type: ignore[arg-type]
        scores.append(best_val)
    return [candidates[i] for i in selected]


# =========================
# Reranker (cross-encoder)
# =========================
_RERANKER = None
_RERANKER_READY = None  # tri-state: None (unknown), True, False

def _get_reranker():
    """
    Carga perezosa del cross-encoder. Devuelve None si falla.
    """
    global _RERANKER, _RERANKER_READY
    if _RERANKER_READY is True:
        return _RERANKER
    if _RERANKER_READY is False:
        return None

    try:
        os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from sentence_transformers import CrossEncoder
        model_name = _get_setting("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
        _RERANKER = CrossEncoder(model_name, trust_remote_code=True)
        _RERANKER_READY = True
        return _RERANKER
    except Exception:
        _RERANKER = None
        _RERANKER_READY = False
        return None

def rerank_hits(query: str,
                candidates: List[Tuple[Chunk, float, Dict[str, float]]],
                top_n: Optional[int] = None) -> List[Tuple[Chunk, float, Dict[str, float], Optional[float]]]:
    """
    Reordena candidatos con CrossEncoder.
    Entrada: [(chunk, score_hibrido, {"vec","lex"})]
    Salida:  [(chunk, score_hibrido, {"vec","lex"}, score_rerank)] ordenado desc por rerank si disponible.
    """
    if top_n is None:
        top_n = _get_setting("RERANK_TOP_N", 20)

    if not _get_setting("ENABLE_RERANK", True) or not candidates:
        # sin rerank, conserva orden híbrido
        trimmed = candidates[:top_n]
        return [(ch, s, extra, None) for (ch, s, extra) in trimmed]

    model = _get_reranker()
    if model is None:
        trimmed = candidates[:top_n]
        return [(ch, s, extra, None) for (ch, s, extra) in trimmed]

    # Predicción
    pairs = [(query, ch.text or "") for (ch, _s, _extra) in candidates]
    batch_size = _get_setting("RERANK_BATCH_SIZE", 16)

    try:
        scores = model.predict(pairs, batch_size=batch_size, show_progress_bar=False).tolist()
    except Exception:
        # Falla silenciosa -> continua sin rerank
        trimmed = candidates[:top_n]
        return [(ch, s, extra, None) for (ch, s, extra) in trimmed]

    enriched = [(ch, s, extra, float(sc)) for (ch, s, extra), sc in zip(candidates, scores)]
    enriched.sort(key=lambda t: (t[3], t[1]), reverse=True)  # primero por rerank desc, luego híbrido desc
    return enriched[:top_n]


# =========================
# Síntesis de respuesta
# =========================
def synthesize_answer(query: str,
                      hits: List[Tuple[Chunk, float, Dict[str, float], Optional[float]]],
                      max_snippets: int = 5) -> Dict[str, Any]:
    """
    hits: [(chunk, score_hibrido, {"vec","lex"}, score_rerank)]
    """
    snippets = []
    for i, (ch, s_h, extra, s_rr) in enumerate(hits[:max_snippets], start=1):
        title = ch.document.title or f"{ch.document.source_slug.upper()} {ch.document.number or ''}".strip()
        preview = (ch.text or "")[:360].replace("\n", " ").strip()
        snippets.append({
            "rank": i,
            "document_id": ch.document_id,
            "chunk_id": ch.id,
            "title": title,
            "section": ch.section,
            "preview": preview,
            "similarity": round(float(extra.get("vec", 0.0)), 4),
            "lexical": round(float(extra.get("lex", 0.0)), 4) if extra.get("lex") is not None else None,
            "hybrid": round(float(s_h), 4),
            "rerank": (round(float(s_rr), 4) if s_rr is not None else None),
        })

    lines = [f"Consulta: {query}", "", "Pasajes relevantes:"]
    for s in snippets:
        extras = []
        extras.append(f"sim={s['similarity']}")
        if s["lexical"] is not None:
            extras.append(f"lex={s['lexical']}")
        extras.append(f"hyb={s['hybrid']}")
        if s["rerank"] is not None:
            extras.append(f"rr={s['rerank']}")
        lines.append(f"- {s['title']} [{s['section'] or 'BODY'}] ({', '.join(extras)}) — {s['preview']}")

    return {"text": "\n".join(lines), "snippets": snippets}


# =========================
# Orquestación principal
# =========================
def ask(user, query: str, session: Optional[ChatSession] = None) -> Tuple[ChatMessage, List[SearchHit]]:
    """
    Flujo:
      1) hybrid_search (lex + vec) -> candidatos ordenados por score híbrido
      2) rerank_hits (cross-encoder) sobre top CANDIDATES
      3) MMR opcional para diversidad en el conjunto rerankeado (sobre top_n)
      4) síntesis + persistencia
    """
    t0 = time.perf_counter()
    if session is None:
        title = (query[:80] + "…") if len(query) > 80 else query
        session = ChatSession.objects.create(user=user, title=title)

    # Guardar mensaje user
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, text=query)

    # 1) híbrido
    alpha = _get_setting("HYBRID_ALPHA", 0.6)
    search_top_k = _get_setting("SEARCH_TOP_K", 50)
    hybrid_scored = hybrid_search(query, top_k=search_top_k, alpha=alpha)  # [(chunk, s_h, {"vec","lex"})]

    # 2) rerank encima del híbrido (prefiltrando candidatos C)
    candidates = hybrid_scored[: _get_setting("RERANK_CANDIDATES", 80)]
    reranked = rerank_hits(query, candidates, top_n=_get_setting("RERANK_TOP_N", 20))
    # reranked: [(chunk, s_h, {"vec","lex"}, s_rr)]

    # 3) MMR opcional (trabaja con embeddings ya guardados)
    use_mmr = True
    max_snippets = 5
    final_hits: List[Tuple[Chunk, float, Dict[str, float], Optional[float]]]
    if use_mmr and reranked:
        # formato esperado por mmr_select: [(chunk, score_base, extra)]
        # score_base el rerank si existe; si no, el híbrido.
        base_for_mmr = [(ch, (s_rr if s_rr is not None else s_h), extra) for (ch, s_h, extra, s_rr) in reranked]
        qvec = _encode_query(query)
        k = max_snippets
        mmr_selected = mmr_select(base_for_mmr[: max(20, k * 4)], qvec, k=k, lambda_=0.7)
        # Reinyectar s_h y s_rr desde 'reranked' original
        map_info = {ch.id: (s_h, extra, s_rr) for (ch, s_h, extra, s_rr) in reranked}
        final_hits = []
        for (ch, _score_base, _extra) in mmr_selected:
            s_h, extra, s_rr = map_info[ch.id]
            final_hits.append((ch, s_h, extra, s_rr))
    else:
        final_hits = reranked[:max_snippets]

    # 4) síntesis
    answer = synthesize_answer(query, final_hits, max_snippets=max_snippets)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    # Persistencia
    with transaction.atomic():
        msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text=answer["text"],
            answer_json={
                "snippets": answer["snippets"],
                "alpha": alpha,
                "enable_rerank": bool(_get_setting("ENABLE_RERANK", True)),
            },
            latency_ms=latency_ms,
        )

        # Guardar todos los resultados rerankeados (no solo los de síntesis)
        hits: List[SearchHit] = []
        # Para orden estable, reconstrucción del orden final para almacenamiento:
        store_list = reranked  # ya está recortado a TOP_N
        for i, (ch, s_h, extra, s_rr) in enumerate(store_list, start=1):
            kwargs = dict(
                message=msg,
                document=ch.document,
                chunk=ch,
                rank=i,
                score_vector=float(extra.get("vec", 0.0)),
                meta_json={
                    "section": ch.section,
                    "lex": float(extra.get("lex", 0.0)) if extra.get("lex") is not None else 0.0,
                    "hybrid": float(s_h),
                    "rerank": (float(s_rr) if s_rr is not None else None),
                },
            )
            if hasattr(SearchHit, "score_rerank"):
                kwargs["score_rerank"] = (float(s_rr) if s_rr is not None else None)
            hits.append(SearchHit(**kwargs))
        SearchHit.objects.bulk_create(hits, batch_size=500)

    return msg, hits

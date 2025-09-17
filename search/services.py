import os
import time
import inspect
from typing import List, Tuple, Dict, Any

import numpy as np
from django.conf import settings
from django.db import transaction
from pgvector.django import CosineDistance
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank

from documents.models import Chunk, Document
from .models import ChatSession, ChatMessage, SearchHit

# Cache de modelo global (como en Celery)
_EMBED_MODEL = None

def _get_embedder():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        # Evita torchvision
        os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from sentence_transformers import SentenceTransformer
        name = os.getenv("EMBEDDINGS_MODEL", getattr(settings, "EMBEDDINGS_MODEL", "BAAI/bge-m3"))
        _EMBED_MODEL = SentenceTransformer(name)
    return _EMBED_MODEL


def _encode_query(text: str) -> np.ndarray:
    model = _get_embedder()
    kwargs = dict(normalize_embeddings=True, convert_to_numpy=True, batch_size=1)
    try:
        # Algunos modelos no traen prompts configurados
        if "prompt_name" in inspect.signature(model.encode).parameters and getattr(model, "prompts", None):
            if "query" in model.prompts:
                kwargs["prompt_name"] = "query"
    except (ValueError, TypeError):
        pass
    vec = model.encode([text], **kwargs)[0]
    return vec

def _minmax(values: List[float]) -> Tuple[float, float]:
    vmin, vmax = (min(values), max(values)) if values else (0.0, 0.0)
    return vmin, vmax

def vector_search(query_vec: np.ndarray, top_k: int = None) -> List[Tuple[Chunk, float]]:
    """
    Devuelve [(chunk, score_vector)] ordenados por similitud coseno ascendente (menor distancia = más similar).
    """
    if top_k is None:
        top_k = getattr(settings, "SEARCH_TOP_K", 50)

    # Asegúrate de que el documento esté indexado
    qs = (
        Chunk.objects
             .filter(document__state="INDEXED", embedding__isnull=False)
             .annotate(distance=CosineDistance("embedding", query_vec.tolist()))
             .select_related("document")
             .order_by("distance")[:top_k]
    )

    # score_vector: convertir distancia a similitud (1 - dist/2) o usar -distance
    results = []
    for ch in qs:
        # CosineDistance devuelve [0..2], 0 = idéntico. Normalizamos a similitud ~ [0..1]
        sim = 1.0 - float(ch.distance) / 2.0
        results.append((ch, sim))
    return results

def lexical_search(query: str, top_k: int | None = None) -> List[Tuple[Chunk, float]]:
    """
    Devuelve [(chunk, score_lexical)] ordenados por score desc.
    score_lexical = ts_rank_cd sobre tsvector(section+text) con config 'spanish'.
    """
    if top_k is None:
        top_k = getattr(settings, "SEARCH_TOP_K", 50)

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

    results = []
    for ch in qs:
        results.append((ch, float(ch.rank)))  # rank ~ [0..1], mayor es mejor
    return results

def hybrid_search(query: str, top_k: int | None = None, alpha: float | None = None) -> List[Tuple[Chunk, float, Dict[str, float]]]:
    """
    Devuelve [(chunk, score_hibrido, {"vec": sim, "lex": rank})] ordenado desc.
    """
    if top_k is None:
        top_k = getattr(settings, "SEARCH_TOP_K", 50)
    if alpha is None:
        alpha = getattr(settings, "HYBRID_ALPHA", 0.6)

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

    # 4) min-max normalization independiente
    vec_vals = [d.get("vec", 0.0) for d in by_id.values()]
    lex_vals = [d.get("lex", 0.0) for d in by_id.values()]
    vmin, vmax = _minmax(vec_vals)
    lmin, lmax = _minmax(lex_vals)

    def norm(v, vmin, vmax):
        if vmax <= vmin:
            return 0.0
        return (v - vmin) / (vmax - vmin)

    # 5) score híbrido
    scored = []
    for d in by_id.values():
        v = norm(d.get("vec", 0.0), vmin, vmax)
        l = norm(d.get("lex", 0.0), lmin, lmax)
        s = alpha * v + (1 - alpha) * l
        scored.append((d["chunk"], s, {"vec": d.get("vec", 0.0), "lex": d.get("lex", 0.0)}))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]

def mmr_select(candidates: List[Tuple[Chunk, float, Dict[str, float]]],
               qvec: np.ndarray,
               k: int = 10,
               lambda_: float = 0.7) -> List[Tuple[Chunk, float, Dict[str, float]]]:
    """
    MMR clásico: balancea relevancia al query y disimilitud entre seleccionados.
    Requiere embeddings de chunks; usamos los ya guardados.
    """
    selected: List[int] = []
    pool = list(range(len(candidates)))
    # Prepara matriz de embeddings en RAM (cuidado con muy grandes)
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
        selected.append(best_i)
        pool.remove(best_i)
        scores.append(best_val)

    return [candidates[i] for i in selected]

def synthesize_answer(query: str, hits: List[Tuple[Chunk, float]], max_snippets: int = 5) -> Dict[str, Any]:
    """
    MVP: responde con una síntesis simple (no-LLM) y citas.
    """
    snippets = []
    for i, (ch, sim) in enumerate(hits[:max_snippets], start=1):
        title = ch.document.title or f"{ch.document.source_slug.upper()} {ch.document.number or ''}".strip()
        preview = (ch.text or "")[:360].replace("\n", " ").strip()
        snippets.append({
            "rank": i,
            "document_id": ch.document_id,
            "chunk_id": ch.id,
            "title": title,
            "section": ch.section,
            "preview": preview,
            "similarity": round(sim, 4),
        })

    # Plantilla sencilla
    lines = [f"Consulta: {query}", "", "Pasajes relevantes:"]
    for s in snippets:
        lines.append(f"- {s['title']} [{s['section'] or 'BODY'}] (sim={s['similarity']}) — {s['preview']}")
    answer_text = "\n".join(lines)

    return {"text": answer_text, "snippets": snippets}


def ask(user, query: str, session: ChatSession | None = None) -> Tuple[ChatMessage, list[SearchHit]]:
    t0 = time.perf_counter()
    if session is None:
        session = ChatSession.objects.create(user=user, title=(query[:80] + "…") if len(query) > 80 else query)

    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, text=query)

    # --- HYBRID ---
    alpha = getattr(settings, "HYBRID_ALPHA", 0.6)
    top_k = getattr(settings, "SEARCH_TOP_K", 50)
    scored = hybrid_search(query, top_k=top_k, alpha=alpha)  # [(chunk, score, {"vec","lex"})]

    # --- MMR (opcional) ---
    use_mmr = True
    max_snippets = 5
    if use_mmr:
        qvec = _encode_query(query)
        scored = mmr_select(scored[: max(20, max_snippets*4)], qvec, k=max_snippets, lambda_=0.7)
    top_hits = [(ch, s) for (ch, s, _) in scored[:max_snippets]]

    answer = synthesize_answer(query, top_hits)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    with transaction.atomic():
        msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text=answer["text"],
            answer_json={"snippets": answer["snippets"], "alpha": alpha},
            latency_ms=latency_ms,
        )
        hits = []
        rank = 0
        for ch, s, extra in scored:
            rank += 1
            hits.append(SearchHit(
                message=msg,
                document=ch.document,
                chunk=ch,
                rank=rank,
                score_vector=float(extra.get("vec", 0.0)),
                meta_json={"section": ch.section, "lex": extra.get("lex", 0.0), "hybrid": float(s)},
            ))
        SearchHit.objects.bulk_create(hits, batch_size=500)
    return msg, hits

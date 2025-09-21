import os
import re
import time
import inspect
from datetime import datetime, timezone, date
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


# -------------------------
# Ranking weights (defaults)
# -------------------------
# Fórmula: S_final = W_ce*S_ce + W_vig*1[vigente] + W_org*peso_org + W_id*1[match_id] + W_t*recencia
RANK_WEIGHTS_DEFAULT = {
    "W_CE": 1.0,     # peso del cross-encoder (principal)
    "W_VIG": 0.75,   # bonificación por vigencia
    "W_ORG": 0.35,   # jerarquía del órgano/fuente
    "W_ID": 0.90,    # match explícito de identificador
    "W_T": 0.25,     # recencia (jurisprudencia)
}
# Mapea por slug/autoridad (usa el que exista)
ORG_WEIGHTS_DEFAULT = {
    "tcp": 1.0, "TCP": 1.0,
    "tsj": 0.8, "TSJ": 0.8,
    "sala": 0.6, "SALA": 0.6,
    "ley": 0.7, "LEY": 0.7,
    "cpe": 0.9, "CPE": 0.9,
    "alp": 0.7, "ALP": 0.7,
    "otros": 0.3, "OTROS": 0.3,
}
# Fuentes donde sí aplica recencia (jurisprudencia)
RECENCY_SOURCES_DEFAULT = {"tcp", "tsj", "sala"}
RECENCY_HALFLIFE_DAYS_DEFAULT = 4 * 365  # media-vida ≈ 4 años


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
# RRF (fusion candidates)
# =========================
def _rrf_score(rank: int, k: float = 60.0) -> float:
    # Reciprocal Rank Fusion: 1/(k + rank)
    return 1.0 / (k + rank)

def rrf_fuse(vec_pairs: List[Tuple[Chunk, float]],
             lex_pairs: List[Tuple[Chunk, float]],
             k_rrf: float = 60.0,
             limit: int = 100) -> List[Tuple[Chunk, float, Dict[str, float]]]:
    """
    Funde listas por RRF considerando los órdenes independientes.
    Entrada:
        vec_pairs: [(chunk, sim_vec)], ordenado desc por similitud
        lex_pairs: [(chunk, rank_lex)], ordenado desc por rank
    Salida:
        [(chunk, rrf_score_total, {"vec": sim, "lex": rank})] ordenado desc por rrf
    """
    # Mapear rangos
    rank_map_vec: Dict[int, int] = {}
    rank_map_lex: Dict[int, int] = {}

    for i, (ch, _s) in enumerate(sorted(vec_pairs, key=lambda t: t[1], reverse=True), start=1):
        rank_map_vec[ch.id] = i
    for i, (ch, _s) in enumerate(sorted(lex_pairs, key=lambda t: t[1], reverse=True), start=1):
        rank_map_lex[ch.id] = i

    # Unir IDs
    by_id: Dict[int, Dict[str, Any]] = {}
    for ch, s in vec_pairs:
        by_id.setdefault(ch.id, {"chunk": ch, "vec": float(s)})
    for ch, s in lex_pairs:
        d = by_id.setdefault(ch.id, {"chunk": ch})
        d["lex"] = float(s)

    fused: List[Tuple[Chunk, float, Dict[str, float]]] = []
    for cid, d in by_id.items():
        rrf = 0.0
        if cid in rank_map_vec:
            rrf += _rrf_score(rank_map_vec[cid], k_rrf)
        if cid in rank_map_lex:
            rrf += _rrf_score(rank_map_lex[cid], k_rrf)
        fused.append((d["chunk"], rrf, {"vec": float(d.get("vec", 0.0)), "lex": float(d.get("lex", 0.0))}))

    fused.sort(key=lambda x: x[1], reverse=True)
    return fused[:limit]


# =========================
# Señales jurídicas / utilidades
# =========================
def _norm_slug(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]+", "", s.lower())

def _infer_slug_from_storage(doc: Document) -> Optional[str]:
    sk = (doc.storage_key or "").lower()
    if "/tcp/" in sk:
        return "tcp"
    if "/tsj/" in sk:
        return "tsj"
    if "/normativa/" in sk and "/cpc/" in sk:
        return "cpc"
    if "/normativa/" in sk and ("cpe" in sk or "constitucion" in sk or "constitución" in sk):
        return "cpe"
    return None

def _get_source_slug(doc: Document) -> str:
    # 1) si viene en DB
    if getattr(doc, "source_slug", None):
        return _norm_slug(doc.source_slug)
    # 2) intentar por storage_key
    s = _infer_slug_from_storage(doc)
    if s:
        return s
    # 3) por título como último recurso
    title = (getattr(doc, "title", "") or "").lower()
    if "constitucional" in title or "scp" in title or "sc " in title:
        return "tcp"
    if "auto supremo" in title or " as " in title:
        return "tsj"
    if "ley" in title:
        return "ley"
    if "constitución" in title or "cpe" in title:
        return "cpe"
    return "otros"

def _deep_get(d: Any, keys: List[str]) -> Optional[str]:
    """Obtiene primera coincidencia truthy en dict anidado para claves variantes."""
    if not isinstance(d, dict):
        return None
    for k, v in d.items():
        if isinstance(v, dict):
            r = _deep_get(v, keys)
            if r is not None:
                return r
        else:
            if k.lower() in keys:
                return str(v)
    return None

def _is_vigente(doc: Document) -> bool:
    """
    Busca banderas de vigencia dentro de meta (jsonb). Si no hay dato, asume vigente.
    """
    meta = getattr(doc, "meta", None)
    if isinstance(meta, dict):
        raw = _deep_get(meta, ["vigente", "is_current", "is_active", "vigency", "vigencia"])
        if raw is not None:
            s = str(raw).strip().lower()
            if s in {"0", "false", "no", "derogado", "abrogado", "sin vigencia", "invalido", "inválido"}:
                return False
            if s in {"1", "true", "si", "sí", "vigente", "en vigor", "valido", "válido"}:
                return True
    # sin dato -> true por defecto
    return True

def _doc_date(doc: Document) -> Optional[datetime]:
    """
    Usa published_date (date) o year → datetime UTC.
    """
    pd = getattr(doc, "published_date", None)
    if isinstance(pd, date):
        return datetime(pd.year, pd.month, pd.day, tzinfo=timezone.utc)
    year = getattr(doc, "year", None)
    if isinstance(year, int) and 1500 < year < 2100:
        return datetime(year, 7, 1, tzinfo=timezone.utc)
    return None

_ID_PATTERNS = [
    r"\bsc?p?\s*\d+/\d{4}\b",       # SC/SCP 0001/2019
    r"\bas\s*\d+/\d{4}\b",          # AS 123/2020
    r"\bauto\s+supremo\s*\d+/\d{4}\b",
    r"\bsentencia\s+constitucional\s*\d+/\d{4}\b",
    r"\bley\s+\d{1,4}\b",           # Ley 004
    r"\btsj\s*\d+/\d{4}\b",
]

def _extract_ids(raw_query: str) -> List[str]:
    q = raw_query.lower()
    ids: List[str] = []
    for pat in _ID_PATTERNS:
        ids += re.findall(pat, q)
    # normalizar espacios
    ids = [re.sub(r"\s+", " ", s.strip()) for s in ids]
    return list(dict.fromkeys(ids))  # unique, keep order

def _match_exacto_id(doc: Document, query_ids: List[str]) -> bool:
    if not query_ids:
        return False
    title = (getattr(doc, "title", "") or "").lower()
    number = (getattr(doc, "number", "") or "").lower()
    text_ids = [title, number]
    for s in text_ids:
        if not s:
            continue
        for qid in query_ids:
            if qid in s:
                return True
    return False

def _org_weight(doc: Document) -> float:
    org_map = _get_setting("ORG_WEIGHTS", ORG_WEIGHTS_DEFAULT)
    authority = (getattr(doc, "authority", None) or "").strip()
    src = _get_source_slug(doc)
    # intenta con autoridad, luego slug, luego otros
    if authority in org_map:
        return float(org_map[authority])
    if src in org_map:
        return float(org_map[src])
    return float(org_map.get("otros", 0.3))

def _recency_score(doc: Document) -> float:
    src = _get_source_slug(doc)
    recency_sources = set(_get_setting("RECENCY_SOURCES", RECENCY_SOURCES_DEFAULT))
    if src not in recency_sources:
        return 0.0
    dt = _doc_date(doc)
    if dt is None:
        return 0.0
    now = datetime.now(tz=timezone.utc)
    age_days = max(0.0, (now - dt).days)
    half_life = float(_get_setting("RECENCY_HALFLIFE_DAYS", RECENCY_HALFLIFE_DAYS_DEFAULT))
    # decaimiento exponencial con media-vida: score in (0,1]
    return float(0.5 ** (age_days / max(1.0, half_life)))

def compute_legal_signals(query: str, doc: Document) -> Dict[str, Any]:
    ids = _extract_ids(query)
    vigente = _is_vigente(doc)
    match_id = _match_exacto_id(doc, ids)
    org_w = _org_weight(doc)
    rec = _recency_score(doc)
    return {
        "vigente": bool(vigente),
        "match_id": bool(match_id),
        "peso_org": float(org_w),
        "recencia": float(rec),
    }

def combine_final_score(s_ce: float, signals: Dict[str, Any]) -> float:
    W = _get_setting("RANK_WEIGHTS", RANK_WEIGHTS_DEFAULT)
    w_ce = float(W.get("W_CE", RANK_WEIGHTS_DEFAULT["W_CE"]))
    w_vig = float(W.get("W_VIG", RANK_WEIGHTS_DEFAULT["W_VIG"]))
    w_org = float(W.get("W_ORG", RANK_WEIGHTS_DEFAULT["W_ORG"]))
    w_id = float(W.get("W_ID", RANK_WEIGHTS_DEFAULT["W_ID"]))
    w_t = float(W.get("W_T", RANK_WEIGHTS_DEFAULT["W_T"]))

    term_vig = 1.0 if signals.get("vigente") else 0.0
    term_id = 1.0 if signals.get("match_id") else 0.0
    term_org = float(signals.get("peso_org", 0.0))
    term_t = float(signals.get("recencia", 0.0))

    # Nota: S_ce ya está en escala del CrossEncoder (mayor es mejor).
    return (
        w_ce * float(s_ce)
        + w_vig * term_vig
        + w_org * term_org
        + w_id * term_id
        + w_t * term_t
    )


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
    Entrada: [(chunk, score_base, {"vec","lex"})]
    Salida:  [(chunk, score_base, {"vec","lex"}, score_rerank)]
    """
    if top_n is None:
        top_n = _get_setting("RERANK_CANDIDATES", 100)

    if not _get_setting("ENABLE_RERANK", True) or not candidates:
        trimmed = candidates[:top_n]
        return [(ch, s, extra, None) for (ch, s, extra) in trimmed]

    model = _get_reranker()
    if model is None:
        trimmed = candidates[:top_n]
        return [(ch, s, extra, None) for (ch, s, extra) in trimmed]

    # Predicción
    pairs = [(query, ch.text or "") for (ch, _s, _extra) in candidates[:top_n]]
    batch_size = _get_setting("RERANK_BATCH_SIZE", 16)

    try:
        scores = model.predict(pairs, batch_size=batch_size, show_progress_bar=False).tolist()
    except Exception:
        trimmed = candidates[:top_n]
        return [(ch, s, extra, None) for (ch, s, extra) in trimmed]

    enriched = [(ch, s, extra, float(sc)) for (ch, s, extra), sc in zip(candidates[:top_n], scores)]
    # La combinación final aplicará la fórmula y reordenará
    return enriched


# =========================
# Síntesis de respuesta
# =========================
def synthesize_answer(query: str,
                      hits: List[Tuple[Chunk, float, Dict[str, float], Optional[float], float, Dict[str, Any]]],
                      max_snippets: int = 5) -> Dict[str, Any]:
    """
    hits: [(chunk, score_hibrido/rrf, {"vec","lex"}, score_rerank, final_score, signals)]
    """
    snippets = []
    for i, (ch, s_base, extra, s_rr, s_final, signals) in enumerate(hits[:max_snippets], start=1):
        src = (ch.document.source_slug or "").upper() if getattr(ch.document, "source_slug", None) else ""
        title = ch.document.title or f"{src} {ch.document.number or ''}".strip()
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
            "base": round(float(s_base), 4),
            "rerank": (round(float(s_rr), 4) if s_rr is not None else None),
            "final": round(float(s_final), 4),
            "signals": {
                "vigente": bool(signals.get("vigente")),
                "peso_org": round(float(signals.get("peso_org", 0.0)), 3),
                "match_id": bool(signals.get("match_id")),
                "recencia": round(float(signals.get("recencia", 0.0)), 3),
            }
        })

    lines = [f"Consulta: {query}", "", "Pasajes relevantes:"]
    for s in snippets:
        badges = []
        if s["signals"]["vigente"]:
            badges.append("vigente")
        if s["signals"]["match_id"]:
            badges.append("ID exacto")
        if s["signals"]["peso_org"] > 0:
            badges.append(f"órg={s['signals']['peso_org']}")
        if s["signals"]["recencia"] > 0:
            badges.append(f"t={s['signals']['recencia']}")
        extras = []
        extras.append(f"base={s['base']}")
        if s["rerank"] is not None:
            extras.append(f"ce={s['rerank']}")
        extras.append(f"final={s['final']}")
        lines.append(f"- {s['title']} [{s['section'] or 'BODY'}] ({', '.join(extras)} | {'; '.join(badges)}) — {s['preview']}")

    return {"text": "\n".join(lines), "snippets": snippets}


# =========================
# Orquestación principal
# =========================
def ask(user, query: str, session: Optional[ChatSession] = None) -> Tuple[ChatMessage, List[SearchHit]]:
    """
    Flujo:
      1) retrieve (vec + lex) -> RRF (C=FUSION_CANDIDATES)
      2) rerank (cross-encoder) sobre C
      3) combinar señales jurídicas (fórmula) -> ordenar -> quedarnos con TOP_N
      4) (opcional) MMR sobre TOP_N para diversidad visual
      5) síntesis + persistencia
    """
    t0 = time.perf_counter()
    if session is None:
        title = (query[:80] + "…") if len(query) > 80 else query
        session = ChatSession.objects.create(user=user, title=title)

    # Guardar mensaje user
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, text=query)

    # 1) retrieve vec+lex y fusionar por RRF
    search_top_k = _get_setting("SEARCH_TOP_K", 50)
    qvec = _encode_query(query)
    vec_pairs = vector_search(qvec, top_k=search_top_k)
    lex_pairs = lexical_search(query, top_k=search_top_k)
    fusion_candidates = _get_setting("FUSION_CANDIDATES", 100)
    rrf_scored = rrf_fuse(vec_pairs, lex_pairs, k_rrf=float(_get_setting("RRF_K", 60.0)), limit=fusion_candidates)
    # rrf_scored: [(chunk, s_rrf, {"vec","lex"})]

    # 2) rerank encima del RRF (prefiltrando candidatos C)
    rerank_candidates = _get_setting("RERANK_CANDIDATES", fusion_candidates)
    reranked = rerank_hits(query, rrf_scored, top_n=rerank_candidates)
    # reranked: [(chunk, s_rrf, {"vec","lex"}, s_ce)]

    # 3) combinación determinística con señales jurídicas
    combined: List[Tuple[Chunk, float, Dict[str, float], Optional[float], float, Dict[str, Any]]] = []
    for (ch, s_base, extra, s_ce) in reranked:
        ce = float(s_ce if s_ce is not None else s_base)  # si falla CE, usar base
        signals = compute_legal_signals(query, ch.document)
        s_final = combine_final_score(ce, signals)
        combined.append((ch, s_base, extra, s_ce, s_final, signals))

    combined.sort(key=lambda t: (t[4], t[1]), reverse=True)  # final desc, desempate por base (RRF)

    # Mantener TOP_N para UI
    top_n = int(_get_setting("RERANK_TOP_N", 12))
    top_for_ui = combined[:top_n]

    # 4) MMR opcional para diversidad visual (sobre TOP_N ya combinado)
    use_mmr = True
    max_snippets = 5
    if use_mmr and top_for_ui:
        # MMR usa como base el score final
        mmr_in = [(ch, s_final, extra) for (ch, _s_base, extra, _s_ce, s_final, _signals) in top_for_ui]
        mmr_selected = mmr_select(mmr_in, qvec, k=max_snippets, lambda_=0.7)
        # Reinyectar estructuras originales preservando s_final
        id_map = {ch.id: (s_base, extra, s_ce, s_final, signals) for (ch, s_base, extra, s_ce, s_final, signals) in top_for_ui}
        final_hits = []
        for (ch, _score_base, _extra) in mmr_selected:
            s_base, extra, s_ce, s_final, signals = id_map[ch.id]
            final_hits.append((ch, s_base, extra, s_ce, s_final, signals))
    else:
        final_hits = top_for_ui[:max_snippets]

    # 5) síntesis
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
                "enable_rerank": bool(_get_setting("ENABLE_RERANK", True)),
                "weights": _get_setting("RANK_WEIGHTS", RANK_WEIGHTS_DEFAULT),
                "org_weights": _get_setting("ORG_WEIGHTS", ORG_WEIGHTS_DEFAULT),
            },
            latency_ms=latency_ms,
        )

        # Guardar todos los resultados combinados (TOP_N)
        hits: List[SearchHit] = []
        for i, (ch, s_base, extra, s_ce, s_final, signals) in enumerate(top_for_ui, start=1):
            kwargs = dict(
                message=msg,
                document=ch.document,
                chunk=ch,
                rank=i,
                score_vector=float(extra.get("vec", 0.0)),
                meta_json={
                    "section": ch.section,
                    "lex": float(extra.get("lex", 0.0)) if extra.get("lex") is not None else 0.0,
                    "base_rrf": float(s_base),
                    "rerank_ce": (float(s_ce) if s_ce is not None else None),
                    "final_score": float(s_final),
                    "signals": {
                        "vigente": bool(signals.get("vigente")),
                        "peso_org": float(signals.get("peso_org", 0.0)),
                        "match_id": bool(signals.get("match_id")),
                        "recencia": float(signals.get("recencia", 0.0)),
                    },
                },
            )
            if hasattr(SearchHit, "score_rerank"):
                kwargs["score_rerank"] = (float(s_ce) if s_ce is not None else None)
            hits.append(SearchHit(**kwargs))
        SearchHit.objects.bulk_create(hits, batch_size=500)

    return msg, hits


# =========================
# Diversidad (MMR)
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
        selected.append(best_i)              # type: ignore[arg-type]
        pool.remove(best_i)                  # type: ignore[arg-type]
    return [candidates[i] for i in selected]

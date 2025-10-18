from typing import List, Tuple, Dict, Optional, Sequence
from hashlib import sha1

from django.core.cache import cache

from apps.documents.models import Chunk
from .settings import get_setting
from .cache import key_pair  # lo seguimos importando por compat si lo usas en otros lados
from .signals import compute_legal_signals, combine_final_score_vector
from common.clients.tei_rerank import tei_rerank_scores

# ---- Caché (Redis vía django-redis) ----
CE_CACHE_TTL = int(get_setting("RERANK_CACHE_TTL", 60 * 60 * 24 * 7))  # 7 días
CE_NS = "ce:"  # namespace para llaves

# Métricas para diagnóstico (leídas desde ask.py opcionalmente)
_LAST_CACHE_STATS: Dict[str, int] = {"hits": 0, "miss": 0, "set": 0}


def get_last_cache_stats() -> Dict[str, int]:
    """Devuelve y resetea las métricas de uso de caché (para logging en ask.py)."""
    global _LAST_CACHE_STATS
    out = dict(_LAST_CACHE_STATS)
    _LAST_CACHE_STATS = {"hits": 0, "miss": 0, "set": 0}
    return out


def _doc_from_chunk(ch: Chunk):
    try:
        return ch.document
    except Exception:
        return None


def _remote_scores_hf(query: str, docs: Sequence[str]) -> Optional[List[float]]:
    try:
        return tei_rerank_scores(query, list(docs), raw=True)
    except Exception:
        return None


def _stable_key(query: str, ch: Chunk) -> str:
    """
    Key robusta y estable para Redis:
      - sha1 del query normalizado
      - id de chunk
      - len(text)
      - updated_ts en segundos (o 0)
    """
    qh = sha1(query.strip().encode("utf-8")).hexdigest()[:20]
    text_len = len(ch.text or "")
    updated = getattr(ch, "updated_at", None)
    try:
        updated_ts = int(updated.timestamp()) if updated else 0
    except Exception:
        updated_ts = 0
    return f"{CE_NS}{qh}:{ch.id}:{text_len}:{updated_ts}"


def rerank_hits(
    query: str,
    candidates: List[Tuple[Chunk, float, Dict[str, float]]],
    top_n: Optional[int] = None
) -> List[Tuple[Chunk, float, Dict[str, float], Optional[float], float, dict]]:

    if top_n is None:
        top_n = get_setting("RERANK_CANDIDATES", 100)

    if not get_setting("ENABLE_RERANK", True) or not candidates:
        trimmed = candidates[:top_n]
        out = []
        for (ch, s, extra) in trimmed:
            doc = _doc_from_chunk(ch)
            sig = compute_legal_signals(query, getattr(doc, 'document', doc) or doc) if doc else {}
            s_ce = None
            s_final = combine_final_score_vector(0.0, sig)
            out.append((ch, s, extra, s_ce, s_final, sig))
        out.sort(key=lambda t: t[4], reverse=True)
        return out

    cand_trim = candidates[:top_n]

    keys: List[str] = [_stable_key(query, ch) for (ch, _s, _e) in cand_trim]

    cached: Dict[str, float] = cache.get_many(keys) if keys else {}

    scores_out: List[Optional[float]] = [None] * len(cand_trim)
    need_idx: List[int] = []
    need_docs: List[str] = []

    for i, (ch, _s, _e) in enumerate(cand_trim):
        k = keys[i]
        sc = cached.get(k)
        if sc is None:
            need_idx.append(i)
            need_docs.append(ch.text or "")
            _LAST_CACHE_STATS["miss"] += 1
        else:
            scores_out[i] = float(sc)
            _LAST_CACHE_STATS["hits"] += 1

    to_set: Dict[str, float] = {}
    if need_idx:
        remote_scores = _remote_scores_hf(query, need_docs)
        if remote_scores and len(remote_scores) == len(need_docs):
            for j, i in enumerate(need_idx):
                val = float(remote_scores[j])
                scores_out[i] = val
                to_set[keys[i]] = val
            if to_set:
                cache.set_many(to_set, timeout=CE_CACHE_TTL)
                _LAST_CACHE_STATS["set"] += len(to_set)

    enriched: List[Tuple[Chunk, float, Dict[str, float], Optional[float], float, dict]] = []
    for (tpl, sc) in zip(cand_trim, scores_out):
        ch, s_base, extra = tpl
        doc = _doc_from_chunk(ch)
        sig = compute_legal_signals(query, getattr(doc, 'document', doc) or doc) if doc else {}
        s_ce = (None if sc is None else float(sc))
        s_final = combine_final_score_vector(s_ce or 0.0, sig)
        enriched.append((ch, s_base, extra, s_ce, s_final, sig))

    enriched.sort(key=lambda t: t[4], reverse=True)
    return enriched

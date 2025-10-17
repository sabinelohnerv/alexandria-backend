import os
from typing import List, Tuple, Dict, Optional, Sequence

from documents.models import Chunk
from .settings import get_setting
from .cache import key_pair
from .signals import compute_legal_signals, combine_final_score_vector
from common.clients.tei_rerank import tei_rerank_scores

_CE_SCORE_CACHE: Dict[str, float] = {}
_CE_CACHE_MAX = 20000

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

    texts: List[str] = [(c[0].text or "") for c in cand_trim]
    scores_out: List[Optional[float]] = [None] * len(cand_trim)
    need_idx: List[int] = []
    need_docs: List[str] = []

    for i, (ch, _s, _extra) in enumerate(cand_trim):
        updated = getattr(ch, "updated_at", None)
        k = key_pair(query, ch.id, updated, len(ch.text or ""))
        sc = _CE_SCORE_CACHE.get(k)
        if sc is None:
            need_idx.append(i)
            need_docs.append(texts[i])
        else:
            scores_out[i] = sc

    if need_idx:
        remote_scores = _remote_scores_hf(query, need_docs)
        if remote_scores and len(remote_scores) == len(need_docs):
            for j, i in enumerate(need_idx):
                ch = cand_trim[i][0]
                updated = getattr(ch, "updated_at", None)
                k = key_pair(query, ch.id, updated, len(ch.text or ""))
                val = float(remote_scores[j])
                scores_out[i] = val
                if len(_CE_SCORE_CACHE) >= _CE_CACHE_MAX:
                    _CE_SCORE_CACHE.pop(next(iter(_CE_SCORE_CACHE)))
                _CE_SCORE_CACHE[k] = val

    enriched = []
    for (tpl, sc) in zip(cand_trim, scores_out):
        ch, s_base, extra = tpl
        doc = _doc_from_chunk(ch)
        sig = compute_legal_signals(query, getattr(doc, 'document', doc) or doc) if doc else {}
        s_ce = (None if sc is None else float(sc))
        s_final = combine_final_score_vector(s_ce or 0.0, sig)
        enriched.append((ch, s_base, extra, s_ce, s_final, sig))

    enriched.sort(key=lambda t: t[4], reverse=True)
    return enriched

from typing import List, Tuple, Dict, Optional, Sequence
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from apps.documents.models import Chunk
from .settings import get_setting
from .cache import key_pair
from .signals import compute_legal_signals, combine_final_score_vector
from common.clients.tei_rerank import tei_rerank_scores

_CE_SCORE_CACHE: Dict[str, float] = {}
_CE_CACHE_MAX = 200_000

def _doc_from_chunk(ch: Chunk):
    try:
        return ch.document
    except Exception:
        return None

def _remote_scores_parallel(query: str, docs: Sequence[str], workers: int = 2, shard_size: int = 12) -> Optional[List[float]]:
    n = len(docs)
    if n == 0:
        return []

    idxs = list(range(n))
    shards = [idxs[i:i+shard_size] for i in range(0, n, shard_size)]

    results: Dict[int, float] = {}
    def _call(shard: List[int]):
        sub = [docs[i] for i in shard]
        scores = tei_rerank_scores(query, sub, raw=True)
        for local_pos, global_idx in enumerate(shard):
            results[global_idx] = float(scores[local_pos])

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(shards)))) as ex:
        futs = [ex.submit(_call, sh) for sh in shards]
        for _ in as_completed(futs):
            pass

    # Re-construir en orden
    if len(results) != n:
        return None
    return [results[i] for i in range(n)]

def rerank_hits(
    query: str,
    candidates: List[Tuple[Chunk, float, Dict[str, float]]],
    top_n: Optional[int] = None
) -> List[Tuple[Chunk, float, Dict[str, float], Optional[float], float, dict]]:


    if top_n is None:
        top_n = int(get_setting("RERANK_CANDIDATES", 24))
    max_chars = int(get_setting("MAX_RERANK_CHARS", 900))
    per_doc_cap = int(get_setting("RERANK_DOC_CAP", 2))
    tei_workers = int(get_setting("TEI_WORKERS", 2))          
    tei_shard   = int(get_setting("TEI_SHARD_SIZE", 16))     

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

    # ----- 1) Cap por documento + recorte a top_n -----
    seen_per_doc: Dict[int, int] = defaultdict(int)
    pretrim: List[Tuple[Chunk, float, Dict[str, float]]] = []
    for tpl in candidates:
        ch, s_base, extra = tpl
        did = getattr(ch, "document_id", None)
        if seen_per_doc[did] < per_doc_cap:
            pretrim.append(tpl)
            seen_per_doc[did] += 1
        if len(pretrim) >= top_n:
            break
    cand_trim = pretrim if pretrim else candidates[:top_n]

    # ----- 2) Construcción de payload + caché -----
    texts: List[str] = []
    for ch, _s, _e in cand_trim:
        t = ch.text or ""
        if max_chars and len(t) > max_chars:
            t = t[:max_chars]
        texts.append(t)

    scores_out: List[Optional[float]] = [None] * len(cand_trim)
    need_idx: List[int] = []
    need_docs: List[str] = []
    for i, (ch, _s, _e) in enumerate(cand_trim):
        updated = getattr(ch, "updated_at", None)
        k = key_pair(query, ch.id, updated, len(texts[i]))  
        sc = _CE_SCORE_CACHE.get(k)
        if sc is None:
            need_idx.append(i)
            need_docs.append(texts[i]) 
        else:
            scores_out[i] = sc

    # ----- 3) TEI en paralelo -----
    if need_idx:
        remote_scores = _remote_scores_parallel(query, need_docs, workers=tei_workers, shard_size=tei_shard)
        if remote_scores and len(remote_scores) == len(need_docs):
            for j, i in enumerate(need_idx):
                ch = cand_trim[i][0]
                updated = getattr(ch, "updated_at", None)
                k = key_pair(query, ch.id, updated, len(texts[i]))
                val = float(remote_scores[j])
                scores_out[i] = val
                if len(_CE_SCORE_CACHE) >= _CE_CACHE_MAX:
                    try:
                        _CE_SCORE_CACHE.pop(next(iter(_CE_SCORE_CACHE)))
                    except StopIteration:
                        _CE_SCORE_CACHE.clear()
                _CE_SCORE_CACHE[k] = val

    # ----- 4) Combinar con señales -----
    enriched: List[Tuple[Chunk, float, Dict[str, float], Optional[float], float, dict]] = []
    for (tpl, sc) in zip(cand_trim, scores_out):
        ch, s_base, extra = tpl
        doc = _doc_from_chunk(ch)
        sig = compute_legal_signals(query, getattr(doc, 'document', doc) or doc) if doc else {}
        s_ce = None if sc is None else float(sc)
        s_final = combine_final_score_vector((s_ce or 0.0), sig)
        enriched.append((ch, s_base, extra, s_ce, s_final, sig))

    enriched.sort(key=lambda t: t[4], reverse=True)
    return enriched


from typing import List, Tuple, Dict, Any, Optional
import numpy as np
from pgvector.django import CosineDistance
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank

from documents.models import Chunk
from .settings import get_setting

# ---- Vector search -----------------------------------------------------------
def vector_search(query_vec: np.ndarray, top_k: Optional[int] = None) -> List[Tuple[Chunk, float]]:
    if top_k is None:
        top_k = get_setting("SEARCH_TOP_K", 50)

    qs = (
        Chunk.objects
             .filter(document__state="INDEXED", embedding__isnull=False)
             .annotate(distance=CosineDistance("embedding", query_vec.tolist()))
             .select_related("document")
             .order_by("distance")[:top_k]
    )
    out: List[Tuple[Chunk, float]] = []
    for ch in qs:
        sim = 1.0 - float(ch.distance) / 2.0
        out.append((ch, sim))
    return out


# ---- Lexical search ----------------------------------------------------------
def lexical_search(query: str, top_k: Optional[int] = None) -> List[Tuple[Chunk, float]]:
    if top_k is None:
        top_k = get_setting("SEARCH_TOP_K", 50)

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


# ---- RRF fusion --------------------------------------------------------------
def _rrf_score(rank: int, k: float = 60.0) -> float:
    return 1.0 / (k + rank)

def rrf_fuse(vec_pairs: List[Tuple[Chunk, float]],
             lex_pairs: List[Tuple[Chunk, float]],
             k_rrf: float = 60.0,
             limit: int = 100) -> List[Tuple[Chunk, float, Dict[str, float]]]:
    rank_map_vec: Dict[int, int] = {}
    rank_map_lex: Dict[int, int] = {}

    for i, (ch, _s) in enumerate(sorted(vec_pairs, key=lambda t: t[1], reverse=True), start=1):
        rank_map_vec[ch.id] = i
    for i, (ch, _s) in enumerate(sorted(lex_pairs, key=lambda t: t[1], reverse=True), start=1):
        rank_map_lex[ch.id] = i

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

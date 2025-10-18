# retrieval.py (optimizado)
from __future__ import annotations
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
from django.db import connection
from django.db.models import Prefetch
from apps.documents.models import Chunk  
from .settings import get_setting


def _table_names():
    chunk_tbl = Chunk._meta.db_table
    doc_field = Chunk._meta.get_field("document")
    doc_tbl = doc_field.remote_field.model._meta.db_table
    return chunk_tbl, doc_tbl

def _embedding_dim() -> int:
    try:
        return getattr(Chunk._meta.get_field("embedding"), "dimensions", 1024) or 1024
    except Exception:
        return 1024

def _inflate_chunks(rows: List[Tuple], columns=("id", "section", "block", "text", "document_id")) -> Dict[int, Chunk]:
    ids = [r[0] for r in rows]
    if not ids:
        return {}
    qs = (Chunk.objects
                .filter(id__in=ids)
                .select_related("document")
                .only("id", "section", "block", "text", "document_id"))
    by_id = {c.id: c for c in qs}
    for r in rows:
        cid, section, block, text, doc_id = r[:5]
        ch = by_id.get(cid)
        if ch:
            ch.section = section
            ch.block = block
            ch.text = text
            ch.document_id = doc_id
    return by_id


# === Vector search (usa ANN de pgvector) =====================================

def vector_search(query_vec: np.ndarray, top_k: Optional[int] = None) -> List[Tuple[Chunk, float]]:
    """
    Busca por similitud coseno usando el índice ANN (HNSW) con opclass `vector_cosine_ops`.
    Asegura el patrón `ORDER BY embedding <=> :vec LIMIT :k` para que el planner use el índice.
    """
    if top_k is None:
        top_k = int(get_setting("SEARCH_TOP_K", 50))

    chunk_tbl, doc_tbl = _table_names()
    dim = _embedding_dim()

    hnsw_ef = get_setting("HNSW_EF_SEARCH", None)
    ivf_probes = get_setting("IVFFLAT_PROBES", None)

    sql_set = []
    if isinstance(hnsw_ef, int) and hnsw_ef > 0:
        sql_set.append("SET LOCAL hnsw.ef_search = %s")
    if isinstance(ivf_probes, int) and ivf_probes > 0:
        sql_set.append("SET LOCAL ivfflat.probes = %s")

    sql = f"""
    SELECT c.id, c.section, c.block, c.text, c.document_id,
           (c.embedding <=> %s::vector({dim})) AS dist
    FROM {chunk_tbl} AS c
    JOIN {doc_tbl}   AS d ON d.id = c.document_id
    WHERE d.state = 'INDEXED' AND c.embedding IS NOT NULL
    ORDER BY c.embedding <=> %s::vector({dim})
    LIMIT %s
    """

    # Parametriza (mismo vector 2 veces para ORDER BY y proyección)
    vec = [float(x) for x in query_vec.tolist()]
    params: List[Any] = []
    if sql_set:
        with connection.cursor() as cur:
            i = 0
            for stmt in sql_set:
                cur.execute(stmt, [(hnsw_ef if "hnsw" in stmt else ivf_probes)])
            cur.execute(sql, [vec, vec, top_k])
            rows = cur.fetchall()
    else:
        with connection.cursor() as cur:
            cur.execute(sql, [vec, vec, top_k])
            rows = cur.fetchall()

    if not rows:
        return []

    by_id = _inflate_chunks(rows)
    out: List[Tuple[Chunk, float]] = []
    for (_cid, _sec, _blk, _txt, _doc, dist) in rows:
        ch = by_id.get(_cid)
        if ch:
            # distancia coseno ∈ [0..2]; similitud ~ [0..1]
            sim = 1.0 - float(dist) / 2.0
            out.append((ch, sim))
    return out


# === Lexical search (tsvector + GIN; 2 etapas) ===============================

def lexical_search(query: str, top_k: Optional[int] = None) -> List[Tuple[Chunk, float]]:
    """
    Usa la columna generada `tsv` (config `spanish_unaccent`) e índice GIN.
    Fase 1: filtra candidatos (rápido con GIN).
    Fase 2: rankea pocos con `ts_rank_cd`.
    """
    if top_k is None:
        top_k = int(get_setting("SEARCH_TOP_K", 50))

    chunk_tbl, doc_tbl = _table_names()
    cand_cap = int(get_setting("LEXICAL_CANDIDATE_CAP", 1000))

    sql = f"""
    WITH cand AS (
      SELECT c.id, c.tsv
      FROM {chunk_tbl} AS c
      JOIN {doc_tbl}   AS d ON d.id = c.document_id
      WHERE d.state = 'INDEXED'
        AND c.tsv @@ websearch_to_tsquery('spanish_unaccent', %s)
      LIMIT %s
    )
    SELECT c.id,
           ts_rank_cd(c.tsv, websearch_to_tsquery('spanish_unaccent', %s)) AS r
    FROM cand c
    ORDER BY r DESC
    LIMIT %s
    """

    with connection.cursor() as cur:
        cur.execute(sql, [query, cand_cap, query, top_k])
        rows = cur.fetchall()  # [(id, rank), ...]

    if not rows:
        return []

    ids = [r[0] for r in rows]
    chunks = {c.id: c for c in (Chunk.objects
                                    .filter(id__in=ids)
                                    .select_related("document")
                                    .only("id", "section", "block", "text", "document_id"))}

    out: List[Tuple[Chunk, float]] = []
    for (cid, rank) in rows:
        ch = chunks.get(cid)
        if ch:
            out.append((ch, float(rank)))
    return out


# === RRF fusion (simple y cache-friendly) ====================================

def _rrf_score(rank: int, k: float = 60.0) -> float:
    return 1.0 / (k + rank)

def rrf_fuse(
    vec_pairs: List[Tuple[Chunk, float]],
    lex_pairs: List[Tuple[Chunk, float]],
    k_rrf: float = 60.0,
    limit: int = 100
) -> List[Tuple[Chunk, float, Dict[str, float]]]:
    rank_vec: Dict[int, int] = {ch.id: i for i, (ch, _) in enumerate(sorted(vec_pairs, key=lambda t: t[1], reverse=True), 1)}
    rank_lex: Dict[int, int] = {ch.id: i for i, (ch, _) in enumerate(sorted(lex_pairs, key=lambda t: t[1], reverse=True), 1)}

    by_id: Dict[int, Dict[str, Any]] = {}
    for ch, s in vec_pairs:
        by_id.setdefault(ch.id, {"chunk": ch, "vec": float(s)})
    for ch, s in lex_pairs:
        d = by_id.setdefault(ch.id, {"chunk": ch})
        d["lex"] = float(s)

    fused: List[Tuple[Chunk, float, Dict[str, float]]] = []
    for cid, d in by_id.items():
        rrf = 0.0
        rv = rank_vec.get(cid)
        rl = rank_lex.get(cid)
        if rv: rrf += _rrf_score(rv, k_rrf)
        if rl: rrf += _rrf_score(rl, k_rrf)
        fused.append((d["chunk"], rrf, {
            "vec": float(d.get("vec", 0.0)),
            "lex": float(d.get("lex", 0.0)),
        }))

    fused.sort(key=lambda x: x[1], reverse=True)
    return fused[:limit]
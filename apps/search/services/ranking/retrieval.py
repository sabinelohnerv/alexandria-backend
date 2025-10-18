from __future__ import annotations
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
from django.db import connection
from apps.documents.models import Chunk  
from .settings import get_setting




def _table_names() -> Tuple[str, str]:
    chunk_tbl = Chunk._meta.db_table
    doc_field = Chunk._meta.get_field("document")
    doc_tbl = doc_field.remote_field.model._meta.db_table
    return chunk_tbl, doc_tbl

def _embedding_dim() -> int:
    try:
        return int(getattr(Chunk._meta.get_field("embedding"), "dimensions", 1024) or 1024)
    except Exception:
        return 1024

def _inflate_chunks(rows: List[Tuple]) -> Dict[int, Chunk]:
    ids = [r[0] for r in rows]
    if not ids:
        return {}
    qs = (
        Chunk.objects
             .filter(id__in=ids)
             .select_related("document")
             .only("id", "section", "block", "text", "document_id")
    )
    by_id = {c.id: c for c in qs}
    for (cid, section, block, text, doc_id, _dist) in rows:
        ch = by_id.get(cid)
        if ch:
            ch.section = section
            ch.block = block
            ch.text = text
            ch.document_id = doc_id
    return by_id


# ------------------------ Vector search (ANN) --------------------------------

def vector_search(query_vec: np.ndarray, top_k: Optional[int] = None) -> List[Tuple[Chunk, float]]:
    if top_k is None:
        top_k = int(get_setting("SEARCH_TOP_K", 50))

    chunk_tbl, doc_tbl = _table_names()
    dim = _embedding_dim()

    filter_by_doc_state = True

    if filter_by_doc_state:
        sql = f"""
        SELECT c.id, c.section, c.block, c.text, c.document_id,
               (c.embedding <=> %s::vector({dim})) AS dist
        FROM {chunk_tbl} AS c
        JOIN {doc_tbl}   AS d ON d.id = c.document_id
        WHERE d.state = 'INDEXED' AND c.embedding IS NOT NULL
        ORDER BY c.embedding <=> %s::vector({dim})
        LIMIT %s
        """
    else:
        sql = f"""
        SELECT c.id, c.section, c.block, c.text, c.document_id,
               (c.embedding <=> %s::vector({dim})) AS dist
        FROM {chunk_tbl} AS c
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> %s::vector({dim})
        LIMIT %s
        """

    vec_param = [float(x) for x in query_vec.tolist()]

    with connection.cursor() as cur:
        cur.execute(sql, [vec_param, vec_param, int(top_k)])
        rows = cur.fetchall()  

    if not rows:
        return []

    by_id = _inflate_chunks(rows)
    out: List[Tuple[Chunk, float]] = []
    for (cid, _section, _block, _text, _docid, dist) in rows:
        ch = by_id.get(cid)
        if ch:
            sim = 1.0 - float(dist) / 2.0
            out.append((ch, sim))
    return out


# ------------------------ Lexical search (GIN) -------------------------------

def lexical_search(query: str, top_k: Optional[int] = None) -> List[Tuple[Chunk, float]]:
    """
    Búsqueda léxica sobre columna generada `tsv` (config `spanish_unaccent`)
    con índice GIN. Estrategia en 2 etapas:
      1) Filtra candidatos con el índice (rápido).
      2) Rankeado de pocos con ts_rank_cd.
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
        cur.execute(sql, [query, int(cand_cap), query, int(top_k)])
        rows = cur.fetchall()  

    if not rows:
        return []

    ids = [r[0] for r in rows]
    chunks = {
        c.id: c
        for c in (
            Chunk.objects
                 .filter(id__in=ids)
                 .select_related("document")
                 .only("id", "section", "block", "text", "document_id")
        )
    }

    out: List[Tuple[Chunk, float]] = []
    for (cid, rank) in rows:
        ch = chunks.get(cid)
        if ch:
            out.append((ch, float(rank)))
    return out


# ------------------------ RRF fusion -----------------------------------------

def _rrf_score(rank: int, k: float = 60.0) -> float:
    return 1.0 / (k + rank)

def rrf_fuse(
    vec_pairs: List[Tuple[Chunk, float]],
    lex_pairs: List[Tuple[Chunk, float]],
    k_rrf: float = 60.0,
    limit: int = 100
) -> List[Tuple[Chunk, float, Dict[str, float]]]:
    rank_vec: Dict[int, int] = {
        ch.id: i for i, (ch, _) in enumerate(sorted(vec_pairs, key=lambda t: t[1], reverse=True), start=1)
    }
    rank_lex: Dict[int, int] = {
        ch.id: i for i, (ch, _) in enumerate(sorted(lex_pairs, key=lambda t: t[1], reverse=True), start=1)
    }

    by_id: Dict[int, Dict[str, Any]] = {}
    for ch, s in vec_pairs:
        by_id.setdefault(ch.id, {"chunk": ch, "vec": float(s)})
    for ch, s in lex_pairs:
        d = by_id.setdefault(ch.id, {"chunk": ch})
        d["lex"] = float(s)

    fused: List[Tuple[Chunk, float, Dict[str, float]]] = []
    for cid, d in by_id.items():
        rv = rank_vec.get(cid)
        rl = rank_lex.get(cid)
        rrf = ( _rrf_score(rv, k_rrf) if rv else 0.0 ) + ( _rrf_score(rl, k_rrf) if rl else 0.0 )
        fused.append((d["chunk"], rrf, {
            "vec": float(d.get("vec", 0.0)),
            "lex": float(d.get("lex", 0.0)),
        }))

    fused.sort(key=lambda x: x[1], reverse=True)
    return fused[:limit]

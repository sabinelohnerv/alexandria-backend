import time
from typing import Tuple, List, Dict, Any, Optional

from django.db import transaction

from documents.models import Chunk
from ..models import ChatSession, ChatMessage, SearchHit

from .ranking.settings import get_setting
from .ranking.embeddings import encode_query
from .ranking.retrieval import vector_search, lexical_search, rrf_fuse
from .ranking.reranker import rerank_hits
from .ranking.signals import compute_legal_signals, combine_final_score
from .ranking.mmr import mmr_select
from .ranking.synthesis import synthesize_answer


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
    search_top_k = get_setting("SEARCH_TOP_K", 50)
    qvec = encode_query(query)
    vec_pairs = vector_search(qvec, top_k=search_top_k)
    lex_pairs = lexical_search(query, top_k=search_top_k)
    fusion_candidates = get_setting("FUSION_CANDIDATES", 100)
    rrf_scored = rrf_fuse(
        vec_pairs, lex_pairs,
        k_rrf=float(get_setting("RRF_K", 60.0)),
        limit=fusion_candidates
    )
    # rrf_scored: [(chunk, s_rrf, {"vec","lex"})]

    # 2) rerank encima del RRF (prefiltrando candidatos C)
    rerank_candidates = get_setting("RERANK_CANDIDATES", fusion_candidates)
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
    top_n = int(get_setting("RERANK_TOP_N", 12))
    top_for_ui = combined[:top_n]

    # 4) MMR opcional para diversidad visual (sobre TOP_N ya combinado)
    use_mmr = bool(get_setting("ENABLE_MMR", True))
    max_snippets = int(get_setting("MMR_K", 5))
    if use_mmr and top_for_ui:
        # MMR usa como base el score final
        mmr_in = [(ch, s_final, extra) for (ch, _s_base, extra, _s_ce, s_final, _signals) in top_for_ui]
        mmr_selected = mmr_select(mmr_in, qvec, k=max_snippets, lambda_=float(get_setting("MMR_LAMBDA", 0.7)))
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
    from django.db import transaction
    with transaction.atomic():
        msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text=answer["text"],
            answer_json={
                "snippets": answer["snippets"],
                "enable_rerank": bool(get_setting("ENABLE_RERANK", True)),
                "weights": get_setting("RANK_WEIGHTS", {}),
                "org_weights": get_setting("ORG_WEIGHTS", {}),
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

import time
from concurrent.futures import ThreadPoolExecutor
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
from .generation.synthesis import synthesize_answer


def _ms(since: float) -> int:
    return int((time.perf_counter() - since) * 1000)


def ask(user, query: str, session: Optional[ChatSession] = None) -> Tuple[ChatMessage, List[SearchHit]]:
    """
    Flujo:
      1) retrieve (vec + lex, en paralelo) -> RRF (C=FUSION_CANDIDATES)
      2) rerank (cross-encoder) sobre C
      3) combinar señales jurídicas (fórmula) -> ordenar -> quedarnos con TOP_N
      4) (opcional) MMR sobre TOP_N para diversidad visual
      5) síntesis + persistencia
    """
    t0 = time.perf_counter()
    perf: List[str] = []

    # Crear sesión si no viene
    if session is None:
        title = (query[:80] + "…") if len(query) > 80 else query
        session = ChatSession.objects.create(user=user, title=title)

    # Guardar mensaje user (no medimos aquí)
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, text=query)

    # -------- 1) RETRIEVE (paralelo) --------
    t_retrieve = time.perf_counter()

    search_top_k = int(get_setting("SEARCH_TOP_K", 50))
    fusion_candidates = int(get_setting("FUSION_CANDIDATES", 100))
    rrf_k = float(get_setting("RRF_K", 60.0))

    # Embedding de consulta (cacheable si implementas lru_cache en encode_query)
    qvec = encode_query(query)

    # Ejecutar vec + lex en paralelo (ahorra I/O y latencia de DB/ANN)
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_vec = ex.submit(vector_search, qvec, search_top_k)
        fut_lex = ex.submit(lexical_search, query, search_top_k)
        vec_pairs = fut_vec.result()
        lex_pairs = fut_lex.result()

    rrf_scored = rrf_fuse(vec_pairs, lex_pairs, k_rrf=rrf_k, limit=fusion_candidates)
    # rrf_scored: [(chunk, s_rrf, {"vec","lex"})]

    perf.append(f"retrieve={_ms(t_retrieve)}ms")

    # -------- 2) RERANK --------
    t_rerank = time.perf_counter()

    rerank_candidates = int(get_setting("RERANK_CANDIDATES", fusion_candidates))
    reranked = rerank_hits(query, rrf_scored, top_n=rerank_candidates)
    # reranked: [(chunk, s_rrf, {"vec","lex"}, s_ce)]

    perf.append(f"rerank={_ms(t_rerank)}ms")

    # -------- 3) Señales jurídicas + combinación --------
    t_signals = time.perf_counter()

    # Memo de señales por documento para evitar recomputar
    signals_cache: Dict[int, Dict[str, Any]] = {}
    combined: List[Tuple[Chunk, float, Dict[str, float], Optional[float], float, Dict[str, Any]]] = []

    for (ch, s_base, extra, s_ce) in reranked:
        doc_id = ch.document_id
        if doc_id not in signals_cache:
            # compute_legal_signals puede tocar DB: cachea por doc_id
            signals_cache[doc_id] = compute_legal_signals(query, ch.document)
        signals = signals_cache[doc_id]

        ce = float(s_ce if s_ce is not None else s_base)  # si falla CE, usar base (RRF)
        s_final = combine_final_score(ce, signals)
        combined.append((ch, s_base, extra, s_ce, s_final, signals))

    # Ordenar: score final desc, desempate por base (RRF)
    combined.sort(key=lambda t: (t[4], t[1]), reverse=True)

    perf.append(f"signals={_ms(t_signals)}ms")

    # Mantener TOP_N para UI (con posibilidad de degradación suave)
    top_n = int(get_setting("RERANK_TOP_N", 12))
    top_for_ui = combined[:top_n]

    # -------- 4) MMR (opcional) --------
    t_mmr = time.perf_counter()

    use_mmr = bool(get_setting("ENABLE_MMR", True))
    max_snippets = int(get_setting("MMR_K", 5))
    mmr_lambda = float(get_setting("MMR_LAMBDA", 0.7))

    # Degradación suave si retrieve+rerank fueron lentos (recorta para el resto de fases)
    try:
        retrieve_ms = int(perf[0].split("=")[1].rstrip("ms"))  
        rerank_ms = int(perf[1].split("=")[1].rstrip("ms"))    
    except Exception:
        retrieve_ms = rerank_ms = 0

    # Umbrales simples; ajusta según tus métricas reales
    if retrieve_ms > 800 or rerank_ms > 1000:
        # recorta TOP_N y snippets para acelerar MMR + LLM
        top_for_ui = top_for_ui[: max(6, min(len(top_for_ui), top_n // 2))]
        max_snippets = max(3, min(max_snippets, 4))

    if use_mmr and top_for_ui:
        # MMR usa score final como base
        mmr_in = [(ch, s_final, extra) for (ch, _s_base, extra, _s_ce, s_final, _signals) in top_for_ui]
        mmr_selected = mmr_select(mmr_in, qvec, k=max_snippets, lambda_=mmr_lambda)
        # Reinyectar estructuras originales preservando s_final
        id_map = {ch.id: (s_base, extra, s_ce, s_final, signals) for (ch, s_base, extra, s_ce, s_final, signals) in top_for_ui}
        final_hits = []
        for (ch, _score_base, _extra) in mmr_selected:
            s_base, extra, s_ce, s_final, signals = id_map[ch.id]
            final_hits.append((ch, s_base, extra, s_ce, s_final, signals))
    else:
        final_hits = top_for_ui[:max_snippets]

    perf.append(f"mmr={_ms(t_mmr)}ms")

    # -------- 5) Síntesis LLM --------
    t_llm = time.perf_counter()

    answer = synthesize_answer(query, final_hits, max_snippets=max_snippets)

    perf.append(f"llm={_ms(t_llm)}ms")
    latency_ms = _ms(t0)
    perf.append(f"total={latency_ms}ms")

    # -------- Persistencia --------
    with transaction.atomic():
        msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text=answer.get("text", "") or "",
            answer_json={
                "snippets": answer.get("snippets", []),
                "enable_rerank": bool(get_setting("ENABLE_RERANK", True)),
                "weights": get_setting("RANK_WEIGHTS", {}),
                "org_weights": get_setting("ORG_WEIGHTS", {}),
                "perf": perf,
            },
            latency_ms=latency_ms,
        )

        # Guardar todos los resultados combinados (TOP_N original recortado si aplicó degradación)
        hits: List[SearchHit] = []
        for i, (ch, s_base, extra, s_ce, s_final, signals) in enumerate(top_for_ui, start=1):
            kwargs = dict(
                message=msg,
                document=ch.document,
                chunk=ch,
                rank=i,
                score_vector=float(extra.get("vec", 0.0)),
                score_lexical=float(extra.get("lex", 0.0)) if extra.get("lex") is not None else None,
                meta_json={
                    "section": getattr(ch, "section", None),
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
            if hasattr(SearchHit, "score_lexical") and extra.get("lex") is not None:
                kwargs["score_lexical"] = float(extra.get("lex", 0.0))

            hits.append(SearchHit(**kwargs))
        SearchHit.objects.bulk_create(hits, batch_size=500)

    return msg, hits

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple, List, Dict, Any, Optional, Sequence

from django.db import transaction

from apps.documents.models import Chunk
from ..models import ChatSession, ChatMessage, SearchHit

from .ranking.settings import get_setting
from .ranking.embeddings import encode_query
from .ranking.retrieval import vector_search, lexical_search, rrf_fuse
from .ranking.reranker import rerank_hits
from .ranking.signals import compute_legal_signals, SIGNAL_ORDER, signals_to_vector
from .ranking.adaptive import get_active_signal_weights, get_alpha_ce
from .ranking.mmr import mmr_select
from .generation.synthesis import synthesize_answer


def _ms(since: float) -> int:
    return int((time.perf_counter() - since) * 1000)


def _score_with_weights(s_ce: float, signals: Dict[str, Any],
                        w: Sequence[float], alpha: float) -> float:
    x = signals_to_vector(signals)  # orden SIGNAL_ORDER
    # s_ce ya viene normalizado del reranker; señales en [0,1]
    return alpha * float(s_ce) + sum((wi or 0.0) * xi for wi, xi in zip(w, x))


def ask(user, query: str, session: Optional[ChatSession] = None) -> Tuple[ChatMessage, List[SearchHit]]:
    """
    Flujo:
      1) retrieve (vec + lex, en paralelo) -> RRF (C=FUSION_CANDIDATES)
      2) rerank (cross-encoder) sobre C (devuelve s_ce normalizado)
      3) combinar señales con PESOS ACTIVOS -> ordenar -> TOP_N
      4) (opcional) MMR sobre TOP_N para diversidad
      5) síntesis + persistencia
    """
    t0 = time.perf_counter()
    
    # Diccionario para almacenar tiempos de cada fase
    timings = {}

    # 0) Sesión y mensaje del usuario
    t_setup = time.perf_counter()
    if session is None:
        title = (query[:80] + "…") if len(query) > 80 else query
        session = ChatSession.objects.create(user=user, title=title)
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, text=query)

    # === Pesos activos y alpha (sin A/B) ===
    alpha = get_alpha_ce()
    w_active = get_active_signal_weights()
    model_version_used = "active"
    experiment_bucket = "control"  # etiqueta fija para compatibilidad
    timings["setup_ms"] = _ms(t_setup)

    # -------- 1) RETRIEVE (paralelo) --------
    t_retrieve = time.perf_counter()

    search_top_k = int(get_setting("SEARCH_TOP_K", 50))
    fusion_candidates = int(get_setting("FUSION_CANDIDATES", 100))
    rrf_k = float(get_setting("RRF_K", 60.0))

    # Embedding de consulta
    t_emb = time.perf_counter()
    qvec = encode_query(query)
    timings["embedding_ms"] = _ms(t_emb)

    # Ejecutar vec + lex en paralelo
    t_search = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_vec = ex.submit(vector_search, qvec, search_top_k)
        fut_lex = ex.submit(lexical_search, query, search_top_k)
        vec_pairs = fut_vec.result()
        lex_pairs = fut_lex.result()
    timings["search_ms"] = _ms(t_search)

    t_rrf = time.perf_counter()
    rrf_scored = rrf_fuse(vec_pairs, lex_pairs, k_rrf=rrf_k, limit=fusion_candidates)
    timings["rrf_fusion_ms"] = _ms(t_rrf)

    # rank_before según RRF (antes de CE y señales)
    rank_before_map = {ch.id: (idx + 1) for idx, (ch, _s, _e) in enumerate(rrf_scored)}

    timings["retrieve_total_ms"] = _ms(t_retrieve)

    # -------- 2) RERANK --------
    t_rerank = time.perf_counter()

    rerank_candidates = int(get_setting("RERANK_CANDIDATES", fusion_candidates))
    # Espera tuplas: (ch, s_base, extra, s_ce_norm, s_final_rer, signals)
    reranked_full = rerank_hits(query, rrf_scored, top_n=rerank_candidates)

    timings["rerank_ms"] = _ms(t_rerank)

    # -------- 3) Señales + combinación con PESOS ACTIVOS --------
    t_signals = time.perf_counter()
    combined: List[
        Tuple[Chunk, float, Dict[str, float], Optional[float], float, Dict[str, Any]]
    ] = []

    for tpl in reranked_full:
        ch, s_base, extra, s_ce_norm, _s_final_rer, signals = tpl

        # CE normalizado; fallback al score base si no hay CE
        if s_ce_norm is None:
            ce_for_formula = float(max(0.0, min(1.0, s_base)))
        else:
            ce_for_formula = float(s_ce_norm)

        s_final = _score_with_weights(ce_for_formula, signals, w_active, alpha)
        combined.append((ch, s_base, extra, s_ce_norm, s_final, signals))

    # Ordenar por score final (desc), desempate por RRF base
    combined.sort(key=lambda t: (t[4], t[1]), reverse=True)

    # TOP_N para UI
    top_n = int(get_setting("RERANK_TOP_N", 12))
    top_for_ui = combined[:top_n]
    timings["signals_scoring_ms"] = _ms(t_signals)

    # -------- 4) MMR (opcional) --------
    t_mmr = time.perf_counter()

    use_mmr = bool(get_setting("ENABLE_MMR", True))
    max_snippets = int(get_setting("MMR_K", 5))
    mmr_lambda = float(get_setting("MMR_LAMBDA", 0.7))

    # Degradación suave si retrieve+rerank fueron lentos
    if timings["retrieve_total_ms"] > 800 or timings["rerank_ms"] > 1000:
        top_for_ui = top_for_ui[: max(6, min(len(top_for_ui), top_n // 2))]
        max_snippets = max(3, min(max_snippets, 4))

    if use_mmr and top_for_ui:
        # MMR usa score final como base
        mmr_in = [(ch, s_final, extra) for (ch, _s_base, extra, _s_ce, s_final, _signals) in top_for_ui]
        mmr_selected = mmr_select(mmr_in, qvec, k=max_snippets, lambda_=mmr_lambda)
        # Reinyectar estructuras originales
        id_map = {
            ch.id: (s_base, extra, s_ce_norm, s_final, signals)
            for (ch, s_base, extra, s_ce_norm, s_final, signals) in top_for_ui
        }
        final_hits = []
        for (ch, _score_base, _extra) in mmr_selected:
            s_base, extra, s_ce_norm, s_final, signals = id_map[ch.id]
            final_hits.append((ch, s_base, extra, s_ce_norm, s_final, signals))
    else:
        final_hits = top_for_ui[:max_snippets]

    timings["mmr_ms"] = _ms(t_mmr)

    # -------- 5) Síntesis LLM --------
    t_llm = time.perf_counter()

    # synthesis.py espera 6-tuplas: (ch, s_base, extra, s_ce, s_final, signals)
    final_hits_for_synth = final_hits
    answer = synthesize_answer(query, final_hits_for_synth, max_snippets=max_snippets)

    timings["llm_synthesis_ms"] = _ms(t_llm)
    timings["total_ms"] = _ms(t0)

    # -------- Persistencia --------
    t_persist = time.perf_counter()
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
                "timings": timings,
                "experiment_bucket": experiment_bucket,   # fijo "control"
                "weights_version_used": model_version_used,  # "active"
                "rerank_score_mode": str(get_setting("RERANK_SCORE_MODE", "sigmoid_minmax")),
            },
            latency_ms=timings["total_ms"],
        )

        # Guardar resultados mostrados
        hits: List[SearchHit] = []
        for i, (ch, s_base, extra, s_ce_norm, s_final, signals) in enumerate(final_hits, start=1):
            meta = {
                "section": getattr(ch, "section", None),
                "lex": float(extra.get("lex", 0.0)) if extra.get("lex") is not None else 0.0,
                "base_rrf": float(s_base),
                "rerank_ce": (float(s_ce_norm) if s_ce_norm is not None else None),   # CE normalizado
                "rerank_ce_raw": (float(extra.get("ce_raw")) if extra.get("ce_raw") is not None else None),
                "final_score": float(s_final) if (s_final is not None) else 0.0,
                "signals": {
                    "vigente": bool(signals.get("vigente")),
                    "peso_org": float(signals.get("peso_org", 0.0)),
                    "match_id": bool(signals.get("match_id")),
                    "recencia": float(signals.get("recencia", 0.0)),
                },
                "experiment_bucket": experiment_bucket,
                "weights_version_used": model_version_used,
            }

            # Sanea final_score ante NaN
            try:
                if meta["final_score"] != meta["final_score"]:
                    meta["final_score"] = 0.0
            except Exception:
                meta["final_score"] = 0.0

            kwargs = dict(
                message=msg,
                document=ch.document,
                chunk=ch,
                rank=i,
                score_vector=float(extra.get("vec", 0.0)),
                score_lexical=float(extra.get("lex", 0.0)) if extra.get("lex") is not None else None,
                meta_json=meta,
            )
            if hasattr(SearchHit, "score_rerank"):
                kwargs["score_rerank"] = (float(s_ce_norm) if s_ce_norm is not None else None)
            if hasattr(SearchHit, "score_lexical") and extra.get("lex") is not None:
                kwargs["score_lexical"] = float(extra.get("lex", 0.0))

            hits.append(SearchHit(**kwargs))
        SearchHit.objects.bulk_create(hits, batch_size=500)

        # Logging de decisiones (modo control-only)
        try:
            from apps.ranking_adaptive.models import RankingDecision
        except Exception:
            RankingDecision = None

        if RankingDecision is not None:
            decisions = []
            for shown_pos, (ch, _s_base, _extra, s_ce_norm, _s_final, signals) in enumerate(final_hits, start=1):
                rb = rank_before_map.get(ch.id, shown_pos)
                sig_vec = signals_to_vector(signals)
                decisions.append(RankingDecision(
                    query_id=msg.id,
                    message_id=msg.id,
                    hit_id=ch.id,
                    model_version=model_version_used,  # "active"
                    score_ce=(float(s_ce_norm) if s_ce_norm is not None else 0.0),
                    rank_before=rb,
                    rank_after=shown_pos,
                    shown_pos=shown_pos,
                    signals=sig_vec,
                    signal_names=SIGNAL_ORDER,
                ))
            if decisions:
                from django.db import IntegrityError
                try:
                    RankingDecision.objects.bulk_create(decisions, batch_size=500)
                except IntegrityError:
                    pass
    
    timings["persistence_ms"] = _ms(t_persist)

    return msg, hits

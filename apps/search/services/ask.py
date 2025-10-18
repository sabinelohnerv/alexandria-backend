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

def _assign_bucket(query_id: int) -> str:
    h = query_id % 10
    if h == 0:  # 10% shadow
        return "shadow"
    if h in (1, 2):  # 20% treatment
        return "treatment"
    return "control"

def _get_candidate_weights_or_none():
    """Devuelve (version, weights) de la última versión INACTIVA, o (None, None)."""
    try:
        from apps.ranking_adaptive.models import RankingWeights
        cand = RankingWeights.objects.filter(is_active=False).order_by('-created_at').first()
        return (cand.version, cand.weights) if cand else (None, None)
    except Exception:
        return (None, None)

def _score_with_weights(s_ce: float, signals: Dict[str, Any],
                        w: Sequence[float], alpha: float) -> float:
    x = signals_to_vector(signals)  # en el orden SIGNAL_ORDER
    return alpha * float(s_ce) + sum((wi or 0.0) * xi for wi, xi in zip(w, x))


def ask(user, query: str, session: Optional[ChatSession] = None) -> Tuple[ChatMessage, List[SearchHit]]:
    """
    Flujo:
      1) retrieve (vec + lex, en paralelo) -> RRF (C=FUSION_CANDIDATES)
      2) rerank (cross-encoder TEI) sobre C
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

    # -------- A/B: bucket y selección de pesos --------
    bucket = _assign_bucket((session.id or 0))
    alpha = get_alpha_ce()
    w_active = get_active_signal_weights()
    w_to_use = w_active
    model_version_used = "active"

    cand_version, cand_w = _get_candidate_weights_or_none()
    if bucket == "treatment" and cand_w:
        w_to_use = cand_w
        model_version_used = cand_version or "candidate"

    # Log de asignación de experimento (best-effort)
    try:
        from apps.ranking_adaptive.models import ExperimentAssignment
        ExperimentAssignment.objects.update_or_create(
            query_id=session.id,
            defaults={
                "bucket": bucket,
                "weights_version": (
                    (cand_version or "candidate") if bucket in ("treatment", "shadow") else "active"
                ),
            },
        )
    except Exception:
        pass

    # -------- 1) RETRIEVE (paralelo) --------
    t_retrieve = time.perf_counter()

    search_top_k = int(get_setting("SEARCH_TOP_K", 50))
    fusion_candidates = int(get_setting("FUSION_CANDIDATES", 100))
    rrf_k = float(get_setting("RRF_K", 60.0))

    # Embedding de consulta
    qvec = encode_query(query)

    # Ejecutar vec + lex en paralelo
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_vec = ex.submit(vector_search, qvec, search_top_k)
        fut_lex = ex.submit(lexical_search, query, search_top_k)
        vec_pairs = fut_vec.result()
        lex_pairs = fut_lex.result()

    rrf_scored = rrf_fuse(vec_pairs, lex_pairs, k_rrf=rrf_k, limit=fusion_candidates)
    # rank_before según RRF (antes de CE y señales)
    rank_before_map = {ch.id: (idx + 1) for idx, (ch, _s, _e) in enumerate(rrf_scored)}

    perf.append(f"retrieve={_ms(t_retrieve)}ms")

    # -------- 2) RERANK (TEI) --------
    t_rerank = time.perf_counter()

    rerank_candidates = int(get_setting("RERANK_CANDIDATES", fusion_candidates))
    # rerank_hits devuelve: (chunk, s_base, extra, s_ce, s_final, signals_dict)
    reranked_full = rerank_hits(query, rrf_scored, top_n=rerank_candidates)

    perf.append(f"rerank={_ms(t_rerank)}ms")

    # -------- 3) Señales jurídicas + combinación --------
    t_signals = time.perf_counter()

    # Memo de señales por documento para evitar recomputar
    signals_cache: Dict[int, Dict[str, Any]] = {}
    combined: List[
        Tuple[Chunk, float, Dict[str, float], Optional[float], float, Dict[str, Any], Optional[float]]
    ] = []

    for tpl in reranked_full:
        # Soporta tanto 4-tupla (legacy) como 6-tupla (actual)
        ch, s_base, extra = tpl[0], tpl[1], tpl[2]
        s_ce = tpl[3] if len(tpl) >= 4 else None
        sigs_from_reranker = tpl[5] if len(tpl) >= 6 else None

        doc_id = ch.document_id
        if doc_id not in signals_cache:
            if sigs_from_reranker and isinstance(sigs_from_reranker, dict):
                # Reusa señales calculadas en reranker.py (evita DB hit)
                signals_cache[doc_id] = sigs_from_reranker
            else:
                # Calcula señales si no vinieron del reranker (compat)
                signals_cache[doc_id] = compute_legal_signals(query, ch.document)

        signals = signals_cache[doc_id]
        # Si el CE falló, usamos el score base (RRF) como sustituto para la fórmula
        ce_for_formula = float(s_ce if s_ce is not None else s_base)

        if bucket == "shadow" and cand_w:
            s_final_active = _score_with_weights(ce_for_formula, signals, w_active, alpha)
            s_final_cand = _score_with_weights(ce_for_formula, signals, cand_w, alpha)
            combined.append((ch, s_base, extra, s_ce, s_final_active, signals, s_final_cand))
        else:
            s_final = _score_with_weights(ce_for_formula, signals, w_to_use, alpha)
            combined.append((ch, s_base, extra, s_ce, s_final, signals, None))

    # Ordenar: score final desc, desempate por base (RRF)
    combined.sort(key=lambda t: (t[4], t[1]), reverse=True)

    perf.append(f"signals={_ms(t_signals)}ms")

    # Mantener TOP_N para UI
    top_n = int(get_setting("RERANK_TOP_N", 12))
    top_for_ui = combined[:top_n]

    # -------- 4) MMR (opcional) --------
    t_mmr = time.perf_counter()

    use_mmr = bool(get_setting("ENABLE_MMR", True))
    max_snippets = int(get_setting("MMR_K", 5))
    mmr_lambda = float(get_setting("MMR_LAMBDA", 0.7))

    # Degradación suave si retrieve+rerank fueron lentos
    try:
        retrieve_ms = int(perf[0].split("=")[1].rstrip("ms"))
        rerank_ms   = int(perf[1].split("=")[1].rstrip("ms"))
    except Exception:
        retrieve_ms = rerank_ms = 0

    if retrieve_ms > 800 or rerank_ms > 1000:
        top_for_ui   = top_for_ui[: max(6, min(len(top_for_ui), top_n // 2))]
        max_snippets = max(3, min(max_snippets, 4))

    if use_mmr and top_for_ui:
        # MMR usa score final como base (columna 4 de nuestras tuplas)
        mmr_in = [(ch, s_final, extra) for (ch, _s_base, extra, _s_ce, s_final, _signals, _s_shadow) in top_for_ui]
        mmr_selected = mmr_select(mmr_in, qvec, k=max_snippets, lambda_=mmr_lambda)
        # Reinyectar estructuras originales preservando s_final y s_final_shadow
        id_map = {
            ch.id: (s_base, extra, s_ce, s_final, signals, s_shadow)
            for (ch, s_base, extra, s_ce, s_final, signals, s_shadow) in top_for_ui
        }
        final_hits = []
        for (ch, _score_base, _extra) in mmr_selected:
            s_base, extra, s_ce, s_final, signals, s_shadow = id_map[ch.id]
            final_hits.append((ch, s_base, extra, s_ce, s_final, signals, s_shadow))
    else:
        final_hits = top_for_ui[:max_snippets]

    perf.append(f"mmr={_ms(t_mmr)}ms")

    # -------- 5) Síntesis LLM --------
    t_llm = time.perf_counter()

    # synthesis.py espera 6-tuplas: (ch, s_base, extra, s_ce, s_final, signals)
    final_hits_for_synth = [
        (ch, s_base, extra, s_ce, s_final, signals)
        for (ch, s_base, extra, s_ce, s_final, signals, _s_shadow) in final_hits
    ]
    answer = synthesize_answer(query, final_hits_for_synth, max_snippets=max_snippets)

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
                "experiment_bucket": bucket,
                "weights_version_used": model_version_used,
            },
            latency_ms=latency_ms,
        )

        # Guardar todos los resultados combinados (lo que mostrará la UI)
        hits: List[SearchHit] = []
        for i, (ch, s_base, extra, s_ce, s_final, signals, s_shadow) in enumerate(final_hits, start=1):
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
                    "final_score_shadow": (float(s_shadow) if s_shadow is not None else None),
                    "signals": {
                        "vigente": bool(signals.get("vigente")),
                        "peso_org": float(signals.get("peso_org", 0.0)),
                        "match_id": bool(signals.get("match_id")),
                        "recencia": float(signals.get("recencia", 0.0)),
                    },
                    "experiment_bucket": bucket,
                    "weights_version_used": model_version_used,
                },
            )
            if hasattr(SearchHit, "score_rerank"):
                kwargs["score_rerank"] = (float(s_ce) if s_ce is not None else None)
            if hasattr(SearchHit, "score_lexical") and extra.get("lex") is not None:
                kwargs["score_lexical"] = float(extra.get("lex", 0.0))

            hits.append(SearchHit(**kwargs))
        SearchHit.objects.bulk_create(hits, batch_size=500)

        # ===== Logging de decisiones para adaptive =====
        try:
            from apps.ranking_adaptive.models import RankingDecision
        except Exception:
            RankingDecision = None

        if RankingDecision is not None:
            decisions = []
            for shown_pos, (ch, s_base, _extra, s_ce, s_final, signals, _s_shadow) in enumerate(final_hits, start=1):
                rb = rank_before_map.get(ch.id, shown_pos)
                sig_vec = signals_to_vector(signals)
                mv = (
                    (f"shadow:{cand_version or 'candidate'}")
                    if bucket == "shadow" and cand_version
                    else model_version_used
                )
                decisions.append(RankingDecision(
                    query_id=msg.id,
                    message_id=msg.id,
                    hit_id=ch.id,
                    model_version=mv,
                    score_ce=(float(s_ce) if s_ce is not None else 0.0),
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

    return msg, hits
import os
from typing import List, Tuple, Dict, Optional
from documents.models import Chunk
from .settings import get_setting
from .cache import key_pair
from .signals import compute_legal_signals, combine_final_score_vector

_RERANKER = None
_RERANKER_READY = None  # tri-state: None (unknown), True, False

# caché simple en proceso: key->float
_CE_SCORE_CACHE: Dict[str, float] = {}
_CE_CACHE_MAX = 20000  


def _get_reranker():
    global _RERANKER, _RERANKER_READY
    if _RERANKER_READY is True:
        return _RERANKER
    if _RERANKER_READY is False:
        return None
    try:
        os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from sentence_transformers import CrossEncoder
        model_name = get_setting("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
        _RERANKER = CrossEncoder(model_name, trust_remote_code=True)
        _RERANKER._target_device  # ensures device placement
        _RERANKER_READY = True
        return _RERANKER
    except Exception:
        _RERANKER = None
        _RERANKER_READY = False
        return None

def _doc_from_chunk(ch: Chunk):
    try:
        return ch.document
    except Exception:
        return None

def rerank_hits(query: str,
                candidates: List[Tuple[Chunk, float, Dict[str, float]]],
                top_n: Optional[int] = None
               ) -> List[Tuple[Chunk, float, Dict[str, float], Optional[float], float, dict]]:
    """
    Entrada: [(chunk, score_base, {"vec","lex"})]
    Salida:  [(chunk, score_base, {"vec","lex"}, score_ce, score_final, signals_dict)]
             - score_ce puede ser None si no hubo rerank
             - score_final combina CE + señales jurídicas
    """
    if top_n is None:
        top_n = get_setting("RERANK_CANDIDATES", 100)

    if not get_setting("ENABLE_RERANK", True) or not candidates:
        trimmed = candidates[:top_n]
        out = []
        for (ch, s, extra) in trimmed:
            doc = _doc_from_chunk(ch)
            sig = compute_legal_signals(query, getattr(doc, 'document', doc) or doc) if doc else {}
            s_ce = None
            s_final = combine_final_score_vector(s_ce or 0.0, sig)
            out.append((ch, s, extra, s_ce, s_final, sig))
        # Ordena por score_final si quieres asegurar ranking estable
        out.sort(key=lambda t: t[4], reverse=True)
        return out

    model = _get_reranker()
    if model is None:
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

    # --- CE como ya lo tienes (caché, predict, etc.) ---
    pairs, need_pred_idx = [], []
    scores_out: List[Optional[float]] = [None] * len(cand_trim)
    for i, (ch, _s, _extra) in enumerate(cand_trim):
        updated = getattr(ch, "updated_at", None)
        k = key_pair(query, ch.id, updated, len(ch.text or ""))
        sc = _CE_SCORE_CACHE.get(k)
        if sc is None:
            need_pred_idx.append(i)
            pairs.append((query, ch.text or ""))
        else:
            scores_out[i] = sc

    if need_pred_idx:
        batch_size = get_setting("RERANK_BATCH_SIZE", 16)
        try:
            new_scores = model.predict(pairs, batch_size=batch_size, show_progress_bar=False).tolist()
        except Exception:
            # falla CE → vuelve sin score pero con señales
            out = []
            for (ch, s, extra) in cand_trim:
                doc = _doc_from_chunk(ch)
                sig = compute_legal_signals(query, getattr(doc, 'document', doc) or doc) if doc else {}
                s_ce = None
                s_final = combine_final_score_vector(0.0, sig)
                out.append((ch, s, extra, s_ce, s_final, sig))
            out.sort(key=lambda t: t[4], reverse=True)
            return out

        for j, i in enumerate(need_pred_idx):
            ch = cand_trim[i][0]
            updated = getattr(ch, "updated_at", None)
            k = key_pair(query, ch.id, updated, len(ch.text or ""))
            val = float(new_scores[j])
            scores_out[i] = val
            if len(_CE_SCORE_CACHE) >= _CE_CACHE_MAX:
                _CE_SCORE_CACHE.pop(next(iter(_CE_SCORE_CACHE)))
            _CE_SCORE_CACHE[k] = val

    # --- Combina CE + señales jurídicas ---
    enriched = []
    for (tpl, sc) in zip(cand_trim, scores_out):
        ch, s_base, extra = tpl
        doc = _doc_from_chunk(ch)
        sig = compute_legal_signals(query, getattr(doc, 'document', doc) or doc) if doc else {}
        s_ce = (None if sc is None else float(sc))
        s_final = combine_final_score_vector(s_ce or 0.0, sig)
        enriched.append((ch, s_base, extra, s_ce, s_final, sig))

    # Orden final por score_final
    enriched.sort(key=lambda t: t[4], reverse=True)
    return enriched
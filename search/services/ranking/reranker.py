import os
from typing import List, Tuple, Dict, Optional
from documents.models import Chunk
from .settings import get_setting

_RERANKER = None
_RERANKER_READY = None  # tri-state: None (unknown), True, False


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
        _RERANKER_READY = True
        return _RERANKER
    except Exception:
        _RERANKER = None
        _RERANKER_READY = False
        return None


def rerank_hits(query: str,
                candidates: List[Tuple[Chunk, float, Dict[str, float]]],
                top_n: Optional[int] = None) -> List[Tuple[Chunk, float, Dict[str, float], Optional[float]]]:
    """
    Entrada: [(chunk, score_base, {"vec","lex"})]
    Salida:  [(chunk, score_base, {"vec","lex"}, score_rerank)]
    """
    if top_n is None:
        top_n = get_setting("RERANK_CANDIDATES", 100)

    if not get_setting("ENABLE_RERANK", True) or not candidates:
        trimmed = candidates[:top_n]
        return [(ch, s, extra, None) for (ch, s, extra) in trimmed]

    model = _get_reranker()
    if model is None:
        trimmed = candidates[:top_n]
        return [(ch, s, extra, None) for (ch, s, extra) in trimmed]

    pairs = [(query, ch.text or "") for (ch, _s, _extra) in candidates[:top_n]]
    batch_size = get_setting("RERANK_BATCH_SIZE", 16)

    try:
        scores = model.predict(pairs, batch_size=batch_size, show_progress_bar=False).tolist()
    except Exception:
        trimmed = candidates[:top_n]
        return [(ch, s, extra, None) for (ch, s, extra) in trimmed]

    enriched = [(ch, s, extra, float(sc)) for (ch, s, extra), sc in zip(candidates[:top_n], scores)]
    return enriched

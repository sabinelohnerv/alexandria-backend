import os
import inspect
import numpy as np
from functools import lru_cache
from .settings import get_setting

_EMBED_MODEL = None

def _get_embedder():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from sentence_transformers import SentenceTransformer
        name = os.getenv("EMBEDDINGS_MODEL", get_setting("EMBEDDINGS_MODEL", "BAAI/bge-m3"))
        _EMBED_MODEL = SentenceTransformer(name)
    return _EMBED_MODEL

@lru_cache(maxsize=512)
def _encode_query_cached(text: str) -> bytes:
    model = _get_embedder()
    kwargs = dict(normalize_embeddings=True, convert_to_numpy=True, batch_size=1)
    try:
        if "prompt_name" in inspect.signature(model.encode).parameters and getattr(model, "prompts", None):
            if "query" in model.prompts:
                kwargs["prompt_name"] = "query"
    except (ValueError, TypeError):
        pass
    vec = model.encode([text], **kwargs)[0]
    return vec.tobytes()  

def encode_query(text: str) -> np.ndarray:
    return np.frombuffer(_encode_query_cached(text), dtype=np.float32)

def warmup_models():
    try:
        _ = encode_query("warmup")
    except Exception:
        pass

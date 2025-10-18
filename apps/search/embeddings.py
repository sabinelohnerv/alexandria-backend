import os
import threading
from sentence_transformers import SentenceTransformer

_MODEL = None
_LOCK = threading.Lock()

def get_query_model():
    global _MODEL
    if _MODEL is None:
        with _LOCK:
            if _MODEL is None:
                os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")
                os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
                name = os.getenv("EMBEDDINGS_MODEL", "BAAI/bge-m3")
                _MODEL = SentenceTransformer(name)
    return _MODEL

def warmup():
    try:
        m = get_query_model()
        m.encode(["ok"], batch_size=1, normalize_embeddings=True, convert_to_numpy=True)
    except Exception:
        pass

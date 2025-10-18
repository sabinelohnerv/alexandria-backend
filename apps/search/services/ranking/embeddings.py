import os
from functools import lru_cache
from typing import Sequence

import numpy as np
from common.clients.tei_embed import tei_embed

@lru_cache(maxsize=512)
def _encode_query_cached(text: str) -> bytes:
    vec = tei_embed([text])[0]     
    return vec.astype(np.float32, copy=False).tobytes()

def encode_query(text: str) -> np.ndarray:
    return np.frombuffer(_encode_query_cached(text), dtype=np.float32)

def encode_texts(texts: Sequence[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, 0), dtype=np.float32)
    return tei_embed(list(texts))

def warmup_models():
    _ = tei_embed(["warmup-emb"])

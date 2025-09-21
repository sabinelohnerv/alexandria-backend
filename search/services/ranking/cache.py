from functools import lru_cache
from typing import Tuple
import hashlib

def _h(s: str) -> str:
    return hashlib.blake2b(s.encode("utf-8"), digest_size=16).hexdigest()

def key_pair(query: str, chunk_id: int, chunk_updated_at, text_len: int) -> str:
    """
    Clave estable para cachear scores de cross-encoder.
    chunk_updated_at: datetime para invalidar si el chunk cambia.
    """
    base = f"{query}::{chunk_id}::{chunk_updated_at and chunk_updated_at.isoformat()}::{text_len}"
    return _h(base)

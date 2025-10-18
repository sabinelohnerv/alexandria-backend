import os
from typing import Optional
from openai import OpenAI

_TOGETHER_BASE_URL = os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz/v1")

_client: Optional[OpenAI] = None

def together_client() -> OpenAI:
    """
    Crea (una vez) y devuelve un cliente apuntando a Together.
    Requiere TOGETHER_API_KEY en entorno.
    """
    global _client
    if _client is None:
        api_key = os.getenv("TOGETHER_API_KEY")
        if not api_key:
            raise RuntimeError("Falta TOGETHER_API_KEY en variables de entorno.")
        _client = OpenAI(api_key=api_key, base_url=_TOGETHER_BASE_URL)
    return _client

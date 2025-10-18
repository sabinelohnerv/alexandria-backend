import os
import math
from typing import Any, Dict, List, Tuple

from .client import together_client
from ..ranking.settings import get_setting
from .prompt import build_messages

def _truncate_snippets(final_hits: List[Tuple[Any, float, dict, float, float, dict]], max_snippets: int) -> List[Dict[str, Any]]:
    """
    Convierte tus 'final_hits' a una lista de diccionarios serializables y limita a max_snippets.
    Cada item de final_hits: (chunk, s_base, extra, s_ce, s_final, signals)
    """
    out: List[Dict[str, Any]] = []
    for (ch, _s_base, extra, s_ce, s_final, _signals) in final_hits[:max_snippets]:
        out.append({
            "chunk_id": ch.id,
            "doc_id": ch.document_id,
            "title": getattr(ch.document, "title", "") if hasattr(ch, "document") else "",
            "section": getattr(ch, "section", None),
            "text": getattr(ch, "text", "") or getattr(ch, "content", "") or "",
            "scores": {
                "vec": float(extra.get("vec", 0.0)),
                "lex": float(extra.get("lex", 0.0)) if extra.get("lex") is not None else 0.0,
                "rerank_ce": (float(s_ce) if s_ce is not None else None),
                "final": float(s_final),
            }
        })
    return out

def synthesize_answer(query: str, final_hits: List[Tuple[Any, float, dict, float, float, dict]], max_snippets: int = 5) -> Dict[str, Any]:
    """
    Construye el prompt con snippets y llama al modelo en Together (vía cliente OpenAI).
    Retorna {"text": <respuesta>, "snippets": <lista_serializable_para_guardar>} 
    """
    # 1) Selección de snippets
    snippets = _truncate_snippets(final_hits, max_snippets=max_snippets)

    # 2) Parámetros del modelo
    model = os.getenv("TOGETHER_MODEL", str(get_setting("TOGETHER_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo")))
    max_tokens = int(os.getenv("TOGETHER_MAX_TOKENS", str(get_setting("TOGETHER_MAX_TOKENS", 768))))
    temperature = float(os.getenv("TOGETHER_TEMPERATURE", str(get_setting("TOGETHER_TEMPERATURE", 0.2))))
    top_p = float(os.getenv("TOGETHER_TOP_P", str(get_setting("TOGETHER_TOP_P", 1.0))))
    freq_pen = float(os.getenv("TOGETHER_FREQUENCY_PENALTY", str(get_setting("TOGETHER_FREQUENCY_PENALTY", 0.0))))
    pres_pen = float(os.getenv("TOGETHER_PRESENCE_PENALTY", str(get_setting("TOGETHER_PRESENCE_PENALTY", 0.0))))

    # 3) Mensajes estilo Chat
    messages = build_messages(query, snippets)

    # 4) Llamada a Together (Chat Completions)
    client = together_client()

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            frequency_penalty=freq_pen,
            presence_penalty=pres_pen,
        )
        text = (completion.choices[0].message.content or "").strip()
    except Exception as e:
        # Fallback simple para no romper el flujo de ask()
        text = (
            "No fue posible generar una respuesta con el modelo de lenguaje en este momento. "
            f"Detalle técnico: {e}"
        )

    return {
        "text": text,
        "snippets": snippets,
    }

from typing import List, Dict, Any

SYSTEM_PROMPT = (
    "Eres un asistente jurídico conciso y factual para el contexto boliviano. "
    "Usa únicamente la evidencia proporcionada en los fragmentos (snippets). "
    "Cita con [doc_id:chunk_id] después de cada afirmación clave. "
    "Si no hay soporte, di explícitamente que falta evidencia. Evita alucinar."
)

def build_messages(query: str, snippets: List[Dict[str, Any]]) -> list:
    """
    Construye mensajes estilo Chat para un modelo instruct. 
    snippets: lista de dicts con {"chunk_id","doc_id","title","section","text"}.
    """
    # Empaquetamos contexto como un 'document' para delimitar claramente la evidencia
    context_lines = []
    for sn in snippets:
        ctx_title = sn.get("title") or ""
        ctx_sec = sn.get("section") or ""
        ctx_text = (sn.get("text") or "").strip()
        ctx_doc = sn.get("doc_id")
        ctx_chunk = sn.get("chunk_id")
        header = f"[{ctx_doc}:{ctx_chunk}] {ctx_title} — {ctx_sec}".strip(" —")
        context_lines.append(f"{header}\n{ctx_text}")

    context_block = "\n\n---\n\n".join(context_lines) if context_lines else "(sin evidencia disponible)"

    user_prompt = (
        f"Pregunta del usuario:\n{query}\n\n"
        f"Contexto (snippets):\n{context_block}\n\n"
        "Instrucciones:\n"
        "- Responde en español, con tono claro y profesional.\n"
        "- Prioriza normas vigentes y jurisprudencia aplicable.\n"
        "- Incluye citas en línea con el formato [doc_id:chunk_id].\n"
        "- Si hay ambigüedad normativa o contradicciones, explícalas brevemente.\n"
        "- Termina con una sección 'Fuentes' listando los ids citados.\n"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    return messages

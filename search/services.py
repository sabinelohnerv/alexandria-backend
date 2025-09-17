import os
import time
import inspect
from typing import List, Tuple, Dict, Any

import numpy as np
from django.conf import settings
from django.db import transaction
from pgvector.django import CosineDistance

from documents.models import Chunk, Document
from .models import ChatSession, ChatMessage, SearchHit

# Cache de modelo global (como en Celery)
_EMBED_MODEL = None

def _get_embedder():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        # Evita torchvision
        os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from sentence_transformers import SentenceTransformer
        name = os.getenv("EMBEDDINGS_MODEL", getattr(settings, "EMBEDDINGS_MODEL", "BAAI/bge-m3"))
        _EMBED_MODEL = SentenceTransformer(name)
    return _EMBED_MODEL


def _encode_query(text: str) -> np.ndarray:
    model = _get_embedder()
    kwargs = dict(normalize_embeddings=True, convert_to_numpy=True, batch_size=1)
    try:
        # Algunos modelos no traen prompts configurados
        if "prompt_name" in inspect.signature(model.encode).parameters and getattr(model, "prompts", None):
            if "query" in model.prompts:
                kwargs["prompt_name"] = "query"
    except (ValueError, TypeError):
        pass
    vec = model.encode([text], **kwargs)[0]
    return vec


def vector_search(query_vec: np.ndarray, top_k: int = None) -> List[Tuple[Chunk, float]]:
    """
    Devuelve [(chunk, score_vector)] ordenados por similitud coseno ascendente (menor distancia = más similar).
    """
    if top_k is None:
        top_k = getattr(settings, "SEARCH_TOP_K", 50)

    # Asegúrate de que el documento esté indexado
    qs = (
        Chunk.objects
             .filter(document__state="INDEXED", embedding__isnull=False)
             .annotate(distance=CosineDistance("embedding", query_vec.tolist()))
             .select_related("document")
             .order_by("distance")[:top_k]
    )

    # score_vector: convertir distancia a similitud (1 - dist/2) o usar -distance
    results = []
    for ch in qs:
        # CosineDistance devuelve [0..2], 0 = idéntico. Normalizamos a similitud ~ [0..1]
        sim = 1.0 - float(ch.distance) / 2.0
        results.append((ch, sim))
    return results


def synthesize_answer(query: str, hits: List[Tuple[Chunk, float]], max_snippets: int = 5) -> Dict[str, Any]:
    """
    MVP: responde con una síntesis simple (no-LLM) y citas.
    """
    snippets = []
    for i, (ch, sim) in enumerate(hits[:max_snippets], start=1):
        title = ch.document.title or f"{ch.document.source_slug.upper()} {ch.document.number or ''}".strip()
        preview = (ch.text or "")[:360].replace("\n", " ").strip()
        snippets.append({
            "rank": i,
            "document_id": ch.document_id,
            "chunk_id": ch.id,
            "title": title,
            "section": ch.section,
            "preview": preview,
            "similarity": round(sim, 4),
        })

    # Plantilla sencilla
    lines = [f"Consulta: {query}", "", "Pasajes relevantes:"]
    for s in snippets:
        lines.append(f"- {s['title']} [{s['section'] or 'BODY'}] (sim={s['similarity']}) — {s['preview']}")
    answer_text = "\n".join(lines)

    return {"text": answer_text, "snippets": snippets}


def ask(user, query: str, session: ChatSession | None = None) -> Tuple[ChatMessage, list[SearchHit]]:
    """
    Orquestración: guarda mensaje user, busca, genera answer, guarda mensaje assistant y hits.
    """
    t0 = time.perf_counter()

    if session is None:
        session = ChatSession.objects.create(user=user, title=(query[:80] + "…") if len(query) > 80 else query)

    # Mensaje del usuario
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, text=query)

    # Retrieve
    qvec = _encode_query(query)
    pairs = vector_search(qvec)

    # Síntesis MVP
    answer = synthesize_answer(query, pairs)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    # Persistir assistant + hits
    with transaction.atomic():
        msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text=answer["text"],
            answer_json={"snippets": answer["snippets"]},
            latency_ms=latency_ms,
        )

        hits = []
        for i, (ch, sim) in enumerate(pairs, start=1):
            hits.append(SearchHit(
                message=msg,
                document=ch.document,
                chunk=ch,
                rank=i,
                score_vector=float(sim),
                meta_json={"section": ch.section},
            ))
        SearchHit.objects.bulk_create(hits, batch_size=500)

    return msg, hits

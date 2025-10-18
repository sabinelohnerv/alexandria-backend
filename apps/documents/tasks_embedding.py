import os
import logging
from celery import shared_task
from django.db import transaction

from .models import Document, Chunk
from common.clients.tei_embed import tei_embed

log = logging.getLogger(__name__)

_MODEL_NAME = os.getenv("EMBEDDINGS_MODEL", "BAAI/bge-m3")

def _prepare_passages(texts):
    name = (_MODEL_NAME or "").lower()
    if any(k in name for k in ("bge", "e5", "gte")):
        return [f"passage: {t}" for t in texts]
    return texts

@shared_task(queue="embedding")
def warmup_embeddings():
    tei_embed(["ok"]) 
    return "ready"

@shared_task(queue="embedding", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def embed_document(doc_id: int, batch_size: int = 128):
    rows = list(
        Chunk.objects
             .filter(document_id=doc_id)
             .order_by("ordinal")
             .values("id", "text")
    )
    if not rows:
        Document.objects.filter(id=doc_id).update(state="FAILED")
        log.warning("embed_document(%s): no hay chunks", doc_id)
        return

    texts = _prepare_passages([r["text"] or "" for r in rows])

    vecs_all = []
    n = len(texts)
    i = 0
    while i < n:
        j = min(i + int(batch_size), n)
        batch = texts[i:j]
        mat = tei_embed(batch)               
        vecs_all.append(mat)
        i = j

    import numpy as np
    vectors = np.vstack(vecs_all) if len(vecs_all) > 1 else vecs_all[0]

    if vectors.shape[0] != len(rows):
        raise RuntimeError(
            f"embed_document({doc_id}): mismatch filas={len(rows)} vs vecs={vectors.shape[0]}"
        )

    with transaction.atomic():
        for v, r in zip(vectors, rows):
            Chunk.objects.filter(id=r["id"]).update(embedding=v.tolist())
        Document.objects.filter(id=doc_id).update(state="INDEXED")

    log.info("embed_document(%s): %s chunks embebidos (dim=%s)", doc_id, len(rows), vectors.shape[1])

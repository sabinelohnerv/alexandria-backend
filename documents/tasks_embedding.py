# documents/tasks_embedding.py
import os
import logging
from celery import shared_task
from django.db import transaction
from .models import Document, Chunk

log = logging.getLogger(__name__)

_MODEL = None
_MODEL_NAME = os.getenv("EMBEDDINGS_MODEL", "BAAI/bge-m3")

def get_model():
    """Carga perezosa del modelo para no romper el arranque del worker."""
    global _MODEL
    if _MODEL is None:
        # Evita import de torchvision por transformers
        os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(_MODEL_NAME)
        log.info("SentenceTransformer loaded: %s", _MODEL_NAME)
    return _MODEL

def _prepare_passages(texts):
    """Para BGE/E5/GTE, prefija 'passage: ' a cada texto del corpus."""
    name = (_MODEL_NAME or "").lower()
    if any(k in name for k in ("bge", "e5", "gte")):
        return [f"passage: {t}" for t in texts]
    return texts

@shared_task(queue="embedding")
def warmup_embeddings():
    m = get_model()
    m.encode(["ok"], batch_size=1, normalize_embeddings=True, convert_to_numpy=True)
    return "ready"

@shared_task(queue="embedding", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def embed_document(doc_id: int, batch_size: int = 32):
    model = get_model()

    rows = list(
        Chunk.objects
             .filter(document_id=doc_id)
             .order_by("ordinal")
             .values("id", "text")
    )
    if not rows:
        Document.objects.filter(id=doc_id).update(state="FAILED")
        return

    texts = _prepare_passages([r["text"] for r in rows])

    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,   # similitud coseno
        convert_to_numpy=True,
    )

    with transaction.atomic():
        for v, r in zip(vectors, rows):
            Chunk.objects.filter(id=r["id"]).update(embedding=v.tolist())
        Document.objects.filter(id=doc_id).update(state="INDEXED")

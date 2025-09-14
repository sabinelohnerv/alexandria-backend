import os
import inspect
from celery import shared_task
from django.db import transaction
from .models import Document, Chunk

_MODEL = None

def get_model():
    """Carga perezosa del modelo para no romper el arranque del worker."""
    global _MODEL
    if _MODEL is None:
        # Asegura que Transformers no intente cargar torchvision
        os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")
        # Import perezoso: evita cargar transformers/torch al importar el módulo
        from sentence_transformers import SentenceTransformer
        name = os.getenv("EMBEDDINGS_MODEL", "BAAI/bge-m3")
        _MODEL = SentenceTransformer(name)
    return _MODEL

@shared_task(queue="embedding")
def warmup_embeddings():
    m = get_model()
    m.encode(["ok"], batch_size=1, normalize_embeddings=True, convert_to_numpy=True)
    return "ready"

@shared_task(queue="embedding")
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

    encode_kwargs = dict(
        batch_size=batch_size,
        normalize_embeddings=True,   # para similitud coseno
        convert_to_numpy=True,
    )
    try:
        if "prompt_name" in inspect.signature(model.encode).parameters:
            encode_kwargs["prompt_name"] = "passage"
    except (ValueError, TypeError):
        pass

    texts = [r["text"] for r in rows]
    vectors = model.encode(texts, **encode_kwargs)

    with transaction.atomic():
        for v, r in zip(vectors, rows):
            Chunk.objects.filter(id=r["id"]).update(embedding=v.tolist())
        Document.objects.filter(id=doc_id).update(state="INDEXED")

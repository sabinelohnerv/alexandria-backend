from celery import shared_task
from django.db import transaction
from .models import Document, Chunk
from .utils import sliding_windows, count_tokens

@shared_task(queue="chunking", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def chunk_document(doc_id: int, content: dict):
    doc = Document.objects.get(id=doc_id)
    blocks = (content.get("blocks") or {"BODY": content.get("text") or ""})

    ordinal = 0
    to_create = []
    for section, text in blocks.items():
        text = text or ""
        for piece in sliding_windows(text, max_tokens=900, overlap=120):
            ordinal += 1
            to_create.append(Chunk(
                document=doc,
                ordinal=ordinal,
                section=(section or "")[:120],
                text=piece,
                token_count=count_tokens(piece),
            ))

    with transaction.atomic():
        Chunk.objects.filter(document=doc).delete()
        if to_create:
            Chunk.objects.bulk_create(to_create, batch_size=100)
        doc.state = "CHUNKED"
        doc.save(update_fields=["state"])

    from .tasks_embedding import embed_document
    embed_document.apply_async(args=[doc.id], queue="embedding")

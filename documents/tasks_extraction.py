import re
from io import BytesIO
from celery import shared_task
from django.db import transaction
from .models import Document
from .utils import get_pdf_bytes, normalize_spaces

@shared_task(queue="extraction", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def extract_document(doc_id: int):
    """
    Extrae texto del PDF y despacha el chunking.
    """
    from pdfminer.high_level import extract_text

    doc = Document.objects.get(id=doc_id)
    pdf_bytes = get_pdf_bytes(doc.storage_key)
    raw = extract_text(BytesIO(pdf_bytes)) or ""
    raw = normalize_spaces(raw)

    if doc.source_slug == "tcp":
        content = extract_tcp(raw)
    elif doc.source_slug == "tsj":
        content = extract_tsj(raw)
    else:
        content = extract_cpc(raw)

    with transaction.atomic():
        doc.meta = {**(doc.meta or {}), "extracted_chars": len(raw)}
        doc.state = "EXTRACTED"
        doc.save(update_fields=["meta", "state"])

    # Encolar explícitamente en la cola chunking
    from .tasks_chunking import chunk_document
    chunk_document.apply_async(args=[doc.id, content], queue="chunking")


def extract_tcp(text: str) -> dict:
    sections = {}
    pt = re.split(r"(?i)\bPOR\s+TANTO\b[:\-]?", text, maxsplit=1)
    body = pt[0]
    por_tanto = pt[1] if len(pt) > 1 else ""

    parts = re.split(r"(?m)^(I{1,3}\.)\s*", body)
    if len(parts) > 1:
        for i in range(1, len(parts), 2):
            sections[parts[i].strip(".")] = parts[i + 1].strip()
    else:
        sections["BODY"] = body.strip()

    if por_tanto.strip():
        sections["POR_TANTO"] = por_tanto.strip()

    return {"blocks": sections}


def extract_tsj(text: str) -> dict:
    blocks = {}
    m = re.split(r"(?im)^\s*M[ÁA]XIMA\s*:?\s*$", text, maxsplit=1)
    if len(m) > 1:
        rest = m[1]
        r = re.split(r"(?im)^\s*RATIO\s*:?\s*$", rest, maxsplit=1)
        blocks["MAXIMA"] = r[0].strip()
        if len(r) > 1:
            blocks["RATIO"] = r[1].strip()
    else:
        blocks["BODY"] = text
    return {"blocks": blocks}


def extract_cpc(text: str) -> dict:
    pattern = re.compile(r"(?im)^(?:Art[íi]?culo|Art\.)\s+\d+\.-\s*")
    blocks = {}
    current = None
    acc = []
    for ln in text.splitlines(True):
        if pattern.match(ln):
            if current:
                blocks[current] = "".join(acc).strip()
                acc = []
            current = pattern.findall(ln)[0].strip()
            acc.append(ln)
        else:
            acc.append(ln)
    if current:
        blocks[current] = "".join(acc).strip()
    if not blocks:
        blocks["BODY"] = text
    return {"blocks": blocks}

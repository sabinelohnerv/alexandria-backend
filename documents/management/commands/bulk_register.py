import csv
from datetime import date
from django.core.management.base import BaseCommand
from documents.models import Document
from documents.tasks_extraction import extract_document

def parse_date_maybe(value: str):
    if not value:
        return None
    try:
        # ISO: YYYY-MM-DD
        return date.fromisoformat(value)
    except Exception:
        return None

class Command(BaseCommand):
    help = "Register documents from a CSV manifest and enqueue extraction."

    def add_arguments(self, parser):
        parser.add_argument("--csv", required=True, help="CSV path with columns: storage_key,source_slug,authority,doc_type,number,year,published_date,title")

    def handle(self, *args, **opts):
        path = opts["csv"]
        created = 0
        skipped = 0

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                storage_key = (row.get("storage_key") or "").strip()
                source_slug = (row.get("source_slug") or "").strip()
                if not storage_key or not source_slug:
                    continue

                defaults = {
                    "authority": (row.get("authority") or "").strip(),
                    "doc_type": (row.get("doc_type") or "").strip(),
                    "number": (row.get("number") or "").strip(),
                    "year": (row.get("year") or "").strip(),
                    "published_date": parse_date_maybe((row.get("published_date") or "").strip()),
                    "title": (row.get("title") or "").strip(),
                }

                doc, is_new = Document.objects.get_or_create(
                    storage_key=storage_key,
                    defaults={"source_slug": source_slug, **defaults}
                )
                if is_new:
                    created += 1
                    extract_document.delay(doc.id)
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(f"Registered: {created}, skipped (already existed): {skipped}"))

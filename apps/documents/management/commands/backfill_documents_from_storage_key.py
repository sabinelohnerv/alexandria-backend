import re
import os
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.documents.models import Document

NUM_YEAR_PAT = re.compile(r"(?P<num>\d{1,6})-(?P<year>19\d{2}|20\d{2})\b", re.IGNORECASE)
YEAR_IN_PATH = re.compile(r"raw/(?P<year>19\d{2}|20\d{2})/", re.IGNORECASE)

def _path_parts(storage_key: str):
    # raw/2025/09/tcp/0948-2023-S4_CONF.pdf → ["raw","2025","09","tcp","0948-2023-S4_CONF.pdf"]
    return [p for p in storage_key.strip("/").split("/") if p]

def _infer_origin(parts) -> Tuple[Optional[str], Optional[str]]:
    """
    Devuelve (source_slug, authority) por carpeta.
    """
    # Heurística básica por segmento
    if "tcp" in parts:
        return "tcp", "TCP"
    if "tsj" in parts:
        return "tsj", "TSJ"
    # Normativa
    p = "/".join(parts).lower()
    if "normativa" in p and "codigos" in p and "cpc" in p:
        return "cpc", "ALP"
    if "normativa" in p and ("cpe" in p or "constitucion" in p or "constitución" in p):
        return "cpe", "ALP"
    # Desconocido
    return None, None

def _infer_doc_type(parts, filename_noext: str, source_slug: Optional[str]) -> Optional[str]:
    p = "/".join(parts).lower()
    # Normativa / Constitución
    if "normativa" in p and "cpc" in p:
        return "normativa"
    if "normativa" in p and ("cpe" in p or "constitucion" in p or "constitución" in p):
        return "constitucion"

    # Jurisprudencia
    if source_slug == "tcp":
        return "jurisprudencia"

    if source_slug == "tsj":
        if "autos_supremos" in p or "auto_supremo" in filename_noext.lower():
            return "auto_supremo"
        if "resoluciones" in p or "resolucion" in filename_noext.lower():
            return "resolucion"
        if "sentencias" in p or "sentencia" in filename_noext.lower():
            return "sentencia"
        return "jurisprudencia"

    return None

def _infer_number_and_year(filename_noext: str, storage_key: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Intenta detectar "0948-2023" del nombre; si no, año de la carpeta raw/YYYY.
    """
    m = NUM_YEAR_PAT.search(filename_noext)
    if m:
        num = m.group("num").lstrip("0") or m.group("num")  # conserva si todo era 0
        year = int(m.group("year"))
        return f"{num}-{year}", year

    # A veces TSJ resoluciones tienen sólo número
    m2 = re.search(r"\b(?P<num>\d{3,6})\b", filename_noext)
    year = None
    yp = YEAR_IN_PATH.search(storage_key)
    if yp:
        year = int(yp.group("year"))
    return (m2.group("num") if m2 else None), year

def _build_title(source_slug: Optional[str], doc_type: Optional[str], number: Optional[str], year: Optional[int], filename_noext: str) -> str:
    # Títulos simples y consistentes
    if source_slug == "tcp" and number and year:
        # SC/SCP… no siempre está; usamos SCP genérico
        return f"SCP {number.replace('-', '/')}"
    if source_slug == "tsj" and number:
        # Si detectamos "auto supremo" en el nombre
        if "auto" in filename_noext.lower():
            return f"AS {number if '-' not in number else number.replace('-', '/')}"
        if "sentenc" in filename_noext.lower():
            return f"Sentencia {number if '-' not in number else number.replace('-', '/')}"
        if "resoluc" in filename_noext.lower():
            return f"Resolución {number}"
        # genérico
        if year and '-' in number:
            return number.replace('-', '/')
        return number
    if doc_type in {"normativa", "constitucion"}:
        return filename_noext.upper().replace("_", " ")
    # fallback
    return filename_noext

def _safe_lower(val: Optional[str]) -> str:
    return (val or "").strip().lower()

class Command(BaseCommand):
    help = "Backfill/corrección de metadatos Document a partir de storage_key (TSJ/TCP/Normativa)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="No guarda cambios, sólo muestra diff.")
        parser.add_argument("--only", type=str, help="IDs separados por coma para limitar el procesamiento.")
        parser.add_argument("--batch", type=int, default=1000, help="Tamaño de lote para commits.")
        parser.add_argument("--filter", type=str, help="Filtro por source_slug actual (e.g., tcp, tsj).")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        only_ids = []
        if opts.get("only"):
            only_ids = [int(x) for x in opts["only"].split(",") if x.strip().isdigit()]
        q = Q()
        if only_ids:
            q &= Q(id__in=only_ids)
        if opts.get("filter"):
            q &= Q(source_slug=opts["filter"])

        qs = Document.objects.filter(q).order_by("id").only(
            "id", "storage_key", "source_slug", "authority",
            "doc_type", "number", "year", "published_date", "title", "meta", "state"
        )

        updates = 0
        total = qs.count()
        self.stdout.write(self.style.WARNING(f"Procesando {total} documentos (dry_run={dry})"))

        buffer = []
        with transaction.atomic():
            for doc in qs.iterator(chunk_size=500):
                if not doc.storage_key:
                    continue

                parts = _path_parts(doc.storage_key)
                filename = parts[-1] if parts else ""
                filename_noext = os.path.splitext(filename)[0]

                # 1) origen (slug/authority)
                inferred_slug, inferred_auth = _infer_origin(parts)
                cur_slug = _safe_lower(doc.source_slug)
                cur_auth = (doc.authority or "").strip()

                if inferred_slug and cur_slug != inferred_slug:
                    doc.source_slug = inferred_slug
                if inferred_auth and cur_auth != inferred_auth:
                    doc.authority = inferred_auth

                # 2) tipo documental
                if not doc.doc_type:
                    doc.doc_type = _infer_doc_type(parts, filename_noext, doc.source_slug)

                # 3) número + año
                need_number = not doc.number
                need_year = not doc.year
                number, year = _infer_number_and_year(filename_noext, doc.storage_key)

                if need_number and number:
                    doc.number = number
                if need_year and year:
                    doc.year = year

                # 4) published_date (si no hay)
                if not doc.published_date and doc.year:
                    # marcador razonable al medio del año
                    doc.published_date = datetime(int(doc.year), 7, 1, tzinfo=timezone.utc).date()

                # 5) title mínimamente informativo
                if not doc.title:
                    doc.title = _build_title(doc.source_slug, doc.doc_type, doc.number, doc.year, filename_noext)

                # 6) meta: guardar trazabilidad de inferencias
                meta = dict(doc.meta or {})
                meta.setdefault("_backfill", {})
                meta["_backfill"].update({
                    "from_storage_key": True,
                    "inferred_slug": inferred_slug,
                    "inferred_authority": inferred_auth,
                    "filename": filename,
                })
                doc.meta = meta

                # 7) marcar como INDEXED si ya estaba (no tocamos state si viene distinto)
                # no se cambia aquí para no interferir con tu pipeline

                buffer.append(doc)
                if len(buffer) >= opts["batch"]:
                    updates += self._flush(buffer, dry)
                    buffer = []

            if buffer:
                updates += self._flush(buffer, dry)

            if dry:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(f"Listo. Registros {'a actualizar' if dry else 'actualizados'}: {updates}"))

    def _flush(self, docs, dry: bool) -> int:
        if dry:
            for d in docs:
                self.stdout.write(f"[DRY] id={d.id} slug={d.source_slug} auth={d.authority} type={d.doc_type} "
                                  f"num={d.number} year={d.year} pub={d.published_date} title={d.title}")
            return len(docs)
        # Guardado individual (evita overwrites parciales de fields omitidos)
        for d in docs:
            d.save(update_fields=[
                "source_slug", "authority", "doc_type",
                "number", "year", "published_date", "title", "meta", "updated_at"
            ])
        return len(docs)

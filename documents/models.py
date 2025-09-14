import os
from django.db import models
from pgvector.django import VectorField

EMB_DIM = int(os.getenv("EMBEDDINGS_DIM", "1024"))

class Document(models.Model):
    SOURCE_CHOICES = [("tcp", "TCP"), ("tsj", "TSJ"), ("normativa", "Normativa")]
    STATE_CHOICES = [
        ("PENDING", "Pending"),
        ("EXTRACTED", "Extracted"),
        ("CHUNKED", "Chunked"),
        ("INDEXED", "Indexed"),
        ("FAILED", "Failed"),
    ]

    # S3/MinIO object key, e.g. raw/2025/09/tcp/0001-2019-CDP_FUN.pdf
    storage_key = models.CharField(max_length=512, unique=True)
    source_slug = models.CharField(max_length=20, choices=SOURCE_CHOICES)

    authority       = models.CharField(max_length=20, blank=True)   # e.g., TCP / TSJ / LEG
    doc_type        = models.CharField(max_length=50, blank=True)   # e.g., AC, SCP, FICHA, CODE
    number          = models.CharField(max_length=50, blank=True)   # document number/id
    year            = models.CharField(max_length=50, blank=True)   # "gestión" (año)
    published_date  = models.DateField(null=True, blank=True)
    title           = models.CharField(max_length=500, blank=True)

    meta   = models.JSONField(default=dict, blank=True)
    state  = models.CharField(max_length=20, choices=STATE_CHOICES, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.source_slug}:{self.storage_key}"


class Chunk(models.Model):
    document    = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    ordinal     = models.IntegerField()                   # order within document
    section     = models.CharField(max_length=120, blank=True)  # I/II/III/POR_TANTO/ART_xxx/MAXIMA/RATIO
    block       = models.CharField(max_length=120, blank=True)  # extra label if needed
    text        = models.TextField()
    token_count = models.IntegerField(default=0)
    embedding   = VectorField(dimensions=EMB_DIM, null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("document", "ordinal")
        indexes = [models.Index(fields=["document", "ordinal"])]

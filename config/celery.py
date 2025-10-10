# config/celery.py
import os

# === Entorno antes de cargar Django/Celery ===
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from celery import Celery
from kombu import Queue, Exchange

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# --- Colas explícitas ---
app.conf.task_default_queue = "default"
app.conf.task_queues = (
    Queue("default",    Exchange("default"),    routing_key="default"),
    Queue("ingestion",  Exchange("ingestion"),  routing_key="ingestion"),
    Queue("extraction", Exchange("extraction"), routing_key="extraction"),
    Queue("chunking",   Exchange("chunking"),   routing_key="chunking"),
    Queue("embedding",  Exchange("embedding"),  routing_key="embedding"),
)

# --- Rutas por módulo de tareas (según tus archivos) ---
app.conf.task_routes = {
    "documents.tasks_extraction.*": {"queue": "extraction", "routing_key": "extraction"},
    "documents.tasks_chunking.*":   {"queue": "chunking",   "routing_key": "chunking"},
    "documents.tasks_embedding.*":  {"queue": "embedding",  "routing_key": "embedding"},
    "*": {"queue": "default", "routing_key": "default"},
}

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    enable_utc=True,
    timezone="UTC",
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_time_limit=60 * 30,
    task_soft_time_limit=60 * 25,
    broker_connection_retry_on_startup=True,
)

@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")

# Para importar como 'celery_app' desde config
__all__ = ("app",)

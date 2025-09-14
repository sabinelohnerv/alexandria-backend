import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Evita que Transformers intente importar torchvision (origen de torchvision::nms)
os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")
# Evita los avisos de paralelismo del tokenizador
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from celery import Celery  

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")

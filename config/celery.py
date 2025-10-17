import os
import ssl, certifi
from django.conf import settings
from celery import Celery  

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("TRANSFORMERS_NO_TORCHVISION", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.broker_use_ssl = {
    "ssl_cert_reqs": ssl.CERT_REQUIRED,
    "ssl_ca_certs": certifi.where(),
}
app.conf.redis_backend_use_ssl = {
    "ssl_cert_reqs": ssl.CERT_REQUIRED,
    "ssl_ca_certs": certifi.where(),
}
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
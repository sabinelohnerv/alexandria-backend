from django.apps import AppConfig
import os
import sys

class SearchConfig(AppConfig):
    name = "apps.search"

    def ready(self):
        mgmt_cmds_to_skip = {
            "migrate", "makemigrations", "collectstatic", "shell",
            "test", "loaddata", "dumpdata", "createsuperuser"
        }
        if any(cmd in sys.argv for cmd in mgmt_cmds_to_skip):
            return

        if os.getenv("DISABLE_WARMUP", "").lower() in {"1", "true", "yes"}:
            return

        try:
            from . import signals  # noqa: F401

            from .services.ranking.embeddings import warmup_models
            warmup_models()  

            try:
                from common.clients.tei_rerank import tei_rerank_scores
                _ = tei_rerank_scores("warmup", ["a", "b"], raw=True)
            except Exception:
                pass

        except Exception:
            pass

from django.apps import AppConfig

class SearchConfig(AppConfig):
    name = "search"

    def ready(self):
        try:
            from . import signals
            from .services.ranking.embeddings import warmup_models
            warmup_models()
            from .services.ranking.reranker import _get_reranker
            m = _get_reranker()
            if m:
                _ = m.predict([("warmup","warmup")], batch_size=1, show_progress_bar=False)
        except Exception:
            pass

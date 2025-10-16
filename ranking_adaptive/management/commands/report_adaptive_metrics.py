from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from ranking_adaptive.models import RankingDecision
from search.models import Feedback

class Command(BaseCommand):
    def add_arguments(self, p):
        p.add_argument("--hours", type=int, default=24)

    def handle(self, *a, **o):
        since = timezone.now() - timedelta(hours=o["hours"])
        shown = RankingDecision.objects.filter(ts__gte=since, shown_pos__lte=10)
        shown_keys = {(d.query_id, d.hit_id) for d in shown}
        useful = Feedback.objects.filter(hit__isnull=False, label="useful", created_at__gte=since)
        useful_keys = {(f.hit.message_id, f.hit.chunk_id) for f in useful}
        useful_rate = sum(1 for k in shown_keys if k in useful_keys) / max(1, len(shown_keys))
        self.stdout.write(f"useful@top10={useful_rate:.3f}  (window {o['hours']}h)")

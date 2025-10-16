from django.core.management.base import BaseCommand
from ranking_adaptive.models import RankingWeights
class Command(BaseCommand):
    def handle(self, *a, **o):
        rows = list(RankingWeights.objects.order_by('-created_at')[:2])
        if len(rows) < 2:
            self.stdout.write("No prev version"); return
        rows[0].is_active = False; rows[0].save(update_fields=["is_active"])
        rows[1].is_active = True;  rows[1].save(update_fields=["is_active"])
        self.stdout.write(f"Activated prev: {rows[1].version}")
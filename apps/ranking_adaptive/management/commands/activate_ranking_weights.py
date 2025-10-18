# ranking_adaptive/management/commands/activate_ranking_weights.py
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.ranking_adaptive.models import RankingWeights

class Command(BaseCommand):
    help = "Activa una versión de pesos de señales para el reranking"

    def add_arguments(self, parser):
        parser.add_argument("version", type=str, help="Nombre exacto de la versión (p.ej. w_20251016_123456)")

    def handle(self, *args, **options):
        version = options["version"]
        with transaction.atomic():
            try:
                target = RankingWeights.objects.get(version=version)
            except RankingWeights.DoesNotExist:
                raise CommandError(f"Version '{version}' no encontrada")

            RankingWeights.objects.filter(is_active=True).update(is_active=False)
            target.is_active = True
            target.save(update_fields=["is_active"])

        self.stdout.write(self.style.SUCCESS(f"Activada versión: {version}"))

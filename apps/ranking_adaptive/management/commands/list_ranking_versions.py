# ranking_adaptive/management/commands/list_ranking_versions.py
from django.core.management.base import BaseCommand
from apps.ranking_adaptive.models import RankingWeights


class Command(BaseCommand):
    help = "Lista todas las versiones de pesos de ranking almacenadas"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Número máximo de versiones a mostrar (default: 20)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Muestra información detallada incluyendo pesos",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        verbose = options["verbose"]

        versions = RankingWeights.objects.order_by("-created_at")[:limit]
        
        if not versions:
            self.stdout.write(self.style.WARNING("No hay versiones de pesos almacenadas"))
            return

        self.stdout.write(self.style.MIGRATE_HEADING("=== Versiones de Pesos de Ranking ==="))
        self.stdout.write("")
        
        for idx, v in enumerate(versions, 1):
            status_icon = "🟢" if v.is_active else "⚪"
            status_text = "ACTIVA" if v.is_active else "inactiva"
            
            self.stdout.write(
                self.style.SUCCESS(f"{status_icon} [{idx}] {v.version}") 
                if v.is_active 
                else f"{status_icon} [{idx}] {v.version}"
            )
            self.stdout.write(f"    Estado: {status_text}")
            self.stdout.write(f"    Creada: {v.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            
            if v.weights:
                self.stdout.write(f"    Dimensión: {len(v.weights)} señales")
                
                if verbose:
                    self.stdout.write(f"    Pesos: {[round(w, 4) for w in v.weights]}")
            
            if v.notes:
                self.stdout.write(f"    Notas: {v.notes}")
            
            self.stdout.write("")
        
        active_count = sum(1 for v in versions if v.is_active)
        total_count = RankingWeights.objects.count()
        
        self.stdout.write(f"Total de versiones: {total_count}")
        self.stdout.write(f"Versiones activas: {active_count}")
        
        if active_count == 0:
            self.stdout.write(
                self.style.WARNING("\n⚠ No hay ninguna versión activa. Activa una con:")
            )
            if versions:
                self.stdout.write(f"  python manage.py activate_ranking_weights {versions[0].version}")

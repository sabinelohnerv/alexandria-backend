# ranking_adaptive/management/commands/train_ranking_weights.py
from django.core.management.base import BaseCommand
from apps.ranking_adaptive.tasks import train_signal_weights


class Command(BaseCommand):
    help = "Entrena nuevos pesos de señales usando feedback histórico (pairwise learning)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Ventana de días de feedback histórico (default: 30)",
        )
        parser.add_argument(
            "--lr",
            type=float,
            default=5e-3,
            help="Learning rate (default: 0.005)",
        )
        parser.add_argument(
            "--steps",
            type=int,
            default=800,
            help="Número de pasos de optimización (default: 800)",
        )
        parser.add_argument(
            "--l2",
            type=float,
            default=0.2,
            help="Regularización L2 hacia pesos previos (default: 0.2)",
        )
        parser.add_argument(
            "--clip-rel",
            type=float,
            default=0.5,
            help="Clip relativo: ±50%% del peso previo (default: 0.5)",
        )
        parser.add_argument(
            "--nonneg-idx",
            type=str,
            default="0,1",
            help="Índices de señales que deben ser no-negativas (default: '0,1')",
        )

    def handle(self, *args, **options):
        days = options["days"]
        lr = options["lr"]
        steps = options["steps"]
        l2 = options["l2"]
        clip_rel = options["clip_rel"]
        nonneg_str = options["nonneg_idx"]
        
        nonneg_idx = tuple(int(x.strip()) for x in nonneg_str.split(",") if x.strip())

        self.stdout.write(self.style.MIGRATE_HEADING("=== Entrenamiento de Pesos de Ranking ==="))
        self.stdout.write(f"Parámetros:")
        self.stdout.write(f"  - Ventana temporal: {days} días")
        self.stdout.write(f"  - Learning rate: {lr}")
        self.stdout.write(f"  - Pasos de optimización: {steps}")
        self.stdout.write(f"  - Regularización L2: {l2}")
        self.stdout.write(f"  - Clip relativo: ±{clip_rel*100:.0f}%")
        self.stdout.write(f"  - Índices no-negativos: {nonneg_idx}")
        self.stdout.write("")

        try:
            version_name = train_signal_weights(
                days=days,
                lr=lr,
                steps=steps,
                l2=l2,
                nonneg_idx=nonneg_idx,
                clip_rel=clip_rel,
            )
            
            if version_name == "NOOP_EMPTY_DATASET":
                self.stdout.write(
                    self.style.WARNING("⚠ No hay datos suficientes para entrenar")
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Entrenamiento completado: {version_name}")
                )
                self.stdout.write("")
                self.stdout.write("Siguiente paso:")
                self.stdout.write(f"  python manage.py list_ranking_versions")
                self.stdout.write(f"  python manage.py evaluate_ranking_model --version {version_name}")
                self.stdout.write(f"  python manage.py activate_ranking_weights {version_name}")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error durante el entrenamiento: {e}"))
            raise

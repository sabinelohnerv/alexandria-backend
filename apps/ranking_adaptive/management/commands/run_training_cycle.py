# ranking_adaptive/management/commands/run_training_cycle.py
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from io import StringIO
import sys


class Command(BaseCommand):
    help = "Ejecuta el ciclo completo de entrenamiento: entrenar → evaluar → reportar"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Ventana de datos para entrenamiento (default: 30)",
        )
        parser.add_argument(
            "--eval-days",
            type=int,
            default=7,
            help="Ventana de evaluación (default: 7)",
        )
        parser.add_argument(
            "--auto-activate",
            action="store_true",
            help="Activa automáticamente la nueva versión si la evaluación es positiva",
        )
        parser.add_argument(
            "--export",
            action="store_true",
            help="Exporta datos de entrenamiento al final",
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
            help="Pasos de optimización (default: 800)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        eval_days = options["eval_days"]
        auto_activate = options["auto_activate"]
        export = options["export"]
        lr = options["lr"]
        steps = options["steps"]

        start_time = timezone.now()
        
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))
        self.stdout.write(self.style.MIGRATE_HEADING("    CICLO COMPLETO DE ENTRENAMIENTO - RANKING ADAPTATIVO"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))
        self.stdout.write("")
        self.stdout.write(f"Inicio: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write("")

        # PASO 1: Listar versiones actuales
        self._run_step(
            "1/5",
            "Listando versiones actuales",
            "list_ranking_versions",
            limit=5
        )

        # PASO 2: Entrenar nueva versión
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))
        version_name = self._run_training_step(days, lr, steps)
        
        if not version_name or version_name == "NOOP_EMPTY_DATASET":
            self.stdout.write(self.style.ERROR("✗ Entrenamiento falló o no hay datos suficientes"))
            self.stdout.write("")
            self.stdout.write("Ciclo abortado.")
            return

        # PASO 3: Evaluar nueva versión
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))
        self._run_step(
            "3/5",
            f"Evaluando versión {version_name}",
            "evaluate_ranking_model",
            model_version=version_name,
            days=eval_days,
            compare=True
        )

        # PASO 4: Activación (opcional)
        if auto_activate:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))
            self._run_step(
                "4/5",
                f"Activando versión {version_name}",
                "activate_ranking_weights",
                version_name
            )
        else:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("⚠ Auto-activación deshabilitada"))
            self.stdout.write(f"Para activar manualmente: python manage.py activate_ranking_weights {version_name}")

        # PASO 5: Exportar datos (opcional)
        if export:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))
            export_file = f"training_export_{timezone.now():%Y%m%d_%H%M%S}.json"
            self._run_step(
                "5/5",
                "Exportando datos de entrenamiento",
                "export_training_data",
                output=export_file,
                days=days
            )

        # Resumen final
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))
        self.stdout.write(self.style.SUCCESS("✓ CICLO COMPLETADO"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 60))
        self.stdout.write("")
        self.stdout.write(f"Duración total: {duration:.2f} segundos")
        self.stdout.write(f"Nueva versión: {version_name}")
        self.stdout.write(f"Estado: {'ACTIVA' if auto_activate else 'inactiva (requiere activación manual)'}")
        self.stdout.write("")
        
        if not auto_activate:
            self.stdout.write("Próximos pasos:")
            self.stdout.write(f"  1. Revisar evaluación arriba")
            self.stdout.write(f"  2. Activar si es satisfactoria:")
            self.stdout.write(f"     python manage.py activate_ranking_weights {version_name}")
            self.stdout.write(f"  3. Monitorear métricas:")
            self.stdout.write(f"     python manage.py report_adaptive_metrics --hours 24")

    def _run_step(self, step_num, description, command, *args, **kwargs):
        """Ejecuta un paso del ciclo"""
        self.stdout.write(self.style.MIGRATE_LABEL(f"[{step_num}] {description}"))
        self.stdout.write("")
        
        try:
            call_command(command, *args, **kwargs, stdout=self.stdout)
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error en {command}: {e}"))
            return False

    def _run_training_step(self, days, lr, steps):
        """Ejecuta el entrenamiento y captura el nombre de la versión"""
        self.stdout.write(self.style.MIGRATE_LABEL("[2/5] Entrenando nueva versión"))
        self.stdout.write("")
        
        # Capturar output para extraer el nombre de la versión
        output = StringIO()
        
        try:
            call_command(
                "train_ranking_weights",
                days=days,
                lr=lr,
                steps=steps,
                stdout=output
            )
            
            # Mostrar output
            output_text = output.getvalue()
            self.stdout.write(output_text)
            
            # Extraer nombre de versión del output
            for line in output_text.split("\n"):
                if "Entrenamiento completado:" in line:
                    version_name = line.split(":")[-1].strip()
                    return version_name
                elif "NOOP_EMPTY_DATASET" in line:
                    return "NOOP_EMPTY_DATASET"
            
            return None
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error durante entrenamiento: {e}"))
            return None

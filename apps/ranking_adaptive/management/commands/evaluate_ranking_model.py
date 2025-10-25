# ranking_adaptive/management/commands/evaluate_ranking_model.py
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta
import numpy as np
from apps.ranking_adaptive.models import RankingWeights, RankingDecision
from apps.ranking_adaptive.utils import build_pairwise_dataset
from apps.search.models import Feedback


class Command(BaseCommand):
    help = "Evalúa el rendimiento de una versión de pesos de ranking"

    def add_arguments(self, parser):
        parser.add_argument(
            "--model-version",
            type=str,
            dest="version",
            help="Versión específica a evaluar (si no se especifica, usa la activa)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Ventana de evaluación en días (default: 7)",
        )
        parser.add_argument(
            "--compare",
            action="store_true",
            help="Compara con la versión anterior",
        )

    def handle(self, *args, **options):
        version_name = options.get("version")
        days = options["days"]
        compare = options["compare"]

        # Obtener versión a evaluar
        if version_name:
            try:
                version = RankingWeights.objects.get(version=version_name)
            except RankingWeights.DoesNotExist:
                raise CommandError(f"Versión '{version_name}' no encontrada")
        else:
            version = RankingWeights.objects.filter(is_active=True).first()
            if not version:
                raise CommandError("No hay versión activa. Especifica --version")

        self.stdout.write(self.style.MIGRATE_HEADING("=== Evaluación de Modelo de Ranking ==="))
        self.stdout.write(f"Versión: {version.version}")
        self.stdout.write(f"Estado: {'ACTIVA' if version.is_active else 'inactiva'}")
        self.stdout.write(f"Ventana: últimos {days} días")
        self.stdout.write("")

        # 1. Métricas de datos de entrenamiento
        self._evaluate_training_data(version, days)
        
        # 2. Métricas de feedback
        self._evaluate_feedback_metrics(version, days)
        
        # 3. Análisis de pesos
        self._analyze_weights(version)
        
        # 4. Comparación con versión anterior
        if compare:
            self._compare_with_previous(version, days)

    def _evaluate_training_data(self, version, days):
        """Evalúa la calidad del dataset de entrenamiento"""
        self.stdout.write(self.style.MIGRATE_LABEL("1. Dataset de Entrenamiento"))
        
        dataset = build_pairwise_dataset(days=days)
        
        self.stdout.write(f"   Consultas procesadas: {dataset.n_queries}")
        self.stdout.write(f"   Pares generados: {dataset.n_pairs}")
        self.stdout.write(f"   Dimensión de señales: {dataset.dim}")
        
        if dataset.n_pairs > 0:
            avg_pairs_per_query = dataset.n_pairs / max(1, dataset.n_queries)
            self.stdout.write(f"   Pares por consulta: {avg_pairs_per_query:.2f}")
        else:
            self.stdout.write(
                self.style.WARNING("   ⚠ No hay pares de entrenamiento disponibles")
            )
        self.stdout.write("")

    def _evaluate_feedback_metrics(self, version, days):
        """Evalúa métricas de feedback del usuario"""
        self.stdout.write(self.style.MIGRATE_LABEL("2. Métricas de Feedback"))
        
        since = timezone.now() - timedelta(days=days)
        
        # Decisiones mostradas en top-10
        shown = RankingDecision.objects.filter(
            ts__gte=since,
            shown_pos__lte=10,
            model_version=version.version
        )
        shown_count = shown.count()
        
        if shown_count == 0:
            self.stdout.write(
                self.style.WARNING("   ⚠ No hay decisiones registradas para esta versión")
            )
            self.stdout.write("")
            return
        
        shown_keys = {(d.query_id, d.hit_id) for d in shown}
        
        # Feedback útil
        useful = Feedback.objects.filter(
            hit__isnull=False,
            label=Feedback.LABEL_USEFUL,
            created_at__gte=since
        ).select_related("hit")
        
        useful_keys = {(f.hit.message_id, f.hit.chunk_id) for f in useful}
        useful_in_top10 = sum(1 for k in shown_keys if k in useful_keys)
        useful_rate = useful_in_top10 / max(1, shown_count)
        
        # Feedback no útil
        not_useful = Feedback.objects.filter(
            hit__isnull=False,
            label=Feedback.LABEL_NOT_USEFUL,
            created_at__gte=since
        ).select_related("hit")
        
        not_useful_keys = {(f.hit.message_id, f.hit.chunk_id) for f in not_useful}
        not_useful_in_top10 = sum(1 for k in shown_keys if k in not_useful_keys)
        not_useful_rate = not_useful_in_top10 / max(1, shown_count)
        
        self.stdout.write(f"   Decisiones en top-10: {shown_count}")
        self.stdout.write(
            self.style.SUCCESS(f"   Útil@top10: {useful_rate:.3f} ({useful_in_top10} items)")
        )
        self.stdout.write(f"   No útil@top10: {not_useful_rate:.3f} ({not_useful_in_top10} items)")
        
        # Tasa de engagement (cualquier feedback)
        total_feedback = useful_in_top10 + not_useful_in_top10
        engagement_rate = total_feedback / max(1, shown_count)
        self.stdout.write(f"   Engagement rate: {engagement_rate:.3f}")
        self.stdout.write("")

    def _analyze_weights(self, version):
        """Analiza los pesos del modelo"""
        self.stdout.write(self.style.MIGRATE_LABEL("3. Análisis de Pesos"))
        
        if not version.weights:
            self.stdout.write(self.style.WARNING("   ⚠ No hay pesos disponibles"))
            self.stdout.write("")
            return
        
        weights = np.array(version.weights)
        
        self.stdout.write(f"   Dimensión: {len(weights)}")
        self.stdout.write(f"   Pesos: {[round(w, 4) for w in weights]}")
        self.stdout.write(f"   L2 norm: {np.linalg.norm(weights):.4f}")
        self.stdout.write(f"   Max peso: {weights.max():.4f} (índice {weights.argmax()})")
        self.stdout.write(f"   Min peso: {weights.min():.4f} (índice {weights.argmin()})")
        self.stdout.write(f"   Pesos positivos: {(weights > 0).sum()}/{len(weights)}")
        self.stdout.write(f"   Pesos negativos: {(weights < 0).sum()}/{len(weights)}")
        self.stdout.write("")

    def _compare_with_previous(self, version, days):
        """Compara con la versión anterior"""
        self.stdout.write(self.style.MIGRATE_LABEL("4. Comparación con Versión Anterior"))
        
        # Obtener versión anterior
        previous = (
            RankingWeights.objects
            .filter(created_at__lt=version.created_at)
            .order_by("-created_at")
            .first()
        )
        
        if not previous:
            self.stdout.write("   No hay versión anterior para comparar")
            self.stdout.write("")
            return
        
        self.stdout.write(f"   Versión anterior: {previous.version}")
        
        if not version.weights or not previous.weights:
            self.stdout.write(self.style.WARNING("   ⚠ No se pueden comparar pesos"))
            self.stdout.write("")
            return
        
        if len(version.weights) != len(previous.weights):
            self.stdout.write(
                self.style.WARNING("   ⚠ Dimensiones diferentes, no se puede comparar")
            )
            self.stdout.write("")
            return
        
        w_new = np.array(version.weights)
        w_old = np.array(previous.weights)
        
        diff = w_new - w_old
        rel_change = np.abs(diff) / (np.abs(w_old) + 1e-8)
        
        self.stdout.write(f"   Diferencia L2: {np.linalg.norm(diff):.4f}")
        self.stdout.write(f"   Cambio relativo promedio: {rel_change.mean():.3f}")
        self.stdout.write(f"   Cambio relativo máximo: {rel_change.max():.3f}")
        
        # Mostrar cambios significativos
        significant = np.where(np.abs(diff) > 0.01)[0]
        if len(significant) > 0:
            self.stdout.write(f"   Cambios significativos (>0.01):")
            for idx in significant:
                change_pct = ((w_new[idx] - w_old[idx]) / (w_old[idx] + 1e-8)) * 100
                self.stdout.write(
                    f"      Señal {idx}: {w_old[idx]:.4f} → {w_new[idx]:.4f} "
                    f"({change_pct:+.1f}%)"
                )
        self.stdout.write("")

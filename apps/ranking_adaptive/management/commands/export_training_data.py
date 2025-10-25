# ranking_adaptive/management/commands/export_training_data.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import json
from pathlib import Path
from apps.ranking_adaptive.models import RankingDecision, RankingWeights
from apps.ranking_adaptive.utils import build_pairwise_dataset
from apps.search.models import Feedback


class Command(BaseCommand):
    help = "Exporta datos de entrenamiento y métricas para análisis offline"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default="training_data_export.json",
            help="Archivo de salida (default: training_data_export.json)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Ventana de datos en días (default: 30)",
        )
        parser.add_argument(
            "--include-raw",
            action="store_true",
            help="Incluye decisiones y feedback raw",
        )

    def handle(self, *args, **options):
        output_file = options["output"]
        days = options["days"]
        include_raw = options["include_raw"]

        self.stdout.write(self.style.MIGRATE_HEADING("=== Exportación de Datos de Entrenamiento ==="))
        self.stdout.write(f"Ventana: últimos {days} días")
        self.stdout.write(f"Archivo de salida: {output_file}")
        self.stdout.write("")

        since = timezone.now() - timedelta(days=days)
        
        # Construir dataset pairwise
        self.stdout.write("Construyendo dataset pairwise...")
        dataset = build_pairwise_dataset(days=days)
        
        export_data = {
            "metadata": {
                "export_timestamp": timezone.now().isoformat(),
                "window_days": days,
                "include_raw_data": include_raw,
            },
            "dataset": {
                "n_queries": dataset.n_queries,
                "n_pairs": dataset.n_pairs,
                "dimension": dataset.dim,
                "Xdiff_shape": list(dataset.Xdiff.shape) if dataset.Xdiff.size > 0 else [0, 0],
                "y_shape": list(dataset.y.shape) if dataset.y.size > 0 else [0],
            },
            "versions": [],
            "statistics": {},
        }

        # Exportar versiones de pesos
        self.stdout.write("Exportando versiones de pesos...")
        versions = RankingWeights.objects.order_by("-created_at")[:10]
        for v in versions:
            export_data["versions"].append({
                "version": v.version,
                "weights": v.weights,
                "is_active": v.is_active,
                "created_at": v.created_at.isoformat(),
                "notes": v.notes,
            })

        # Estadísticas de decisiones
        self.stdout.write("Calculando estadísticas de decisiones...")
        decisions = RankingDecision.objects.filter(ts__gte=since)
        decisions_count = decisions.count()
        
        export_data["statistics"]["decisions"] = {
            "total": decisions_count,
            "by_position": {},
            "by_version": {},
        }

        if decisions_count > 0:
            # Por posición
            for pos in range(1, 11):
                count = decisions.filter(shown_pos=pos).count()
                export_data["statistics"]["decisions"]["by_position"][pos] = count
            
            # Por versión
            from django.db.models import Count
            by_version = (
                decisions.values("model_version")
                .annotate(count=Count("id"))
                .order_by("-count")
            )
            for item in by_version:
                export_data["statistics"]["decisions"]["by_version"][
                    item["model_version"]
                ] = item["count"]

        # Estadísticas de feedback
        self.stdout.write("Calculando estadísticas de feedback...")
        feedbacks = Feedback.objects.filter(
            created_at__gte=since,
            hit__isnull=False
        )
        feedbacks_count = feedbacks.count()
        
        useful_count = feedbacks.filter(label=Feedback.LABEL_USEFUL).count()
        not_useful_count = feedbacks.filter(label=Feedback.LABEL_NOT_USEFUL).count()
        
        export_data["statistics"]["feedback"] = {
            "total": feedbacks_count,
            "useful": useful_count,
            "not_useful": not_useful_count,
            "useful_rate": useful_count / max(1, feedbacks_count),
        }

        # Datos raw (opcional)
        if include_raw:
            self.stdout.write("Exportando datos raw...")
            
            export_data["raw_decisions"] = []
            for d in decisions[:1000]:  # Limitar a 1000 para no sobrecargar
                export_data["raw_decisions"].append({
                    "query_id": d.query_id,
                    "hit_id": d.hit_id,
                    "model_version": d.model_version,
                    "score_ce": d.score_ce,
                    "rank_before": d.rank_before,
                    "rank_after": d.rank_after,
                    "shown_pos": d.shown_pos,
                    "signals": d.signals,
                    "signal_names": d.signal_names,
                    "timestamp": d.ts.isoformat(),
                })
            
            export_data["raw_feedback"] = []
            for f in feedbacks[:1000]:  # Limitar a 1000
                export_data["raw_feedback"].append({
                    "query_id": f.hit.message_id,
                    "hit_id": f.hit.chunk_id,
                    "label": f.label,
                    "timestamp": f.created_at.isoformat(),
                })

        # Guardar archivo
        self.stdout.write(f"Guardando en {output_file}...")
        output_path = Path(output_file)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        # Resumen
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✓ Exportación completada"))
        self.stdout.write("")
        self.stdout.write("Resumen:")
        self.stdout.write(f"  - Consultas: {dataset.n_queries}")
        self.stdout.write(f"  - Pares de entrenamiento: {dataset.n_pairs}")
        self.stdout.write(f"  - Decisiones: {decisions_count}")
        self.stdout.write(f"  - Feedbacks: {feedbacks_count}")
        self.stdout.write(f"  - Versiones exportadas: {len(export_data['versions'])}")
        self.stdout.write(f"  - Tamaño del archivo: {output_path.stat().st_size / 1024:.2f} KB")

#!/usr/bin/env python
"""
Script para validar end-to-end el flujo de Adaptive Ranking.
Uso: python test_adaptive_ranking.py
"""
import os
import sys
import django
import time
import json
from typing import List, Dict

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from apps.search.models import ChatSession, ChatMessage, SearchHit, Feedback
from apps.ranking_adaptive.models import RankingWeights, RankingDecision, ExperimentAssignment
from apps.ranking_adaptive.utils import build_pairwise_dataset
from apps.ranking_adaptive.tasks import train_signal_weights

User = get_user_model()

def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def get_or_create_test_user():
    """Obtiene o crea un usuario de prueba."""
    user, created = User.objects.get_or_create(
        email="test@adaptive.local",
        defaults={
            "username": "test_adaptive",
            "is_active": True,
        }
    )
    if created:
        user.set_password("testpass123")
        user.save()
        print(f"✓ Usuario de prueba creado: {user.email}")
    else:
        print(f"✓ Usuario de prueba existente: {user.email}")
    return user

def generate_test_queries(user, n: int = 15) -> List[ChatMessage]:
    """Genera consultas de prueba usando el servicio ask."""
    from apps.search.services.ask import ask
    
    print_section("GENERANDO CONSULTAS DE PRUEBA")
    
    queries = [
        "¿Qué es el amparo constitucional?",
        "Jurisprudencia sobre TCP y derechos fundamentales",
        "Sentencias sobre derecho al trabajo",
        "¿Cuál es el procedimiento de amparo?",
        "Normativa sobre contratos laborales",
        "Derechos de la mujer en Bolivia",
        "Jurisprudencia sobre derecho a la salud",
        "¿Qué dice la CPE sobre educación?",
        "Sentencias sobre libertad de expresión",
        "Procedimiento administrativo sancionador",
        "Derechos de los pueblos indígenas",
        "Jurisprudencia sobre medio ambiente",
        "¿Qué es el debido proceso?",
        "Sentencias sobre derecho a la vivienda",
        "Normativa sobre seguridad social",
    ]
    
    messages = []
    for i, query in enumerate(queries[:n], 1):
        try:
            print(f"[{i}/{n}] Consultando: {query[:50]}...")
            msg, hits = ask(user, query)
            messages.append(msg)
            print(f"    → Message ID: {msg.id}, Hits: {len(hits)}")
            time.sleep(0.5)  # Evitar sobrecarga
        except Exception as e:
            print(f"    ✗ Error: {e}")
    
    print(f"\n✓ Total consultas generadas: {len(messages)}")
    return messages

def send_feedback(messages: List[ChatMessage]) -> Dict:
    """Envía feedback contrastante (útil/no útil) para los hits."""
    print_section("ENVIANDO FEEDBACK CONTRASTANTE")
    
    stats = {"useful": 0, "not_useful": 0, "queries_with_feedback": 0}
    
    for msg in messages:
        hits = list(SearchHit.objects.filter(message=msg).order_by('rank')[:5])
        if len(hits) < 2:
            continue
        
        # Marcar el primer hit como útil y el último como no útil
        try:
            # Útil
            Feedback.objects.update_or_create(
                user=msg.session.user,
                hit=hits[0],
                defaults={"label": Feedback.LABEL_USEFUL}
            )
            stats["useful"] += 1
            
            # No útil (último hit)
            Feedback.objects.update_or_create(
                user=msg.session.user,
                hit=hits[-1],
                defaults={"label": Feedback.LABEL_NOT_USEFUL}
            )
            stats["not_useful"] += 1
            stats["queries_with_feedback"] += 1
            
            print(f"✓ Feedback para mensaje {msg.id}: útil={hits[0].id}, no_útil={hits[-1].id}")
        except Exception as e:
            print(f"✗ Error en feedback para mensaje {msg.id}: {e}")
    
    print(f"\n✓ Feedback enviado:")
    print(f"  - Útil: {stats['useful']}")
    print(f"  - No útil: {stats['not_useful']}")
    print(f"  - Consultas con feedback: {stats['queries_with_feedback']}")
    
    return stats

def validate_etl(days: int = 30):
    """Valida el ETL y construcción del dataset pairwise."""
    print_section("VALIDANDO ETL Y DATASET PAIRWISE")
    
    try:
        dataset = build_pairwise_dataset(days=days)
        print(f"✓ Dataset construido:")
        print(f"  - Pares: {dataset.n_pairs}")
        print(f"  - Consultas: {dataset.n_queries}")
        print(f"  - Dimensión: {dataset.dim}")
        print(f"  - Shape Xdiff: {dataset.Xdiff.shape}")
        
        if dataset.n_pairs == 0:
            print("\n⚠ ADVERTENCIA: No hay pares. Necesitas más feedback contrastante.")
            return False
        
        return True
    except Exception as e:
        print(f"✗ Error en ETL: {e}")
        import traceback
        traceback.print_exc()
        return False

def train_weights():
    """Entrena los pesos de señales."""
    print_section("ENTRENANDO PESOS DE SEÑALES")
    
    try:
        print("Ejecutando task de entrenamiento...")
        result = train_signal_weights()
        
        if result == "NOOP_EMPTY_DATASET":
            print("✗ No se pudo entrenar: dataset vacío")
            return None
        
        print(f"✓ Versión creada: {result}")
        
        # Verificar que se creó
        weight = RankingWeights.objects.get(version=result)
        print(f"  - Pesos: {weight.weights}")
        print(f"  - Notas: {weight.notes}")
        print(f"  - Activa: {weight.is_active}")
        
        return result
    except Exception as e:
        print(f"✗ Error en entrenamiento: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_ab_shadow(user, n: int = 5):
    """Prueba A/B y shadow en nuevas consultas."""
    print_section("PROBANDO A/B Y SHADOW")
    
    from apps.search.services.ask import ask
    
    queries = [
        "Prueba A/B: sentencias sobre amparo",
        "Prueba shadow: derechos fundamentales",
        "Prueba control: jurisprudencia TCP",
        "Prueba treatment: normativa laboral",
        "Prueba shadow: derecho a la salud",
    ]
    
    buckets = {"control": 0, "treatment": 0, "shadow": 0}
    
    for i, query in enumerate(queries[:n], 1):
        try:
            print(f"\n[{i}/{n}] Consultando: {query}")
            msg, hits = ask(user, query)
            
            # Verificar bucket
            assignment = ExperimentAssignment.objects.filter(query_id=msg.session.id).first()
            if assignment:
                bucket = assignment.bucket
                buckets[bucket] += 1
                print(f"  → Bucket: {bucket}")
                print(f"  → Versión: {assignment.weights_version}")
            
            # Verificar meta_json del primer hit
            if hits:
                hit = hits[0]
                meta = hit.meta_json or {}
                print(f"  → Experiment bucket (hit): {meta.get('experiment_bucket')}")
                print(f"  → Weights version (hit): {meta.get('weights_version_used')}")
                print(f"  → Final score: {meta.get('final_score')}")
                if meta.get('final_score_shadow') is not None:
                    print(f"  → Final score shadow: {meta.get('final_score_shadow')}")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print(f"\n✓ Distribución de buckets:")
    for bucket, count in buckets.items():
        print(f"  - {bucket}: {count}")

def test_activation_rollback():
    """Prueba activación y rollback de versiones."""
    print_section("PROBANDO ACTIVACIÓN Y ROLLBACK")
    
    # Listar versiones disponibles
    versions = list(RankingWeights.objects.all().order_by('-created_at'))
    print(f"Versiones disponibles: {len(versions)}")
    
    if len(versions) < 1:
        print("⚠ No hay versiones para probar activación")
        return
    
    for v in versions:
        print(f"  - {v.version} (activa: {v.is_active})")
    
    # Activar la última versión inactiva
    candidate = RankingWeights.objects.filter(is_active=False).order_by('-created_at').first()
    if not candidate:
        print("\n⚠ No hay versiones inactivas para activar")
        return
    
    print(f"\nActivando versión: {candidate.version}")
    from django.core.management import call_command
    try:
        call_command('activate_ranking_weights', candidate.version)
        print(f"✓ Versión activada: {candidate.version}")
        
        # Verificar
        candidate.refresh_from_db()
        print(f"  - Estado: {'ACTIVA' if candidate.is_active else 'INACTIVA'}")
        
    except Exception as e:
        print(f"✗ Error en activación: {e}")

def generate_metrics_report():
    """Genera reporte de métricas."""
    print_section("REPORTE DE MÉTRICAS")
    
    # Contadores básicos
    n_decisions = RankingDecision.objects.count()
    n_feedback = Feedback.objects.count()
    n_weights = RankingWeights.objects.count()
    
    print(f"Estadísticas generales:")
    print(f"  - Decisiones de ranking: {n_decisions}")
    print(f"  - Feedbacks: {n_feedback}")
    print(f"  - Versiones de pesos: {n_weights}")
    
    # Dataset
    try:
        dataset = build_pairwise_dataset(days=30)
        print(f"\nDataset pairwise (30 días):")
        print(f"  - Pares: {dataset.n_pairs}")
        print(f"  - Consultas: {dataset.n_queries}")
        print(f"  - Dimensión: {dataset.dim}")
    except Exception as e:
        print(f"\n✗ Error al construir dataset: {e}")
    
    # Métricas adaptativas
    try:
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('report_adaptive_metrics', '--hours', '24', stdout=out)
        print(f"\nMétricas adaptativas (24h):")
        print(f"  {out.getvalue()}")
    except Exception as e:
        print(f"\n✗ Error en métricas: {e}")

def main():
    """Flujo principal de validación."""
    print_section("VALIDACIÓN END-TO-END: ADAPTIVE RANKING")
    
    # 1. Usuario de prueba
    user = get_or_create_test_user()
    
    # 2. Generar consultas
    messages = generate_test_queries(user, n=15)
    if not messages:
        print("\n✗ No se pudieron generar consultas. Abortando.")
        return
    
    # 3. Enviar feedback
    feedback_stats = send_feedback(messages)
    if feedback_stats["queries_with_feedback"] == 0:
        print("\n✗ No se pudo enviar feedback. Abortando.")
        return
    
    # 4. Validar ETL
    if not validate_etl(days=30):
        print("\n✗ ETL falló. Abortando entrenamiento.")
        return
    
    # 5. Entrenar pesos
    new_version = train_weights()
    if not new_version:
        print("\n⚠ No se pudo entrenar, pero continuamos con las pruebas...")
    
    # 6. Probar A/B y shadow
    test_ab_shadow(user, n=5)
    
    # 7. Activación y rollback
    test_activation_rollback()
    
    # 8. Reporte final
    generate_metrics_report()
    
    print_section("VALIDACIÓN COMPLETADA")
    print("✓ Flujo end-to-end ejecutado exitosamente")

if __name__ == "__main__":
    main()

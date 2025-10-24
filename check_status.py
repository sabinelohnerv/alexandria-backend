#!/usr/bin/env python
"""
Script para verificar el estado actual del sistema Adaptive Ranking.
Uso: python check_status.py
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.ranking_adaptive.models import RankingWeights, RankingDecision, ExperimentAssignment
from apps.search.models import Feedback, SearchHit, ChatMessage
from apps.ranking_adaptive.utils import build_pairwise_dataset

def main():
    print("="*60)
    print("  ESTADO ACTUAL - ADAPTIVE RANKING")
    print("="*60)
    
    # Contadores
    print("\nCONTADORES:")
    print(f"  - RankingWeights: {RankingWeights.objects.count()}")
    print(f"  - RankingDecision: {RankingDecision.objects.count()}")
    print(f"  - ExperimentAssignment: {ExperimentAssignment.objects.count()}")
    print(f"  - Feedback: {Feedback.objects.count()}")
    print(f"  - SearchHit: {SearchHit.objects.count()}")
    print(f"  - ChatMessage: {ChatMessage.objects.count()}")
    
    # Versión activa
    print("\nVERSIÓN ACTIVA:")
    active = RankingWeights.objects.filter(is_active=True).first()
    if active:
        print(f"  - Versión: {active.version}")
        print(f"  - Pesos: {active.weights}")
        print(f"  - Creada: {active.created_at}")
        print(f"  - Notas: {active.notes}")
    else:
        print("  - (ninguna)")
    
    # Versión candidata
    print("\nVERSIÓN CANDIDATA (última inactiva):")
    candidate = RankingWeights.objects.filter(is_active=False).order_by('-created_at').first()
    if candidate:
        print(f"  - Versión: {candidate.version}")
        print(f"  - Pesos: {candidate.weights}")
        print(f"  - Creada: {candidate.created_at}")
        print(f"  - Notas: {candidate.notes}")
    else:
        print("  - (ninguna)")
    
    # Todas las versiones
    print("\nTODAS LAS VERSIONES:")
    for w in RankingWeights.objects.order_by('-created_at'):
        status = "ACTIVA" if w.is_active else "  inactiva"
        print(f"  {status} - {w.version} - {w.created_at.strftime('%Y-%m-%d %H:%M')}")
    
    # Dataset pairwise
    print("\nDATASET PAIRWISE (30 días):")
    try:
        ds = build_pairwise_dataset(days=30)
        print(f"  - Pares: {ds.n_pairs}")
        print(f"  - Consultas: {ds.n_queries}")
        print(f"  - Dimensión: {ds.dim}")
        print(f"  - Shape Xdiff: {ds.Xdiff.shape}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # Últimas decisiones
    print("\nÚLTIMAS 5 DECISIONES:")
    for d in RankingDecision.objects.order_by('-ts')[:5]:
        print(f"  - Query {d.query_id}, Hit {d.hit_id}, Versión: {d.model_version}, Score CE: {d.score_ce:.3f}")
    
    # Distribución de buckets
    print("\nDISTRIBUCIÓN DE BUCKETS:")
    from django.db.models import Count
    buckets = ExperimentAssignment.objects.values('bucket').annotate(count=Count('id'))
    for b in buckets:
        print(f"  - {b['bucket']}: {b['count']}")
    
    # Feedback reciente
    print("\nFEEDBACK RECIENTE (últimos 10):")
    for fb in Feedback.objects.order_by('-created_at')[:10]:
        target = f"hit {fb.hit_id}" if fb.hit else f"msg {fb.message_id}"
        print(f"  - {fb.label} → {target} (user: {fb.user_id})")
    
    print("\n" + "="*60)
    print("✓ Reporte completado")
    print("="*60)

if __name__ == "__main__":
    main()

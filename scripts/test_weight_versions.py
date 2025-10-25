"""
Test and compare different weight versions on validation data.
Evaluates ranking quality using various metrics.
"""
import os
import sys
import django
from pathlib import Path
import numpy as np
from typing import List, Dict, Tuple
from collections import defaultdict

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from apps.ranking_adaptive.models import RankingDecision, RankingWeights
from apps.ranking_adaptive.utils import _pointwise_label_for_query_hits

def compute_ndcg(relevances: List[int], k: int = 10) -> float:
    """Compute Normalized Discounted Cumulative Gain"""
    if not relevances:
        return 0.0
    
    # DCG
    dcg = sum((2**rel - 1) / np.log2(i + 2) for i, rel in enumerate(relevances[:k]))
    
    # IDCG (ideal DCG with perfect ranking)
    ideal_relevances = sorted(relevances, reverse=True)
    idcg = sum((2**rel - 1) / np.log2(i + 2) for i, rel in enumerate(ideal_relevances[:k]))
    
    return dcg / idcg if idcg > 0 else 0.0

def compute_precision_at_k(relevances: List[int], k: int = 10) -> float:
    """Compute Precision@K"""
    if not relevances or k == 0:
        return 0.0
    return sum(relevances[:k]) / min(k, len(relevances))

def compute_mrr(relevances: List[int]) -> float:
    """Compute Mean Reciprocal Rank"""
    for i, rel in enumerate(relevances, 1):
        if rel > 0:
            return 1.0 / i
    return 0.0

def evaluate_weights_on_query(query_id: int, decisions: List[RankingDecision], 
                               weights: np.ndarray) -> Dict:
    """Evaluate a weight vector on a single query"""
    
    # Get labels for this query
    labels = _pointwise_label_for_query_hits(query_id)
    
    # Filter decisions that have labels
    labeled_decisions = [d for d in decisions if d.hit_id in labels]
    
    if len(labeled_decisions) < 2:
        return None
    
    # Compute scores with new weights
    scores = []
    relevances = []
    
    for d in labeled_decisions:
        if d.signals and len(d.signals) == len(weights):
            score = np.dot(d.signals, weights)
            scores.append((score, labels[d.hit_id]))
    
    if not scores:
        return None
    
    # Sort by score (descending)
    scores.sort(key=lambda x: x[0], reverse=True)
    relevances = [rel for _, rel in scores]
    
    # Compute metrics
    return {
        'ndcg@5': compute_ndcg(relevances, k=5),
        'ndcg@10': compute_ndcg(relevances, k=10),
        'precision@5': compute_precision_at_k(relevances, k=5),
        'precision@10': compute_precision_at_k(relevances, k=10),
        'mrr': compute_mrr(relevances),
        'n_results': len(relevances),
    }

def evaluate_weight_version(version: RankingWeights, days: int = 30) -> Dict:
    """Evaluate a weight version on validation data"""
    
    print(f"\nEvaluating: {version.version}")
    print("-" * 80)
    
    weights = np.array(version.weights)
    
    # Get recent decisions
    since = timezone.now() - timedelta(days=days)
    decisions_qs = (RankingDecision.objects
                   .filter(ts__gte=since)
                   .order_by('query_id', 'shown_pos')
                   .only('query_id', 'hit_id', 'shown_pos', 'signals'))
    
    # Group by query
    by_query = defaultdict(list)
    for d in decisions_qs:
        by_query[d.query_id].append(d)
    
    print(f"Found {len(by_query)} queries with decisions")
    
    # Evaluate on each query
    query_metrics = []
    for query_id, decisions in by_query.items():
        metrics = evaluate_weights_on_query(query_id, decisions, weights)
        if metrics:
            query_metrics.append(metrics)
    
    if not query_metrics:
        print("No queries could be evaluated!")
        return None
    
    print(f"Successfully evaluated on {len(query_metrics)} queries")
    
    # Aggregate metrics
    aggregated = {
        'ndcg@5': np.mean([m['ndcg@5'] for m in query_metrics]),
        'ndcg@10': np.mean([m['ndcg@10'] for m in query_metrics]),
        'precision@5': np.mean([m['precision@5'] for m in query_metrics]),
        'precision@10': np.mean([m['precision@10'] for m in query_metrics]),
        'mrr': np.mean([m['mrr'] for m in query_metrics]),
        'n_queries': len(query_metrics),
    }
    
    # Print results
    print(f"\nResults:")
    print(f"  NDCG@5:      {aggregated['ndcg@5']:.4f}")
    print(f"  NDCG@10:     {aggregated['ndcg@10']:.4f}")
    print(f"  Precision@5: {aggregated['precision@5']:.4f}")
    print(f"  Precision@10:{aggregated['precision@10']:.4f}")
    print(f"  MRR:         {aggregated['mrr']:.4f}")
    print(f"  Queries:     {aggregated['n_queries']}")
    
    return aggregated

def compare_all_versions(days: int = 30):
    """Compare all weight versions"""
    
    print("="*80)
    print("COMPARING ALL WEIGHT VERSIONS")
    print("="*80)
    
    versions = RankingWeights.objects.order_by('-created_at')
    
    if not versions.exists():
        print("No weight versions found!")
        return
    
    print(f"\nFound {versions.count()} versions to evaluate")
    
    results = []
    
    for version in versions:
        metrics = evaluate_weight_version(version, days=days)
        if metrics:
            results.append({
                'version': version.version,
                'is_active': version.is_active,
                'created_at': version.created_at,
                'weights': version.weights,
                'metrics': metrics,
            })
    
    if not results:
        print("\nNo versions could be evaluated!")
        return
    
    # Print comparison table
    print("\n" + "="*80)
    print("COMPARISON TABLE")
    print("="*80)
    
    # Sort by NDCG@10
    results.sort(key=lambda x: x['metrics']['ndcg@10'], reverse=True)
    
    print(f"\n{'Rank':<6} {'Version':<35} {'NDCG@10':<10} {'P@10':<10} {'MRR':<10} {'Status':<10}")
    print("-" * 100)
    
    for i, result in enumerate(results, 1):
        version = result['version']
        ndcg10 = result['metrics']['ndcg@10']
        p10 = result['metrics']['precision@10']
        mrr = result['metrics']['mrr']
        status = "ACTIVE" if result['is_active'] else ""
        
        print(f"{i:<6} {version:<35} {ndcg10:<10.4f} {p10:<10.4f} {mrr:<10.4f} {status:<10}")
    
    # Best version
    best = results[0]
    print(f"\n{'='*80}")
    print(f"BEST PERFORMING VERSION: {best['version']}")
    print(f"{'='*80}")
    print(f"NDCG@10:     {best['metrics']['ndcg@10']:.4f}")
    print(f"NDCG@5:      {best['metrics']['ndcg@5']:.4f}")
    print(f"Precision@10:{best['metrics']['precision@10']:.4f}")
    print(f"Precision@5: {best['metrics']['precision@5']:.4f}")
    print(f"MRR:         {best['metrics']['mrr']:.4f}")
    print(f"Weights:     {best['weights']}")
    
    if not best['is_active']:
        print(f"\n⚠ This version is NOT currently active!")
        print(f"To activate it, run:")
        print(f"  python manage.py activate_ranking_weights {best['version']}")
    else:
        print(f"\n✓ This version is already active!")
    
    # Show improvement over current active
    active_results = [r for r in results if r['is_active']]
    if active_results and not best['is_active']:
        active = active_results[0]
        improvement = (best['metrics']['ndcg@10'] - active['metrics']['ndcg@10']) / active['metrics']['ndcg@10'] * 100
        print(f"\nImprovement over active version: {improvement:+.2f}%")
    
    print("\n" + "="*80)
    
    return best['version']

def main():
    """Main testing workflow"""
    
    import argparse
    parser = argparse.ArgumentParser(description='Test and compare weight versions')
    parser.add_argument('--days', type=int, default=30, help='Number of days of data to use')
    parser.add_argument('--version', type=str, help='Test specific version only')
    
    args = parser.parse_args()
    
    if args.version:
        # Test specific version
        try:
            version = RankingWeights.objects.get(version=args.version)
            evaluate_weight_version(version, days=args.days)
        except RankingWeights.DoesNotExist:
            print(f"Error: Version '{args.version}' not found!")
            return
    else:
        # Compare all versions
        best_version = compare_all_versions(days=args.days)

if __name__ == "__main__":
    main()

"""
Script to check available training data for adaptive ranking.
Verifies queries, feedback, ranking decisions, and current weights.
"""
import os
import sys
import django
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from apps.search.models import ChatMessage, SearchHit, Feedback
from apps.ranking_adaptive.models import RankingDecision, RankingWeights
from apps.ranking_adaptive.utils import build_pairwise_dataset

def main():
    print("=" * 80)
    print("CHECKING TRAINING DATA FOR ADAPTIVE RANKING")
    print("=" * 80)
    
    # 1. Check queries (ChatMessages)
    print("\n1. QUERIES (ChatMessages)")
    print("-" * 80)
    total_messages = ChatMessage.objects.count()
    user_messages = ChatMessage.objects.filter(role=ChatMessage.ROLE_USER).count()
    assistant_messages = ChatMessage.objects.filter(role=ChatMessage.ROLE_ASSISTANT).count()
    
    print(f"Total messages: {total_messages}")
    print(f"  - User queries: {user_messages}")
    print(f"  - Assistant responses: {assistant_messages}")
    
    # Recent queries
    last_30_days = timezone.now() - timedelta(days=30)
    recent_messages = ChatMessage.objects.filter(
        role=ChatMessage.ROLE_USER,
        created_at__gte=last_30_days
    ).count()
    print(f"  - User queries (last 30 days): {recent_messages}")
    
    # 2. Check SearchHits
    print("\n2. SEARCH HITS")
    print("-" * 80)
    total_hits = SearchHit.objects.count()
    recent_hits = SearchHit.objects.filter(created_at__gte=last_30_days).count()
    
    print(f"Total search hits: {total_hits}")
    print(f"  - Recent hits (last 30 days): {recent_hits}")
    
    # Hits with reranking scores
    hits_with_rerank = SearchHit.objects.filter(score_rerank__isnull=False).count()
    print(f"  - Hits with rerank scores: {hits_with_rerank}")
    
    # 3. Check Feedback
    print("\n3. FEEDBACK")
    print("-" * 80)
    total_feedback = Feedback.objects.count()
    useful_feedback = Feedback.objects.filter(label=Feedback.LABEL_USEFUL).count()
    not_useful_feedback = Feedback.objects.filter(label=Feedback.LABEL_NOT_USEFUL).count()
    
    print(f"Total feedback: {total_feedback}")
    print(f"  - Useful: {useful_feedback}")
    print(f"  - Not useful: {not_useful_feedback}")
    
    # Recent feedback
    recent_feedback = Feedback.objects.filter(created_at__gte=last_30_days).count()
    print(f"  - Recent feedback (last 30 days): {recent_feedback}")
    
    # Feedback on hits vs messages
    hit_feedback = Feedback.objects.filter(hit__isnull=False).count()
    message_feedback = Feedback.objects.filter(message__isnull=False, hit__isnull=True).count()
    
    print(f"  - Feedback on hits (chunks): {hit_feedback}")
    print(f"  - Feedback on messages: {message_feedback}")
    
    # 4. Check RankingDecisions
    print("\n4. RANKING DECISIONS")
    print("-" * 80)
    total_decisions = RankingDecision.objects.count()
    recent_decisions = RankingDecision.objects.filter(ts__gte=last_30_days).count()
    
    print(f"Total ranking decisions: {total_decisions}")
    print(f"  - Recent decisions (last 30 days): {recent_decisions}")
    
    if total_decisions > 0:
        # Check signal dimensions
        sample_decision = RankingDecision.objects.filter(signals__isnull=False).first()
        if sample_decision and sample_decision.signals:
            signal_dim = len(sample_decision.signals)
            print(f"  - Signal dimension: {signal_dim}")
            if sample_decision.signal_names:
                print(f"  - Signal names: {', '.join(sample_decision.signal_names)}")
        
        # Unique queries with decisions
        unique_queries = RankingDecision.objects.values('query_id').distinct().count()
        print(f"  - Unique queries with decisions: {unique_queries}")
    
    # 5. Check Current Weights
    print("\n5. CURRENT WEIGHTS")
    print("-" * 80)
    total_weights = RankingWeights.objects.count()
    active_weights = RankingWeights.objects.filter(is_active=True).first()
    
    print(f"Total weight versions: {total_weights}")
    
    if active_weights:
        print(f"\nActive version: {active_weights.version}")
        print(f"  - Created: {active_weights.created_at}")
        print(f"  - Weights: {active_weights.weights}")
        print(f"  - Notes: {active_weights.notes}")
    else:
        print("No active weights found!")
    
    # List all weight versions
    if total_weights > 0:
        print("\nAll weight versions:")
        for w in RankingWeights.objects.order_by('-created_at'):
            status = "ACTIVE" if w.is_active else "inactive"
            print(f"  - {w.version} ({status}) - {w.created_at.strftime('%Y-%m-%d %H:%M')}")
    
    # 6. Build pairwise dataset to check training readiness
    print("\n6. PAIRWISE DATASET (TRAINING READINESS)")
    print("-" * 80)
    
    for days in [7, 14, 30, 60]:
        print(f"\nTrying to build dataset with last {days} days:")
        try:
            ds = build_pairwise_dataset(days=days)
            print(f"  ✓ Success!")
            print(f"    - Queries: {ds.n_queries}")
            print(f"    - Pairs: {ds.n_pairs}")
            print(f"    - Dimension: {ds.dim}")
            print(f"    - Dataset shape: {ds.Xdiff.shape}")
            
            if ds.n_pairs > 0:
                print(f"    - Ready for training: YES")
            else:
                print(f"    - Ready for training: NO (no pairs generated)")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    # 7. Summary and recommendations
    print("\n" + "=" * 80)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 80)
    
    if total_feedback == 0:
        print("⚠ WARNING: No feedback data available. Cannot train without feedback!")
        print("  → Users need to provide useful/not_useful feedback on search results.")
    elif hit_feedback < 10:
        print(f"⚠ WARNING: Very few hit-level feedbacks ({hit_feedback}). Training may be unstable.")
        print("  → Collect more feedback on individual search hits (chunks).")
    elif recent_decisions == 0:
        print("⚠ WARNING: No ranking decisions recorded. Check if ranking is being logged.")
    else:
        print("✓ Data looks ready for training!")
        print(f"  - {hit_feedback} hit-level feedbacks available")
        print(f"  - {recent_decisions} ranking decisions in last 30 days")
        
        # Try to build dataset
        ds = build_pairwise_dataset(days=30)
        if ds.n_pairs > 0:
            print(f"  - {ds.n_pairs} training pairs can be generated")
            print("\n✓ READY TO TRAIN!")
        else:
            print("  - But no training pairs could be generated.")
            print("  → Check if feedbacks are properly linked to ranking decisions.")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()

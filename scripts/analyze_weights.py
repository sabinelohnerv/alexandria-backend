"""
Detailed analysis of weight versions and their characteristics.
"""
import os
import sys
import django
from pathlib import Path
import numpy as np

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.ranking_adaptive.models import RankingWeights, RankingDecision
from datetime import datetime

def analyze_weights():
    """Analyze all weight versions"""
    
    print("="*80)
    print("WEIGHT VERSION ANALYSIS")
    print("="*80)
    
    versions = RankingWeights.objects.order_by('-created_at')
    
    if not versions.exists():
        print("No weight versions found!")
        return
    
    # Get signal names from a recent decision
    sample_decision = RankingDecision.objects.filter(signal_names__isnull=False).first()
    signal_names = sample_decision.signal_names if sample_decision else ['Signal 0', 'Signal 1', 'Signal 2', 'Signal 3']
    
    print(f"\nSignal names: {signal_names}")
    print(f"Found {versions.count()} versions\n")
    
    # Prepare data for visualization
    version_data = []
    
    for version in versions:
        weights = np.array(version.weights)
        version_data.append({
            'version': version.version,
            'weights': weights,
            'is_active': version.is_active,
            'created_at': version.created_at,
            'notes': version.notes,
        })
    
    # Print detailed comparison
    print("="*80)
    print("WEIGHT COMPARISON")
    print("="*80)
    
    header = f"{'Version':<35}"
    for name in signal_names:
        header += f" {name[:12]:<12}"
    header += " Status"
    print(header)
    print("-" * 120)
    
    for vdata in version_data:
        row = f"{vdata['version']:<35}"
        for w in vdata['weights']:
            row += f" {w:<12.6f}"
        status = "ACTIVE" if vdata['is_active'] else ""
        row += f" {status}"
        print(row)
    
    # Calculate statistics
    print("\n" + "="*80)
    print("WEIGHT STATISTICS")
    print("="*80)
    
    all_weights = np.array([vdata['weights'] for vdata in version_data])
    
    print(f"\nPer signal statistics:")
    for i, name in enumerate(signal_names):
        signal_weights = all_weights[:, i]
        print(f"\n{name}:")
        print(f"  Mean:   {np.mean(signal_weights):.6f}")
        print(f"  Std:    {np.std(signal_weights):.6f}")
        print(f"  Min:    {np.min(signal_weights):.6f}")
        print(f"  Max:    {np.max(signal_weights):.6f}")
        print(f"  Range:  {np.max(signal_weights) - np.min(signal_weights):.6f}")
    
    # Weight distribution
    print("\n" + "="*80)
    print("WEIGHT DISTRIBUTION (AVERAGE)")
    print("="*80)
    
    avg_weights = np.mean(all_weights, axis=0)
    total = np.sum(avg_weights)
    
    print(f"\nAverage weights (normalized to sum=1):")
    for i, name in enumerate(signal_names):
        pct = (avg_weights[i] / total) * 100 if total > 0 else 0
        print(f"  {name:<20}: {avg_weights[i]:.6f} ({pct:.2f}%)")
    
    # Skip visualization due to numpy compatibility issues
    print("\nNote: Visualization skipped (matplotlib/numpy compatibility issues)")
    
    # Analyze weight changes over time
    print("\n" + "="*80)
    print("WEIGHT EVOLUTION")
    print("="*80)
    
    if len(version_data) > 1:
        # Sort by creation time
        sorted_versions = sorted(version_data, key=lambda x: x['created_at'])
        
        print(f"\nWeight changes from oldest to newest:")
        for i in range(1, len(sorted_versions)):
            prev = sorted_versions[i-1]
            curr = sorted_versions[i]
            
            changes = curr['weights'] - prev['weights']
            max_change = np.max(np.abs(changes))
            
            print(f"\n{prev['version']} → {curr['version']}")
            print(f"  Max change: {max_change:.6f}")
            for j, name in enumerate(signal_names):
                if abs(changes[j]) > 0.001:
                    print(f"    {name}: {changes[j]:+.6f}")
    
    print("\n" + "="*80)


def main():
    analyze_weights()

if __name__ == "__main__":
    main()

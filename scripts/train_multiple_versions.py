"""
Comprehensive training script for adaptive ranking weights.
Trains multiple versions with different hyperparameters and compares results.
"""
import os
import sys
import django
from pathlib import Path
import numpy as np
from typing import List, Dict, Tuple
import json
from datetime import datetime

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import transaction
from django.utils import timezone
from apps.ranking_adaptive.models import RankingWeights
from apps.ranking_adaptive.utils import build_pairwise_dataset
from apps.ranking_adaptive.tasks import TrainConfig, _get_prior_w, _train_pairwise, _project_constraints

class TrainingExperiment:
    """Manages training experiments with different configurations"""
    
    def __init__(self, days: int = 30):
        self.days = days
        self.results = []
        
    def train_version(self, name: str, config: TrainConfig, notes: str = "") -> Dict:
        """Train a single version with given config"""
        print(f"\n{'='*80}")
        print(f"Training: {name}")
        print(f"{'='*80}")
        print(f"Config: lr={config.lr}, steps={config.steps}, l2={config.l2}, days={config.days}")
        print(f"        clip_rel={config.clip_rel}, nonneg_idx={config.nonneg_idx}")
        
        # Build dataset
        print("\nBuilding pairwise dataset...")
        ds = build_pairwise_dataset(days=config.days)
        
        if ds.dim <= 0 or ds.n_pairs == 0:
            print("ERROR: Empty dataset, cannot train!")
            return None
        
        print(f"Dataset: {ds.n_queries} queries, {ds.n_pairs} pairs, dim={ds.dim}")
        
        # Get prior weights
        prior = _get_prior_w(ds.dim)
        print(f"Prior weights: {prior}")
        
        # Train
        print("\nTraining...")
        w_new = _train_pairwise(prior, ds.Xdiff, ds.y, config)
        print(f"New weights: {w_new}")
        
        # Calculate training metrics
        pred = ds.Xdiff.dot(w_new)
        accuracy = np.mean((pred > 0).astype(float) == ds.y)
        loss = np.mean(np.log(1 + np.exp(-pred * ds.y)))
        
        print(f"\nTraining metrics:")
        print(f"  - Accuracy: {accuracy:.4f}")
        print(f"  - Log loss: {loss:.4f}")
        
        # Calculate weight changes
        weight_changes = w_new - prior
        max_change = np.max(np.abs(weight_changes))
        print(f"  - Max weight change: {max_change:.4f}")
        print(f"  - Weight changes: {weight_changes}")
        
        # Save to database
        version_name = f"{name}_{timezone.now():%Y%m%d_%H%M%S}"
        full_notes = f"{notes}\nConfig: lr={config.lr} steps={config.steps} l2={config.l2} days={config.days}\n"
        full_notes += f"Metrics: acc={accuracy:.4f} loss={loss:.4f} pairs={ds.n_pairs}"
        
        with transaction.atomic():
            weight_obj = RankingWeights.objects.create(
                version=version_name,
                weights=list(map(float, w_new)),
                notes=full_notes,
                is_active=False,
            )
        
        print(f"\n✓ Saved as version: {version_name}")
        
        result = {
            'version': version_name,
            'name': name,
            'weights': list(w_new),
            'prior': list(prior),
            'config': {
                'lr': config.lr,
                'steps': config.steps,
                'l2': config.l2,
                'days': config.days,
                'clip_rel': config.clip_rel,
                'nonneg_idx': config.nonneg_idx,
            },
            'metrics': {
                'accuracy': float(accuracy),
                'loss': float(loss),
                'n_pairs': ds.n_pairs,
                'n_queries': ds.n_queries,
                'max_change': float(max_change),
            }
        }
        
        self.results.append(result)
        return result
    
    def run_experiments(self):
        """Run multiple training experiments with different configurations"""
        
        print("\n" + "="*80)
        print("STARTING TRAINING EXPERIMENTS")
        print("="*80)
        
        # Experiment 1: Conservative (small learning rate, high regularization)
        config1 = TrainConfig(
            lr=1e-3,
            steps=1000,
            l2=0.3,
            days=self.days,
            nonneg_idx=(0, 1),
            clip_rel=0.3
        )
        self.train_version(
            name="conservative",
            config=config1,
            notes="Conservative training: low lr, high l2, tight clip"
        )
        
        # Experiment 2: Balanced (medium settings)
        config2 = TrainConfig(
            lr=5e-3,
            steps=800,
            l2=0.2,
            days=self.days,
            nonneg_idx=(0, 1),
            clip_rel=0.5
        )
        self.train_version(
            name="balanced",
            config=config2,
            notes="Balanced training: medium lr, medium l2, moderate clip"
        )
        
        # Experiment 3: Aggressive (higher learning rate, lower regularization)
        config3 = TrainConfig(
            lr=1e-2,
            steps=1200,
            l2=0.1,
            days=self.days,
            nonneg_idx=(0, 1),
            clip_rel=0.7
        )
        self.train_version(
            name="aggressive",
            config=config3,
            notes="Aggressive training: high lr, low l2, loose clip"
        )
        
        # Experiment 4: Long training (more steps)
        config4 = TrainConfig(
            lr=3e-3,
            steps=2000,
            l2=0.15,
            days=self.days,
            nonneg_idx=(0, 1),
            clip_rel=0.5
        )
        self.train_version(
            name="long_training",
            config=config4,
            notes="Long training: many steps, moderate settings"
        )
        
        # Experiment 5: Recent data only (7 days)
        config5 = TrainConfig(
            lr=5e-3,
            steps=800,
            l2=0.2,
            days=7,
            nonneg_idx=(0, 1),
            clip_rel=0.5
        )
        self.train_version(
            name="recent_only",
            config=config5,
            notes="Recent data: only last 7 days"
        )
        
        # Experiment 6: All historical data (60 days)
        config6 = TrainConfig(
            lr=5e-3,
            steps=800,
            l2=0.25,
            days=60,
            nonneg_idx=(0, 1),
            clip_rel=0.5
        )
        self.train_version(
            name="historical",
            config=config6,
            notes="Historical data: last 60 days, higher l2 for stability"
        )
    
    def print_summary(self):
        """Print summary of all experiments"""
        print("\n" + "="*80)
        print("TRAINING SUMMARY")
        print("="*80)
        
        if not self.results:
            print("No successful training runs!")
            return
        
        print(f"\nTrained {len(self.results)} versions:\n")
        
        # Sort by accuracy
        sorted_results = sorted(self.results, key=lambda x: x['metrics']['accuracy'], reverse=True)
        
        print(f"{'Rank':<6} {'Name':<20} {'Version':<30} {'Accuracy':<10} {'Loss':<10} {'Pairs':<8}")
        print("-" * 100)
        
        for i, result in enumerate(sorted_results, 1):
            name = result['name']
            version = result['version']
            acc = result['metrics']['accuracy']
            loss = result['metrics']['loss']
            pairs = result['metrics']['n_pairs']
            
            print(f"{i:<6} {name:<20} {version:<30} {acc:<10.4f} {loss:<10.4f} {pairs:<8}")
        
        # Best version
        best = sorted_results[0]
        print(f"\n{'='*80}")
        print(f"BEST VERSION: {best['version']}")
        print(f"{'='*80}")
        print(f"Name: {best['name']}")
        print(f"Accuracy: {best['metrics']['accuracy']:.4f}")
        print(f"Loss: {best['metrics']['loss']:.4f}")
        print(f"Weights: {best['weights']}")
        print(f"\nConfig:")
        for key, val in best['config'].items():
            print(f"  {key}: {val}")
        
        # Save results to JSON
        output_file = BASE_DIR / 'scripts' / f'training_results_{datetime.now():%Y%m%d_%H%M%S}.json'
        with open(output_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'results': self.results,
                'best_version': best['version']
            }, f, indent=2)
        
        print(f"\n✓ Results saved to: {output_file}")
        
        return best['version']

def main():
    """Main training workflow"""
    
    # Run experiments
    experiment = TrainingExperiment(days=30)
    experiment.run_experiments()
    
    # Print summary
    best_version = experiment.print_summary()
    
    print("\n" + "="*80)
    print("NEXT STEPS")
    print("="*80)
    print(f"\n1. Test the versions using:")
    print(f"   python scripts/test_weight_versions.py")
    print(f"\n2. Activate the best version using:")
    print(f"   python manage.py activate_ranking_weights {best_version}")
    print(f"\n3. Monitor performance using:")
    print(f"   python manage.py report_adaptive_metrics --hours 24")
    print("\n" + "="*80)

if __name__ == "__main__":
    main()

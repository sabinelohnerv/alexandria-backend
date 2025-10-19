# ranking_adaptive/tasks.py
from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from django.db import transaction
from django.utils import timezone
from celery import shared_task
from .models import RankingWeights
from .utils import build_pairwise_dataset

@dataclass
class TrainConfig:
    lr: float = 5e-3
    steps: int = 800
    l2: float = 0.2
    days: int = 30
    nonneg_idx: tuple = (0, 1)
    clip_rel: float = 0.5

def _get_prior_w(dim: int) -> np.ndarray:
    row = RankingWeights.objects.filter(is_active=True).order_by('-created_at').first()
    if row and row.weights and len(row.weights) == dim:
        return np.array(row.weights, dtype=float)
    return np.zeros(dim, dtype=float)

def _project_constraints(w: np.ndarray, prior: np.ndarray, cfg: TrainConfig) -> np.ndarray:
    lo = prior * (1.0 - cfg.clip_rel)
    hi = prior * (1.0 + cfg.clip_rel)
    w = np.minimum(np.maximum(w, lo), hi)
    for i in cfg.nonneg_idx:
        w[i] = max(0.0, w[i])
    return w

def _train_pairwise(prior: np.ndarray, Xdiff: np.ndarray, y: np.ndarray, cfg: TrainConfig) -> np.ndarray:
    w = prior.copy()
    for _ in range(cfg.steps):
        pred = Xdiff.dot(w)
        sigm = 1.0 / (1.0 + np.exp(pred))      # sigmoid(-pred) con y=+1
        grad = Xdiff.T.dot(-sigm) + 2.0 * cfg.l2 * (w - prior)
        w = w - cfg.lr * grad
        w = _project_constraints(w, prior, cfg)
    return w

@shared_task(name="ranking_adaptive.train_signal_weights", queue="training", ignore_result=True, soft_time_limit=300, time_limit=600)
def train_signal_weights(days: int = 30,
                         lr: float = 5e-3,
                         steps: int = 800,
                         l2: float = 0.2,
                         nonneg_idx: tuple = (0,1),
                         clip_rel: float = 0.5) -> str:
    cfg = TrainConfig(lr=lr, steps=steps, l2=l2, days=days, nonneg_idx=nonneg_idx, clip_rel=clip_rel)
    ds = build_pairwise_dataset(days=cfg.days)

    if ds.dim <= 0:
        return "NOOP_EMPTY_DATASET"
    prior = _get_prior_w(ds.dim)
    if prior.shape[0] != ds.dim:
        prior = np.zeros(ds.dim, dtype=float)

    if ds.n_pairs == 0 or ds.Xdiff.shape[0] == 0:
        return "NOOP_EMPTY_DATASET"

    w_new = _train_pairwise(prior, ds.Xdiff, ds.y, cfg)

    version_name = f"w_{timezone.now():%Y%m%d_%H%M%S}"
    with transaction.atomic():
        RankingWeights.objects.create(
            version=version_name,
            weights=list(map(float, w_new)),
            notes=f"pairwise training: days={cfg.days} pairs={ds.n_pairs} l2={cfg.l2} steps={cfg.steps}",
            is_active=False,
        )
    return version_name

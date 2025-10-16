from dataclasses import dataclass
from typing import List, Sequence
from django.conf import settings
from .models import RankingWeights

@dataclass
class ActiveWeights:
    version: str
    w: List[float]
    alpha: float

def get_active_weights() -> ActiveWeights:
    row = RankingWeights.objects.filter(is_active=True).order_by('-created_at').first()
    if not row:
        # fallback: todos 0 para señales y alpha = 1.0 (solo CE)
        return ActiveWeights(version="default", w=[], alpha=getattr(settings,'ADAPTIVE_RANKING_ALPHA',1.0))
    return ActiveWeights(version=row.version, w=row.weights, alpha=getattr(settings,'ADAPTIVE_RANKING_ALPHA',1.0))

def linear_score(score_ce: float, signals: Sequence[float], aw: ActiveWeights) -> float:
    # asume len(signals) == len(aw.w); si no, ignora señales
    if not aw.w or len(aw.w) != len(signals):
        return aw.alpha * score_ce
    return aw.alpha * score_ce + sum(wi*xi for wi,xi in zip(aw.w, signals))

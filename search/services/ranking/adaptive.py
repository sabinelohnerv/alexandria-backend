from typing import List
from django.conf import settings
from .settings import get_setting, RANK_WEIGHTS_DEFAULT

_LOCAL_SIGNAL_ORDER = ["vigente", "peso_org", "match_id", "recencia"]

def _weights_from_settings_dict() -> List[float]:
    W = get_setting("RANK_WEIGHTS", RANK_WEIGHTS_DEFAULT)
    mapping = {
        "vigente": float(W.get("W_VIG", RANK_WEIGHTS_DEFAULT["W_VIG"])),
        "peso_org": float(W.get("W_ORG", RANK_WEIGHTS_DEFAULT["W_ORG"])),
        "match_id": float(W.get("W_ID",  RANK_WEIGHTS_DEFAULT["W_ID"])),
        "recencia": float(W.get("W_T",   RANK_WEIGHTS_DEFAULT["W_T"])),
    }
    return [mapping[name] for name in _LOCAL_SIGNAL_ORDER]

def get_active_signal_weights() -> List[float]:
    # si hay pesos en DB (RankingWeights) úsalos tal cual:
    try:
        from ranking_adaptive.models import RankingWeights
        row = RankingWeights.objects.filter(is_active=True).order_by('-created_at').first()
        if row and row.weights:
            return list(map(float, row.weights))
    except Exception:
        pass
    # fallback a settings en el orden local
    return _weights_from_settings_dict()

def get_alpha_ce() -> float:
    W = get_setting("RANK_WEIGHTS", RANK_WEIGHTS_DEFAULT)
    return float(W.get("W_CE", RANK_WEIGHTS_DEFAULT["W_CE"]))

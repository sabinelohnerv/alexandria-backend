from django.conf import settings

# Defaults
RANK_WEIGHTS_DEFAULT = {
    "W_CE": 1.0,
    "W_VIG": 0.75,
    "W_ORG": 0.35,
    "W_ID": 0.90,
    "W_T": 0.25,
}

ORG_WEIGHTS_DEFAULT = {
    "tcp": 1.0, "TCP": 1.0,
    "tsj": 0.8, "TSJ": 0.8,
    "sala": 0.6, "SALA": 0.6,
    "ley": 0.7, "LEY": 0.7,
    "cpe": 0.9, "CPE": 0.9,
    "alp": 0.7, "ALP": 0.7,
    "otros": 0.3, "OTROS": 0.3,
}

RECENCY_SOURCES_DEFAULT = {"tcp", "tsj", "sala"}
RECENCY_HALFLIFE_DAYS_DEFAULT = 4 * 365  # ≈ 4 años


def get_setting(name: str, default):
    return getattr(settings, name, default)

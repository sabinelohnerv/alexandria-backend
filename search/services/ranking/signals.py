import re
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, date
from typing import Sequence, Dict, Any
from documents.models import Document
from .settings import (
    get_setting,
    RANK_WEIGHTS_DEFAULT,
    ORG_WEIGHTS_DEFAULT,
    RECENCY_SOURCES_DEFAULT,
    RECENCY_HALFLIFE_DAYS_DEFAULT,
)

SIGNAL_ORDER = ["vigente", "peso_org", "match_id", "recencia"]

def _norm_slug(s: Optional[str]) -> str:
    if not s:
        return ""
    import re as _re
    return _re.sub(r"[^a-z0-9]+", "", s.lower())

def _to_unit(x: float) -> float:
    # asegura [0,1]
    if x is None:
        return 0.0
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0

def _infer_slug_from_storage(doc: Document) -> Optional[str]:
    sk = (doc.storage_key or "").lower()
    if "/tcp/" in sk:
        return "tcp"
    if "/tsj/" in sk:
        return "tsj"
    if "/normativa/" in sk and "/cpc/" in sk:
        return "cpc"
    if "/normativa/" in sk and ("cpe" in sk or "constitucion" in sk or "constitución" in sk):
        return "cpe"
    return None


def _get_source_slug(doc: Document) -> str:
    if getattr(doc, "source_slug", None):
        return _norm_slug(doc.source_slug)
    s = _infer_slug_from_storage(doc)
    if s:
        return s
    title = (getattr(doc, "title", "") or "").lower()
    if "constitucional" in title or "scp" in title or "sc " in title:
        return "tcp"
    if "auto supremo" in title or " as " in title:
        return "tsj"
    if "ley" in title:
        return "ley"
    if "constitución" in title or "cpe" in title:
        return "cpe"
    return "otros"


def _deep_get(d: Any, keys: List[str]) -> Optional[str]:
    if not isinstance(d, dict):
        return None
    for k, v in d.items():
        if isinstance(v, dict):
            r = _deep_get(v, keys)
            if r is not None:
                return r
        else:
            if k.lower() in keys:
                return str(v)
    return None


def _is_vigente(doc: Document) -> bool:
    meta = getattr(doc, "meta", None)
    if isinstance(meta, dict):
        raw = _deep_get(meta, ["vigente", "is_current", "is_active", "vigency", "vigencia"])
        if raw is not None:
            s = str(raw).strip().lower()
            if s in {"0", "false", "no", "derogado", "abrogado", "sin vigencia", "invalido", "inválido"}:
                return False
            if s in {"1", "true", "si", "sí", "vigente", "en vigor", "valido", "válido"}:
                return True
    return True  # sin dato → se asume vigente


def _doc_date(doc: Document) -> Optional[datetime]:
    pd = getattr(doc, "published_date", None)
    if isinstance(pd, date):
        return datetime(pd.year, pd.month, pd.day, tzinfo=timezone.utc)
    year = getattr(doc, "year", None)
    if isinstance(year, int) and 1500 < year < 2100:
        return datetime(year, 7, 1, tzinfo=timezone.utc)
    return None


_ID_PATTERNS = [
    r"\bsc?p?\s*\d+/\d{4}\b",       # SC/SCP 0001/2019
    r"\bas\s*\d+/\d{4}\b",          # AS 123/2020
    r"\bauto\s+supremo\s*\d+/\d{4}\b",
    r"\bsentencia\s+constitucional\s*\d+/\d{4}\b",
    r"\bley\s+\d{1,4}\b",           # Ley 004
    r"\btsj\s*\d+/\d{4}\b",
]

def _extract_ids(raw_query: str) -> List[str]:
    q = raw_query.lower()
    ids: List[str] = []
    for pat in _ID_PATTERNS:
        ids += re.findall(pat, q)
    ids = [re.sub(r"\s+", " ", s.strip()) for s in ids]
    return list(dict.fromkeys(ids))


def _match_exacto_id(doc: Document, query_ids: List[str]) -> bool:
    if not query_ids:
        return False
    title = (getattr(doc, "title", "") or "").lower()
    number = (getattr(doc, "number", "") or "").lower()
    text_ids = [title, number]
    for s in text_ids:
        if not s:
            continue
        for qid in query_ids:
            if qid in s:
                return True
    return False


def _org_weight(doc: Document) -> float:
    org_map = get_setting("ORG_WEIGHTS", ORG_WEIGHTS_DEFAULT)
    authority = (getattr(doc, "authority", None) or "").strip()
    src = _get_source_slug(doc)
    if authority in org_map:
        return float(org_map[authority])
    if src in org_map:
        return float(org_map[src])
    return float(org_map.get("otros", 0.3))


def _recency_score(doc: Document) -> float:
    src = _get_source_slug(doc)
    recency_sources = set(get_setting("RECENCY_SOURCES", RECENCY_SOURCES_DEFAULT))
    if src not in recency_sources:
        return 0.0
    dt = _doc_date(doc)
    if dt is None:
        return 0.0
    now = datetime.now(tz=timezone.utc)
    age_days = max(0.0, (now - dt).days)
    half_life = float(get_setting("RECENCY_HALFLIFE_DAYS", RECENCY_HALFLIFE_DAYS_DEFAULT))
    return float(0.5 ** (age_days / max(1.0, half_life)))

def signals_to_vector(signals: Dict[str, Any]) -> List[float]:
    """
    Convierte  dict de señales -> vector en el orden de SIGNAL_ORDER.
    - vigente, match_id -> 0/1
    - peso_org ya viene ~[0..1]
    - recencia ya está en [0..1] por  half-life
    """
    return [
        1.0 if bool(signals.get("vigente")) else 0.0,         # vigente
        _to_unit(float(signals.get("peso_org", 0.0))),         # peso_org
        1.0 if bool(signals.get("match_id")) else 0.0,         # match_id
        _to_unit(float(signals.get("recencia", 0.0))),         # recencia
    ]

def score_with_weights(s_ce: float, signals: Dict[str, Any],
                       w: Sequence[float], alpha: float) -> float:
    x = signals_to_vector(signals)  
    return alpha * float(s_ce) + sum(wi*xi for wi, xi in zip(w, x))

def compute_legal_signals(query: str, doc: Document) -> Dict[str, Any]:
    ids = _extract_ids(query)
    vigente = _is_vigente(doc)
    match_id = _match_exacto_id(doc, ids)
    org_w = _org_weight(doc)
    rec = _recency_score(doc)
    return {
        "vigente": bool(vigente),
        "match_id": bool(match_id),
        "peso_org": float(org_w),
        "recencia": float(rec),
    }

def combine_final_score(s_ce: float, signals: Dict[str, Any]) -> float:
    W = get_setting("RANK_WEIGHTS", RANK_WEIGHTS_DEFAULT)
    w_ce = float(W.get("W_CE", RANK_WEIGHTS_DEFAULT["W_CE"]))
    w_vig = float(W.get("W_VIG", RANK_WEIGHTS_DEFAULT["W_VIG"]))
    w_org = float(W.get("W_ORG", RANK_WEIGHTS_DEFAULT["W_ORG"]))
    w_id = float(W.get("W_ID", RANK_WEIGHTS_DEFAULT["W_ID"]))
    w_t = float(W.get("W_T", RANK_WEIGHTS_DEFAULT["W_T"]))

    term_vig = 1.0 if signals.get("vigente") else 0.0
    term_id = 1.0 if signals.get("match_id") else 0.0
    term_org = float(signals.get("peso_org", 0.0))
    term_t = float(signals.get("recencia", 0.0))

    return (
        w_ce * float(s_ce)
        + w_vig * term_vig
        + w_org * term_org
        + w_id * term_id
        + w_t * term_t
    )

def combine_final_score_vector(s_ce: float, signals: Dict[str, Any]) -> float:
    from .adaptive import get_active_signal_weights, get_alpha_ce  # import tardío, evita ciclos
    w = get_active_signal_weights()     # [w_vig, w_org, w_id, w_rec]
    alpha = get_alpha_ce()
    x = signals_to_vector(signals)      # [vig, org, id, rec]
    return alpha * float(s_ce) + sum(wi*xi for wi, xi in zip(w, x))
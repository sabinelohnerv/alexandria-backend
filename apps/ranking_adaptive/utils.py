# ranking_adaptive/utils.py
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List
import numpy as np
from .models import RankingDecision
from apps.search.models import Feedback, SearchHit  

@dataclass
class PairDataset:
    Xdiff: np.ndarray   # (n_pairs, d)
    y: np.ndarray       # (n_pairs,)
    n_queries: int
    n_pairs: int
    dim: int

def _pointwise_label_for_query_hits(qid: int) -> Dict[int, int]:
    """
    Devuelve etiquetas pointwise por CHUNK (id de Chunk) dentro de la consulta/message `qid`.
    y=1 si existe Feedback(label='useful') para ese SearchHit; y=0 si 'not_useful'.
    Se resuelve por mayoría; empate → último feedback.
    Nota: Solo se consideran feedbacks a nivel de hit (hit != NULL). Los de message se ignoran.
    """
    from collections import defaultdict

    # Trae todos los feedbacks por hit para este message
    fbs = (Feedback.objects
           .filter(hit__isnull=False, hit__message_id=qid)
           .select_related("hit")
           .only("label", "created_at", "hit__id", "hit__chunk_id"))

    # Agrega votos por chunk_id (porque RankingDecision.hit_id = chunk_id)
    agg = defaultdict(lambda: {"up": 0, "down": 0, "last": None})
    for fb in fbs:
        chunk_id = fb.hit.chunk_id
        if fb.label == Feedback.LABEL_USEFUL:
            agg[chunk_id]["up"] += 1
            agg[chunk_id]["last"] = 1
        elif fb.label == Feedback.LABEL_NOT_USEFUL:
            agg[chunk_id]["down"] += 1
            agg[chunk_id]["last"] = 0

    labels: Dict[int, int] = {}
    for chunk_id, a in agg.items():
        if a["up"] > a["down"]:
            labels[chunk_id] = 1
        elif a["down"] > a["up"]:
            labels[chunk_id] = 0
        else:
            # empate: toma el último voto si existe; si no, ignora
            if a["last"] is not None:
                labels[chunk_id] = int(a["last"])
    return labels

def _ips_position_weight(pos: int) -> float:
    return 1.0 / math.log(1.0 + max(1, pos))

def build_pairwise_dataset(days: int = 30) -> PairDataset:
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    decs_qs = (RankingDecision.objects
               .filter(ts__gte=since)
               .order_by('query_id', 'shown_pos')
               .only('query_id','hit_id','shown_pos','signals'))

    if not decs_qs.exists():
        return PairDataset(np.zeros((0, 0)), np.zeros((0,)), 0, 0, 0)

    # agrupa por consulta/message
    by_query: Dict[int, List[RankingDecision]] = {}
    for d in decs_qs:
        by_query.setdefault(d.query_id, []).append(d)

    # inferir dimensión
    dim = 0
    for rows in by_query.values():
        for r in rows:
            if r.signals:
                dim = len(r.signals)
                break
        if dim:
            break
    if dim == 0:
        return PairDataset(np.zeros((0, 0)), np.zeros((0,)), len(by_query), 0, 0)

    Xdiff_list: List[np.ndarray] = []
    y_list: List[int] = []

    for qid, rows in by_query.items():
        # Etiquetas SOLO por thumbs (útil / no útil) mapeadas a chunk_id
        labels = _pointwise_label_for_query_hits(qid)

        # nos quedamos con decisiones que tengan etiqueta
        labeled = [r for r in rows if r.hit_id in labels]  # r.hit_id == chunk_id
        if len(labeled) < 2:
            continue

        has_pos = any(labels[r.hit_id] == 1 for r in labeled)
        has_neg = any(labels[r.hit_id] == 0 for r in labeled)
        if not (has_pos and has_neg):
            continue

        for i in range(len(labeled)):
            for j in range(i+1, len(labeled)):
                a, b = labeled[i], labeled[j]
                ya, yb = labels[a.hit_id], labels[b.hit_id]
                if ya == yb:
                    continue
                xa = np.asarray(a.signals, dtype=float)
                xb = np.asarray(b.signals, dtype=float)
                # construimos el par en sentido preferido → y = +1
                xdiff = (xa - xb) if ya > yb else (xb - xa)
                w = _ips_position_weight(a.shown_pos) * _ips_position_weight(b.shown_pos)
                Xdiff_list.append(xdiff * w)
                y_list.append(+1)

    if not Xdiff_list:
        return PairDataset(np.zeros((0, dim)), np.zeros((0,)), len(by_query), 0, dim)

    Xdiff = np.vstack(Xdiff_list)
    y = np.asarray(y_list, dtype=float)
    return PairDataset(Xdiff=Xdiff, y=y, n_queries=len(by_query), n_pairs=len(y_list), dim=dim)

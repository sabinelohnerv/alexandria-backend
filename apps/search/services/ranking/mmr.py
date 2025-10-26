from typing import List, Tuple, Dict
import numpy as np
from apps.documents.models import Chunk

def mmr_select(candidates: List[Tuple[Chunk, float, Dict[str, float]]],
               qvec: np.ndarray,
               k: int = 10,
               lambda_: float = 0.7) -> List[Tuple[Chunk, float, Dict[str, float]]]:
    """
    MMR clásico: balancea relevancia al query y disimilitud entre seleccionados.
    candidates: [(chunk, score_base, extra)]
    """
    if not candidates:
        return []
    selected: List[int] = []
    pool = list(range(len(candidates)))
    embs = [np.array(c[0].embedding, dtype=np.float32) for c in candidates]

    def cos(a, b):
        da = np.linalg.norm(a) + 1e-9
        db = np.linalg.norm(b) + 1e-9
        return float(np.dot(a, b) / (da * db))

    for _ in range(min(k, len(pool))):
        best_i, best_val = None, -1e9
        for i in pool:
            rel = cos(embs[i], qvec)  
            div = 0.0
            if selected:
                div = max(cos(embs[i], embs[j]) for j in selected)  # similitud con los ya elegidos
            mmr = lambda_ * rel - (1 - lambda_) * div
            if mmr > best_val:
                best_val = mmr
                best_i = i
        selected.append(best_i)              # type: ignore[arg-type]
        pool.remove(best_i)                  # type: ignore[arg-type]
    return [candidates[i] for i in selected]

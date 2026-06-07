"""
PILLAR VECTOR STORE  —  y = m·x^n
Tracks pillar co-occurrences and cross-pillar correlations.
"""

import math
import time
from typing import List, Dict
from classifier.pillar_classifier import ClassifiedInput

_pillar_registry:   Dict[str, dict] = {}
_correlation_matrix: Dict[str, dict] = {}


def register_pillars(classified: ClassifiedInput):
    active = [classified.core, classified.emotion, classified.functional] + classified.modifiers
    active = [p for p in active if p]

    for pillar in active:
        if pillar not in _pillar_registry:
            _pillar_registry[pillar] = {"count": 0, "weight": 1.0, "last_seen": time.time()}
        _pillar_registry[pillar]["count"]    += 1
        _pillar_registry[pillar]["last_seen"] = time.time()
        _pillar_registry[pillar]["weight"]    = math.log1p(_pillar_registry[pillar]["count"])

    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            key = "_".join(sorted([active[i], active[j]]))
            if key not in _correlation_matrix:
                _correlation_matrix[key] = {"count": 0, "strength": 0.0}
            _correlation_matrix[key]["count"]    += 1
            _correlation_matrix[key]["strength"]  = math.log1p(_correlation_matrix[key]["count"])


def get_top_correlations(pillar: str, top_k: int = 3) -> List[dict]:
    results = []
    for key, data in _correlation_matrix.items():
        parts = key.split("_")
        if pillar in parts:
            other = "_".join(p for p in parts if p != pillar)
            results.append({"pillar": other, **data})
    return sorted(results, key=lambda x: x["strength"], reverse=True)[:top_k]


def get_dominant_pillars(top_k: int = 5) -> List[dict]:
    return sorted(
        [{"pillar": p, **d} for p, d in _pillar_registry.items()],
        key=lambda x: x["weight"], reverse=True
    )[:top_k]


def get_registry()     -> dict: return dict(_pillar_registry)
def get_correlations() -> dict: return dict(_correlation_matrix)
def reset_store():
    _pillar_registry.clear()
    _correlation_matrix.clear()

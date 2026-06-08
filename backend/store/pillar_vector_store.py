"""
PILLAR VECTOR STORE
y = m * x^n
  m = cosine similarity (pillar match strength)
  x = pillar matrix flattened
  n = keyword count

Tracks co-occurrence and correlations between pillars over time.
"""

import math
import time
from typing import List, Dict
from classifier.pillar_classifier import ClassifiedInput

_registry:    Dict[str, dict] = {}
_correlations: Dict[str, dict] = {}


def register_pillars(classified: ClassifiedInput, session_id: str = "", model: str = ""):
    active = [classified.core, classified.emotion, classified.functional] + classified.modifiers
    active = [p for p in active if p]

    for pillar in active:
        if pillar not in _registry:
            _registry[pillar] = {"count": 0, "weight": 1.0,
                                  "last_seen": time.time(),
                                  "sessions": set(), "models": set()}
        _registry[pillar]["count"]    += 1
        _registry[pillar]["last_seen"] = time.time()
        # y = m * x^n → weight grows logarithmically with count
        _registry[pillar]["weight"]    = classified.core_score * math.log1p(_registry[pillar]["count"])
        if session_id:
            _registry[pillar]["sessions"].add(session_id)
        if model:
            _registry[pillar]["models"].add(model)

    # Pairwise correlations
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            key = "_".join(sorted([active[i], active[j]]))
            if key not in _correlations:
                _correlations[key] = {"count": 0, "strength": 0.0}
            _correlations[key]["count"]    += 1
            _correlations[key]["strength"]  = math.log1p(_correlations[key]["count"])


def get_top_correlations(pillar: str, top_k: int = 3) -> List[dict]:
    results = []
    for key, data in _correlations.items():
        parts = key.split("_")
        if pillar in parts:
            other = "_".join(p for p in parts if p != pillar)
            results.append({"pillar": other, **data})
    return sorted(results, key=lambda x: x["strength"], reverse=True)[:top_k]


def get_dominant_pillars(top_k: int = 5) -> List[dict]:
    return sorted(
        [{"pillar": p, "count": d["count"], "weight": d["weight"]}
         for p, d in _registry.items()],
        key=lambda x: x["weight"], reverse=True
    )[:top_k]


def get_registry()     -> dict: return {k: {**v, "sessions": list(v.get("sessions", set())), "models": list(v.get("models", set()))} for k, v in _registry.items()}
def get_correlations() -> dict: return dict(_correlations)

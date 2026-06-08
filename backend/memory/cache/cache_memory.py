"""
CACHE MEMORY — Hot Cache Layer
Implements the vector field M(x,t) from the paper.

Update rule:  M(x,t) = (1-α)·M(x,t-1) + α·I(x,t)
Decay:        M(x,t) = M(x,t₀)·e^(-λ(t-t₀))
λ_cache = 1.0 (minutes scale)
ε = 0.05 (void threshold)

On void: slot moves to Recall Store (not deleted).
"""

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from classifier.pillar_classifier import ClassifiedInput

ALPHA          = 0.4
LAMBDA_CACHE   = 1.0
VOID_THRESHOLD = 0.05

@dataclass
class CacheSlot:
    key:          str
    value:        str
    strength:     float
    timestamp:    float
    pillar:       str
    access_count: int   = 1
    core:         str   = ""
    emotion:      str   = ""
    functional:   str   = ""
    session_id:   str   = ""
    model:        str   = ""

# Hot cache vector field
_cache: Dict[str, CacheSlot] = {}

# Archive of voided slots (moved to recall, not deleted)
_voided_archive: List[CacheSlot] = []


def _update_slot(key: str, value: str, pillar: str,
                 session_id: str = "", model: str = "",
                 core: str = "", emotion: str = "", functional: str = ""):
    existing = _cache.get(key)
    if existing is None:
        _cache[key] = CacheSlot(key=key, value=value, strength=1.0,
                                 timestamp=time.time(), pillar=pillar,
                                 session_id=session_id, model=model,
                                 core=core, emotion=emotion, functional=functional)
        return

    # α-blend: M(x,t) = (1-α)·M(x,t-1) + α·I(x,t)
    blended = (1 - ALPHA) * existing.strength + ALPHA * 1.0
    _cache[key] = CacheSlot(key=key, value=value, strength=blended,
                             timestamp=time.time(), pillar=pillar,
                             access_count=existing.access_count + 1,
                             session_id=session_id, model=model,
                             core=core, emotion=emotion, functional=functional)


def update_cache(classified: ClassifiedInput, session_id: str = "", model: str = ""):
    kwargs = dict(session_id=session_id, model=model,
                  core=classified.core, emotion=classified.emotion,
                  functional=classified.functional)
    _update_slot("core",       classified.core,       "CORE",       **kwargs)
    _update_slot("emotion",    classified.emotion,    "EMOTION",    **kwargs)
    _update_slot("functional", classified.functional, "FUNCTIONAL", **kwargs)
    _update_slot("last_input", classified.text[:200], "RAW",        **kwargs)
    for mod in classified.modifiers:
        _update_slot(f"mod_{mod}", mod, "MODIFIER", **kwargs)


def apply_decay() -> List[CacheSlot]:
    """Apply decay. Returns voided slots for promotion to recall."""
    now    = time.time()
    voided = []
    for key, slot in list(_cache.items()):
        minutes = (now - slot.timestamp) / 60.0
        decayed = slot.strength * math.exp(-LAMBDA_CACHE * minutes)
        if decayed < VOID_THRESHOLD:
            voided.append(slot)
            _voided_archive.append(slot)
            del _cache[key]
        else:
            slot.strength = decayed
    return voided


def get_cache() -> Dict[str, CacheSlot]:
    return dict(_cache)


def get_active_slots(top_k: int = 10) -> List[dict]:
    slots = [{"key": s.key, "value": s.value, "strength": s.strength,
               "pillar": s.pillar, "timestamp": s.timestamp,
               "access_count": s.access_count, "core": s.core,
               "emotion": s.emotion, "functional": s.functional}
             for s in _cache.values()]
    return sorted(slots, key=lambda x: x["strength"], reverse=True)[:top_k]


def get_voided_archive() -> List[dict]:
    return [{"key": s.key, "value": s.value, "pillar": s.pillar,
             "timestamp": s.timestamp} for s in _voided_archive[-50:]]


def clear_cache():
    _cache.clear()

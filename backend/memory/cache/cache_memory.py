"""
CACHE MEMORY  —  M(x,t) = (1-α)·M(x,t-1) + α·I(x,t)
Decay:            M(x,t) = M(x,t₀)·e^(-λ(t-t₀))
"""

import math
import time
from dataclasses import dataclass
from typing import Dict, Optional
from classifier.pillar_classifier import ClassifiedInput

ALPHA          = 0.4
LAMBDA_CACHE   = 1.0   # per minute
VOID_THRESHOLD = 0.05

@dataclass
class MemorySlot:
    value:        str
    strength:     float
    timestamp:    float
    pillar:       str
    access_count: int = 1

_cache_field: Dict[str, MemorySlot] = {}


def _update_slot(key: str, value: str, pillar: str):
    existing = _cache_field.get(key)
    if existing is None:
        _cache_field[key] = MemorySlot(value=value, strength=1.0,
                                        timestamp=time.time(), pillar=pillar)
        return
    blended = (1 - ALPHA) * existing.strength + ALPHA * 1.0
    _cache_field[key] = MemorySlot(value=value, strength=blended,
                                    timestamp=time.time(), pillar=pillar,
                                    access_count=existing.access_count + 1)


def update_cache(classified: ClassifiedInput):
    _update_slot("core",       classified.core,       "CORE")
    _update_slot("emotion",    classified.emotion,    "EMOTION")
    _update_slot("functional", classified.functional, "FUNCTIONAL")
    _update_slot("last_input", classified.text,       "RAW")
    for mod in classified.modifiers:
        _update_slot(f"modifier_{mod}", mod, "MODIFIER")


def apply_decay():
    now    = time.time()
    voided = []
    for key, slot in _cache_field.items():
        minutes  = (now - slot.timestamp) / 60.0
        decayed  = slot.strength * math.exp(-LAMBDA_CACHE * minutes)
        if decayed < VOID_THRESHOLD:
            voided.append(key)
        else:
            slot.strength = decayed
    for key in voided:
        del _cache_field[key]


def get_cache() -> Dict[str, MemorySlot]:
    return dict(_cache_field)


def get_active_slots(top_k: int = 10):
    slots = [{"key": k, "value": v.value, "strength": v.strength,
               "pillar": v.pillar, "timestamp": v.timestamp,
               "access_count": v.access_count}
             for k, v in _cache_field.items()]
    return sorted(slots, key=lambda x: x["strength"], reverse=True)[:top_k]


def clear_cache():
    _cache_field.clear()

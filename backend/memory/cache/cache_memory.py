"""
CACHE MEMORY — Hot Cache Layer
Implements f = w + b with dynamic learning rate.

f = w + b
w = existing memory strength
b = lr × new_input_strength
lr = base_lr × time_factor × density_factor

Decay: M(x,t) = M(x,t₀)·e^(-λ(t-t₀))
Void threshold ε = 0.05 → slot moves to STM
"""

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from classifier.pillar_classifier import ClassifiedInput

VOID_THRESHOLD = 0.05
LAMBDA_CACHE   = 1.0   # per minute


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
    lr_used:      float = 0.4   # track what lr was used


_cache: Dict[str, CacheSlot] = {}
_voided_archive: List[CacheSlot] = []


def _update_slot(key: str, value: str, pillar: str,
                 session_id: str = "", model: str = "",
                 core: str = "", emotion: str = "",
                 functional: str = "", session_count: int = 1):
    """
    f = w + b  where b = lr × new_input_strength
    """
    from memory.learning_rate import update_memory, dynamic_lr

    existing = _cache.get(key)

    if existing is None:
        # New slot — initialize with full strength
        lr = dynamic_lr("cache", time.time(), session_count)
        _cache[key] = CacheSlot(
            key=key, value=value, strength=lr,
            timestamp=time.time(), pillar=pillar,
            session_id=session_id, model=model,
            core=core, emotion=emotion, functional=functional,
            lr_used=lr,
        )
        return

    # f = w + b (dynamic learning rate)
    new_strength = update_memory(
        w=existing.strength,
        new_input_strength=1.0,
        tier="cache",
        timestamp=existing.timestamp,
        session_count=session_count,
    )
    lr_used = dynamic_lr("cache", existing.timestamp, session_count)

    _cache[key] = CacheSlot(
        key=key, value=value, strength=new_strength,
        timestamp=time.time(), pillar=pillar,
        access_count=existing.access_count + 1,
        session_id=session_id, model=model,
        core=core, emotion=emotion, functional=functional,
        lr_used=lr_used,
    )


def update_cache(classified: ClassifiedInput, session_id: str = "",
                 model: str = "", session_count: int = 1):
    kwargs = dict(session_id=session_id, model=model, session_count=session_count,
                  core=classified.core, emotion=classified.emotion,
                  functional=classified.functional)
    _update_slot("core",       classified.core,       "CORE",       **kwargs)
    _update_slot("emotion",    classified.emotion,    "EMOTION",    **kwargs)
    _update_slot("functional", classified.functional, "FUNCTIONAL", **kwargs)
    _update_slot("last_input", classified.text[:200], "RAW",        **kwargs)
    for mod in classified.modifiers:
        _update_slot(f"mod_{mod}", mod, "MODIFIER", **kwargs)


def apply_decay() -> List[CacheSlot]:
    """Exponential decay. Returns voided slots for promotion to STM."""
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
    slots = [
        {"key": s.key, "value": s.value, "strength": s.strength,
         "pillar": s.pillar, "timestamp": s.timestamp,
         "access_count": s.access_count, "core": s.core,
         "emotion": s.emotion, "functional": s.functional,
         "lr_used": s.lr_used}
        for s in _cache.values()
    ]
    return sorted(slots, key=lambda x: x["strength"], reverse=True)[:top_k]


def get_voided_archive() -> List[dict]:
    return [{"key": s.key, "value": s.value, "pillar": s.pillar,
             "timestamp": s.timestamp} for s in _voided_archive[-50:]]


def clear_cache():
    _cache.clear()

"""
CACHE MEMORY — Hot Cache Layer
Implements f = w + b with dynamic learning rate.

f = w + b
w = existing memory strength
b = lr × new_input_strength
lr = base_lr × time_factor × density_factor

Decay: M(x,t) = M(x,t₀)·e^(-λ(t-t₀))
Void threshold ε = 0.05 → slot moves to STM

FIX: Cache is now keyed by (session_id, slot_name) to prevent
     cross-user/cross-session bleed on concurrent requests.
"""

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from classifier.pillar_classifier import ClassifiedInput

VOID_THRESHOLD = 0.05
LAMBDA_CACHE   = 1.0   # per minute

# Cache key type: (session_id, slot_name)
_CacheKey = Tuple[str, str]


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


# Keyed by (session_id, slot_name) — isolated per session
_cache: Dict[_CacheKey, CacheSlot] = {}
_voided_archive: List[CacheSlot] = []


def _make_key(session_id: str, slot_name: str) -> _CacheKey:
    return (session_id or "__global__", slot_name)


def _update_slot(key: str, value: str, pillar: str,
                 session_id: str = "", model: str = "",
                 core: str = "", emotion: str = "",
                 functional: str = "", session_count: int = 1):
    """
    f = w + b  where b = lr × new_input_strength
    Scoped to session_id to prevent cross-user bleed.

    Update rules:
      - New slot:       initialize with dynamic_lr strength
      - Same value:     reinforcement_update (strengthens toward 1.0)
      - Different value on CORE/EMOTION: contradiction_update (weakens gently)
      - Different value on FUNCTIONAL/RAW: normal update_memory
    """
    from memory.learning_rate import (
        update_memory, dynamic_lr,
        contradiction_update, reinforcement_update,
    )

    cache_key = _make_key(session_id, key)
    existing  = _cache.get(cache_key)

    if existing is None:
        lr = dynamic_lr("cache", time.time(), session_count)
        _cache[cache_key] = CacheSlot(
            key=key, value=value, strength=lr,
            timestamp=time.time(), pillar=pillar,
            session_id=session_id, model=model,
            core=core, emotion=emotion, functional=functional,
            lr_used=lr,
        )
        return

    lr_used = dynamic_lr("cache", existing.timestamp, session_count)

    # Same value repeated → reinforce
    if existing.value == value:
        new_strength = reinforcement_update(
            w=existing.strength,
            tier="cache",
            timestamp=existing.timestamp,
            session_count=session_count,
        )
        update_type = "reinforce"

    # Different value on identity pillars (CORE/EMOTION) → contradiction
    elif pillar in ("CORE", "EMOTION"):
        new_strength = contradiction_update(
            w=existing.strength,
            contradiction_strength=1.0,
            tier="cache",
            timestamp=existing.timestamp,
            session_count=session_count,
        )
        update_type = "contradict"

    # Different value on FUNCTIONAL/RAW → normal update
    else:
        new_strength = update_memory(
            w=existing.strength,
            new_input_strength=1.0,
            tier="cache",
            timestamp=existing.timestamp,
            session_count=session_count,
        )
        update_type = "update"

    _cache[cache_key] = CacheSlot(
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


def apply_decay(session_id: str = "") -> List[CacheSlot]:
    """
    Exponential decay scoped to a session.
    Returns voided slots for promotion to STM.
    Pass session_id="" to decay ALL sessions (e.g. background job).
    """
    now    = time.time()
    voided = []
    for cache_key, slot in list(_cache.items()):
        # If session_id given, only decay that session
        if session_id and cache_key[0] != session_id:
            continue
        minutes = (now - slot.timestamp) / 60.0
        decayed = slot.strength * math.exp(-LAMBDA_CACHE * minutes)
        if decayed < VOID_THRESHOLD:
            voided.append(slot)
            _voided_archive.append(slot)
            del _cache[cache_key]
        else:
            slot.strength = decayed
    return voided


def get_cache(session_id: str = "") -> Dict[str, CacheSlot]:
    """Return cache slots for a specific session."""
    return {
        k[1]: v for k, v in _cache.items()
        if not session_id or k[0] == session_id
    }


def get_active_slots(session_id: str = "", top_k: int = 10) -> List[dict]:
    """Return active slots for a specific session, sorted by strength."""
    slots = [
        {"key": s.key, "value": s.value, "strength": s.strength,
         "pillar": s.pillar, "timestamp": s.timestamp,
         "access_count": s.access_count, "core": s.core,
         "emotion": s.emotion, "functional": s.functional,
         "lr_used": s.lr_used}
        for (sid, _), s in _cache.items()
        if not session_id or sid == session_id
    ]
    return sorted(slots, key=lambda x: x["strength"], reverse=True)[:top_k]


def get_voided_archive(session_id: str = "") -> List[dict]:
    slots = _voided_archive if not session_id else [
        s for s in _voided_archive if s.session_id == session_id
    ]
    return [{"key": s.key, "value": s.value, "pillar": s.pillar,
             "timestamp": s.timestamp} for s in slots[-50:]]


def clear_cache(session_id: str = ""):
    """Clear cache for a specific session, or all sessions if no session_id."""
    if session_id:
        keys_to_delete = [k for k in _cache if k[0] == session_id]
        for k in keys_to_delete:
            del _cache[k]
    else:
        _cache.clear()

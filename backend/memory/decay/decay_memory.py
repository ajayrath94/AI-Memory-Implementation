"""
DECAY MEMORY — System-wide decay orchestrator
M(x,t) = M(x,t₀)·e^(-λₓ(t-t₀))

Decay hierarchy:
  λ_cache = 1.0  (minutes)
  λ_stm   = 0.1  (hours)
  λ_ltm   = 0.01 (days)

Void flow (per paper):
  Cache void → demote to STM
  STM void   → demote to LTM
  LTM void   → archive (never truly deleted)

System entropy S(t) = Σ(1 - e^(-λᵢ(t-t₀)))
"""

import math
import time
from typing import Optional
from memory.cache.cache_memory import apply_decay as apply_cache_decay, get_cache
from memory.recall.recall_memory import (
    apply_stm_decay, apply_ltm_decay,
    demote_from_cache, get_stm, get_ltm
)

DECAY_RATES    = {"cache": 1.0, "stm": 0.1, "ltm": 0.01}
VOID_THRESHOLD = 0.05
_last_run: float = time.time()


def track_decay():
    """
    Full decay tick — called once per user turn.
    Cache → STM demotion → STM → LTM demotion.
    """
    global _last_run
    _last_run = time.time()

    # 1. Cache decay — voided slots get demoted to STM
    voided_slots = apply_cache_decay(session_id="")
    if voided_slots:
        demote_from_cache(voided_slots)

    # 2. STM decay — weak entries get demoted to LTM
    apply_stm_decay()

    # 3. LTM decay — truly expired entries archived
    apply_ltm_decay()


def system_entropy() -> dict:
    """
    S(t) = Σ(1 - e^(-λᵢ(t-t₀)))
    High = lots of decayed memory. Low = fresh memory.
    """
    now = time.time()

    def _entropy(entries, tier, time_unit):
        lam   = DECAY_RATES[tier]
        total = 0.0
        for e in entries:
            ts      = e.get("timestamp", now) if isinstance(e, dict) else getattr(e, "timestamp", now)
            elapsed = (now - ts) / time_unit
            total  += 1 - math.exp(-lam * elapsed)
        return round(total, 4)

    cache_entries = list(get_cache().values())
    return {
        "cache":    _entropy(cache_entries, "cache", 60),
        "stm":      _entropy(get_stm(),     "stm",   3600),
        "ltm":      _entropy(get_ltm(),     "ltm",   86400),
        "last_run": _last_run,
    }

"""
DECAY MEMORY — Cache decay orchestrator
M(x,t) = M(x,t₀)·e^(-λ(t-t₀))

Only the cache tier is decayed here. STM/LTM decay is not needed
because both live in Supabase and are managed by strength scores
on recall — they don't need a periodic tick.

Cache decay constants:
  λ_cache = 1.0  (per minute) — slots die in ~3 min if not refreshed

FIX: Removed calls to apply_stm_decay() and apply_ltm_decay() from
     the old in-process recall_memory.py — those were no-ops that
     operated on Python lists never used by the AI.
"""

import math
import time
from memory.cache.cache_memory import apply_decay as apply_cache_decay, get_cache

DECAY_RATES    = {"cache": 1.0, "stm": 0.1, "ltm": 0.01}
VOID_THRESHOLD = 0.05
_last_run: float = time.time()


def track_decay():
    """
    Cache decay tick — called once per user turn.
    Voided cache slots are handled by _compress_cache_to_stm in engine_router.
    """
    global _last_run
    _last_run = time.time()
    apply_cache_decay(session_id="")


def system_entropy() -> dict:
    """
    S(t) = Σ(1 - e^(-λᵢ(t-t₀)))
    Reports entropy for the cache tier (the only active in-process tier).
    STM/LTM entropy is tracked via Supabase strength scores.
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
        "stm":      "managed by Supabase",
        "ltm":      "managed by Supabase",
        "last_run": _last_run,
    }

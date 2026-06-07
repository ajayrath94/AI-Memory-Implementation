"""
DECAY MEMORY  —  M(x,t) = M(x,t₀)·e^(-λₓ(t-t₀))
λ_cache=1.0 (min)  λ_stm=0.1 (hr)  λ_ltm=0.01 (day)
"""

import math
import time
from typing import Optional
from memory.cache.cache_memory import apply_decay as apply_cache_decay, get_cache
from memory.recall.recall_memory import get_stm, get_ltm

DECAY_RATES = {"cache": 1.0, "stm": 0.1, "ltm": 0.01}
VOID_THRESHOLD = 0.05
_last_decay_run: float = time.time()


def decay_entry(strength: float, timestamp: float, tier: str) -> Optional[float]:
    lambda_val = DECAY_RATES.get(tier, 0.1)
    now = time.time()
    if tier == "cache":
        elapsed = (now - timestamp) / 60.0
    elif tier == "stm":
        elapsed = (now - timestamp) / 3600.0
    else:
        elapsed = (now - timestamp) / 86400.0
    decayed = strength * math.exp(-lambda_val * elapsed)
    return None if decayed < VOID_THRESHOLD else decayed


def track_decay():
    global _last_decay_run
    _last_decay_run = time.time()
    apply_cache_decay()
    stm_voided = sum(1 for e in get_stm() if e.get("strength", 1) < VOID_THRESHOLD)
    ltm_voided = sum(1 for e in get_ltm() if e.get("strength", 1) < VOID_THRESHOLD)
    if stm_voided or ltm_voided:
        print(f"[DecayMemory] Voided — STM: {stm_voided}, LTM: {ltm_voided}")


def system_entropy() -> dict:
    now = time.time()

    def entropy(entries, tier):
        lam = DECAY_RATES[tier]
        total = 0.0
        for e in entries:
            ts = e.get("timestamp", now) if isinstance(e, dict) else getattr(e, "timestamp", now)
            elapsed = (now - ts) / 60.0
            total += 1 - math.exp(-lam * elapsed)
        return round(total, 4)

    cache_entries = list(get_cache().values())
    return {
        "cache":    entropy(cache_entries, "cache"),
        "stm":      entropy(get_stm(),     "stm"),
        "ltm":      entropy(get_ltm(),     "ltm"),
        "last_run": _last_decay_run,
    }

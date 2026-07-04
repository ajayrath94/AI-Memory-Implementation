"""
DYNAMIC LEARNING RATE
Implements f = w + b where b = lr × new_input

Learning rate is dynamic based on:
  - density:   how many sessions/memories exist
  - timestamp: how recent the memory is
  - tier:      which memory layer (cache/stm/ltm)

Formula:
  lr = base_lr × time_factor × density_factor

  time_factor    = e^(-λ(t - t₀))      # recent = higher lr
  density_factor = 1 / (1 + log(n+1))  # more memories = lower lr

Behaviors:
  - Early sessions (density=1):  lr=0.8  fast learner
  - Mid sessions  (density=10):  lr=0.4  balanced
  - Late sessions (density=50):  lr=0.1  stable core
  - Cache layer:  base_lr=0.8   fast update
  - STM layer:    base_lr=0.4   medium update
  - LTM layer:    base_lr=0.1   slow, stable
"""

import math
import time
from typing import Literal

# Base learning rates per tier
BASE_LR = {
    "cache": 0.8,
    "stm":   0.4,
    "ltm":   0.1,
}

# Decay constants per tier (for time factor)
LAMBDA = {
    "cache": 1.0,   # minutes
    "stm":   0.1,   # hours
    "ltm":   0.01,  # days
}

# Time units per tier (in seconds)
TIME_UNIT = {
    "cache": 60,       # minutes
    "stm":   3600,     # hours
    "ltm":   86400,    # days
}


def time_factor(timestamp: float, tier: str) -> float:
    """
    e^(-λ(t - t₀))
    Recent memories have higher time factor (closer to 1.0)
    Old memories have lower time factor (closer to 0.0)
    """
    elapsed = (time.time() - timestamp) / TIME_UNIT[tier]
    return math.exp(-LAMBDA[tier] * elapsed)


def density_factor(session_count: int) -> float:
    """
    1 / (1 + log(n+1))
    More sessions = lower density factor = slower learning
    session_count=1:  factor=1.0  (blank slate)
    session_count=10: factor=0.42
    session_count=50: factor=0.26
    session_count=100: factor=0.22
    """
    return 1.0 / (1.0 + math.log1p(session_count))


def dynamic_lr(tier: str, timestamp: float, session_count: int) -> float:
    """
    Combined dynamic learning rate.
    lr = base_lr × time_factor × density_factor
    """
    base   = BASE_LR.get(tier, 0.4)
    t_fac  = time_factor(timestamp, tier)
    d_fac  = density_factor(session_count)
    lr     = base * t_fac * d_fac
    return round(max(0.01, min(1.0, lr)), 4)  # clamp 0.01-1.0


def update_memory(w: float, new_input_strength: float,
                  tier: str, timestamp: float,
                  session_count: int) -> float:
    """
    f = w + b
    where b = lr × new_input_strength

    w:                  existing memory strength
    new_input_strength: strength of new information (0-1)
    tier:               cache | stm | ltm
    timestamp:          when existing memory was created
    session_count:      total sessions for this user

    Returns: new memory strength (clamped 0-1)
    """
    lr = dynamic_lr(tier, timestamp, session_count)
    b  = lr * new_input_strength
    f  = w + b
    return round(max(0.0, min(1.0, f)), 4)


def contradiction_update(w: float, contradiction_strength: float,
                         tier: str, timestamp: float,
                         session_count: int) -> float:
    """
    Handle contradicting information.
    f = w - b  (weakens but doesn't erase)

    e.g. User said "loves movies" (w=0.9)
         Now says "hates movies" (contradiction)
         Result: 0.9 - 0.2 = 0.7 (weakened, not erased)
         Because maybe they just had a bad day!
    """
    lr = dynamic_lr(tier, timestamp, session_count)
    b  = lr * contradiction_strength * 0.5  # softer for contradictions
    f  = w - b
    return round(max(0.0, min(1.0, f)), 4)


def reinforcement_update(w: float, tier: str,
                         timestamp: float, session_count: int) -> float:
    """
    Same info repeated → strength approaches 1.0
    Used when existing memory is confirmed by new input.
    """
    return update_memory(w, 1.0, tier, timestamp, session_count)


# ── Reporting ──────────────────────────────────────────────────────────────────

def learning_rate_report(session_count: int) -> dict:
    """Show current learning rates across all tiers."""
    now = time.time()
    return {
        "session_count": session_count,
        "density_factor": round(density_factor(session_count), 4),
        "rates": {
            tier: {
                "base_lr":      BASE_LR[tier],
                "time_factor":  round(time_factor(now, tier), 4),
                "density_factor": round(density_factor(session_count), 4),
                "effective_lr": dynamic_lr(tier, now, session_count),
            }
            for tier in ["cache", "stm", "ltm"]
        }
    }

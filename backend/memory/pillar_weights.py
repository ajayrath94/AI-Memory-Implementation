"""
PILLAR WEIGHT SYSTEM
Allows users/caregivers to customize how much Nancy
pays attention to each pillar.

Weight range: 0.1 (nearly ignored) → 1.0 (default) → 2.0 (double priority)

Affects:
  - Priority scoring (HIGH/MEDIUM/LOW thresholds)
  - Alert detection sensitivity
  - Recommendation ranking
  - Profile enrichment triggers

Example:
  caregiver sets HEALTH_WELLNESS → 1.8
  → Nancy is more sensitive to health signals
  → Alerts fire sooner
  → Profile health fields updated more aggressively

  user sets ENTERTAINMENT → 0.3
  → Nancy talks less about cricket/music
  → Interest tracking still works but weighted lower
"""

from typing import Dict, Optional
from functools import lru_cache
import time


# ── Default weights (all pillars = 1.0) ───────────────────────────────────────

DEFAULT_WEIGHTS = {
    # Core
    "HEALTH_WELLNESS": 1.0,
    "FINANCE":         1.0,
    "ENTERTAINMENT":   1.0,
    "ASPIRATIONS":     1.0,
    "CAREER_GOAL":     1.0,
    "GENERAL":         1.0,
    # Emotion
    "OPTIMISM":        1.0,
    "JOY":             1.0,
    "FEAR":            1.0,
    "SADNESS":         1.0,
    "ANGER":           1.0,
    "STRESS":          1.0,
    "LOVE":            1.0,
    # Functional
    "PLAN":            1.0,
    "SEARCH":          1.0,
    "ORDER":           1.0,
    "TRACK":           1.0,
    "NUDGE":           1.0,
}

# Simple in-memory cache: user_id → (weights_dict, timestamp)
_weights_cache: Dict[str, tuple] = {}
CACHE_TTL = 300  # 5 minutes


# ── Get weights ────────────────────────────────────────────────────────────────

def get_pillar_weights(user_id: str) -> Dict[str, float]:
    """
    Get pillar weights for a user.
    Returns DEFAULT_WEIGHTS merged with any user customizations.
    Cached for 5 minutes to avoid DB hits on every message.
    """
    # Check cache
    if user_id in _weights_cache:
        weights, ts = _weights_cache[user_id]
        if time.time() - ts < CACHE_TTL:
            return weights

    try:
        from supabase_store import get_client
        db     = get_client()
        result = db.table("user_pillar_weights")\
            .select("pillar, weight")\
            .eq("user_id", user_id)\
            .execute()

        weights = dict(DEFAULT_WEIGHTS)  # Start from defaults
        for row in (result.data or []):
            pillar = row.get("pillar")
            weight = row.get("weight", 1.0)
            if pillar in weights:
                weights[pillar] = float(weight)

        _weights_cache[user_id] = (weights, time.time())
        return weights

    except Exception as e:
        print(f"[PillarWeights] Failed to load for {user_id}: {e}")
        return dict(DEFAULT_WEIGHTS)


def invalidate_cache(user_id: str):
    """Call after updating weights to clear the cache."""
    _weights_cache.pop(user_id, None)


# ── Apply weights to classification scores ────────────────────────────────────

def apply_weights(classified, user_id: str):
    """
    Apply user pillar weights to a classified input.
    Modifies the effective priority based on weights.

    Returns a dict of weighted scores for use in:
      - Alert detection
      - Recommendation ranking
      - Profile enrichment thresholds
    """
    weights = get_pillar_weights(user_id)

    weighted_scores = {}
    raw_scores = classified.pillar_scores or {}

    for pillar, score in raw_scores.items():
        w = weights.get(pillar, 1.0)
        weighted_scores[pillar] = round(score * w, 4)

    return weighted_scores


def get_weighted_priority(pillar: str, base_score: float, user_id: str) -> str:
    """
    Get priority level after applying user weights.
    Same thresholds as classifier but score is weighted first.
    """
    weights = get_pillar_weights(user_id)
    w       = weights.get(pillar, 1.0)
    score   = base_score * w

    if score >= 0.80:   return "HIGH"
    if score >= 0.65:   return "MEDIUM"
    return "LOW"


# ── Save/update weights ────────────────────────────────────────────────────────

def log_weight_history(user_id: str, pillar: str, old_weight: float,
                        new_weight: float, changed_by: str = "user", reason: str = ""):
    """Log weight change to history table."""
    try:
        from supabase_store import get_client
        db = get_client()
        db.table("pillar_weight_history").insert({
            "user_id":    user_id,
            "changed_by": changed_by,
            "pillar":     pillar,
            "old_weight": old_weight,
            "new_weight": new_weight,
            "reason":     reason,
        }).execute()
    except Exception as e:
        print(f"[PillarWeights] History log failed: {e}")


def set_pillar_weight(user_id: str, pillar: str, weight: float,
                      changed_by: str = "user", reason: str = "") -> bool:
    """
    Set a single pillar weight for a user.
    Weight is clamped to [0.1, 2.0].
    Logs change to history table.
    """
    if pillar not in DEFAULT_WEIGHTS:
        print(f"[PillarWeights] Unknown pillar: {pillar}")
        return False

    weight = max(0.1, min(2.0, float(weight)))

    try:
        from supabase_store import get_client
        db = get_client()

        # Get old weight for history
        old_weights = get_pillar_weights(user_id)
        old_weight  = old_weights.get(pillar, 1.0)

        db.table("user_pillar_weights").upsert({
            "user_id":    user_id,
            "pillar":     pillar,
            "weight":     weight,
            "updated_at": "now()",
        }, on_conflict="user_id,pillar").execute()

        # Log to history
        if old_weight != weight:
            log_weight_history(user_id, pillar, old_weight, weight, changed_by, reason)

        invalidate_cache(user_id)
        print(f"[PillarWeights] Set {pillar}={weight} for {user_id} (was {old_weight})")
        return True

    except Exception as e:
        print(f"[PillarWeights] Failed to set weight: {e}")
        return False


def set_pillar_weights_bulk(user_id: str, weights: Dict[str, float]) -> dict:
    """
    Set multiple pillar weights at once.
    Returns summary of what was set vs rejected.
    """
    results = {"set": [], "rejected": [], "errors": []}

    for pillar, weight in weights.items():
        if pillar not in DEFAULT_WEIGHTS:
            results["rejected"].append(f"{pillar} (unknown pillar)")
            continue
        if set_pillar_weight(user_id, pillar, weight):
            results["set"].append(f"{pillar}={weight}")
        else:
            results["errors"].append(pillar)

    return results


def reset_pillar_weights(user_id: str) -> bool:
    """
    Reset all weights to default (1.0) for a user.
    Deletes all custom rows — defaults kick in automatically.
    """
    try:
        from supabase_store import get_client
        db = get_client()
        db.table("user_pillar_weights")\
            .delete()\
            .eq("user_id", user_id)\
            .execute()
        invalidate_cache(user_id)
        print(f"[PillarWeights] Reset all weights for {user_id}")
        return True
    except Exception as e:
        print(f"[PillarWeights] Reset failed: {e}")
        return False


# ── Build weight summary for prompt injection ──────────────────────────────────

def build_weights_prompt(user_id: str) -> Optional[str]:
    """
    Build a concise description of non-default weights
    to inject into Nancy's system prompt.
    Only mentions pillars that differ from default.
    """
    weights  = get_pillar_weights(user_id)
    modified = {p: w for p, w in weights.items() if abs(w - 1.0) > 0.05}

    if not modified:
        return None

    boosted  = [f"{p.replace('_',' ')} (×{w})" for p, w in modified.items() if w > 1.0]
    reduced  = [f"{p.replace('_',' ')} (×{w})" for p, w in modified.items() if w < 1.0]

    lines = ["CONVERSATION FOCUS (user preferences):"]
    if boosted:
        lines.append(f"Pay MORE attention to: {', '.join(boosted)}")
    if reduced:
        lines.append(f"Pay LESS attention to: {', '.join(reduced)}")

    return "\n".join(lines)


def get_pillar_shares(user_id: str, pillars: list = None) -> dict:
    """
    Normalized share of attention per pillar, summing to 1.0.

    Weights are stored as absolute values (0.1–2.0) because retrieval needs
    them that way — each pillar is judged on its own. But proactive nudges
    are genuinely zero-sum: only one gets sent, so "how often should this
    pillar be chosen" is a share, not a level.

    Muted pillars (below MUTE_THRESHOLD) are excluded entirely.
    Pass `pillars` to restrict to a group, e.g. CORE_PILLARS.
    """
    weights = get_pillar_weights(user_id)
    if pillars:
        weights = {p: w for p, w in weights.items() if p in pillars}

    eligible = {p: w for p, w in weights.items() if w >= 0.5}
    total    = sum(eligible.values())
    if not total:
        return {}
    return {p: round(w / total, 4) for p, w in eligible.items()}

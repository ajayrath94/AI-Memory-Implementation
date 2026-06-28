"""
FORGETTING MECHANISM
Real memory fades — so should Nancy's.

Rules:
  STM clusters:
    - Older than 7 days AND recall_count < 3 → delete
    - Already promoted to LTM (recall_count >= 3) → delete

  LTM patterns:
    - Not recalled in 30+ days → decay strength by 20%
    - Strength < 0.1 after 90+ days without recall → delete

  This runs in the background on session end.
  Cost: 2-3 Supabase queries per session end. Negligible.
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Tuple


def _days_since(timestamp_str: str) -> float:
    """Calculate days since a Supabase timestamp string."""
    if not timestamp_str:
        return 0.0
    try:
        ts  = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - ts).total_seconds() / 86400.0
    except Exception:
        return 0.0


def decay_stm(user_id: str = "") -> Tuple[int, int]:
    """
    Clean up stale STM clusters.
    Returns (deleted_count, kept_count)
    """
    from supabase_store import get_client
    db = get_client()

    try:
        # Get all STM clusters (optionally filter by user via session join)
        result = db.table("stm_clusters").select(
            "id, recall_count, timestamp, session_id"
        ).execute()

        deleted = 0
        kept    = 0

        for cluster in (result.data or []):
            days    = _days_since(cluster.get("timestamp", ""))
            recalls = cluster.get("recall_count", 0)

            # Delete if: older than 7 days and never promoted
            if days > 7 and recalls < 3:
                db.table("stm_clusters").delete().eq("id", cluster["id"]).execute()
                deleted += 1
            else:
                kept += 1

        if deleted:
            print(f"[Forgetting] STM: deleted {deleted} stale clusters, kept {kept}")
        return deleted, kept

    except Exception as e:
        print(f"[Forgetting] STM decay failed: {e}")
        return 0, 0


def decay_ltm(user_id: str) -> Tuple[int, int, int]:
    """
    Decay and prune LTM patterns for a user.
    Returns (decayed_count, deleted_count, kept_count)
    """
    from supabase_store import get_client
    db = get_client()

    try:
        result = db.table("ltm_patterns").select(
            "id, strength, recall_count, timestamp"
        ).eq("user_id", user_id).execute()

        decayed = 0
        deleted = 0
        kept    = 0

        for pattern in (result.data or []):
            days     = _days_since(pattern.get("timestamp", ""))
            strength = pattern.get("strength", 1.0)
            recalls  = pattern.get("recall_count", 0)

            # Delete: very old + low strength + never recalled
            if days > 90 and strength < 0.1 and recalls == 0:
                db.table("ltm_patterns").delete().eq("id", pattern["id"]).execute()
                deleted += 1
                continue

            # Decay: not recalled in 30+ days
            if days > 30:
                # Exponential decay: 20% reduction per 30-day period
                decay_periods = days / 30.0
                new_strength  = strength * math.exp(-0.22 * decay_periods)
                new_strength  = max(0.01, round(new_strength, 4))

                if new_strength != strength:
                    db.table("ltm_patterns").update({
                        "strength": new_strength
                    }).eq("id", pattern["id"]).execute()
                    decayed += 1
                    kept    += 1
                    continue

            kept += 1

        if decayed or deleted:
            print(f"[Forgetting] LTM for {user_id}: decayed={decayed}, deleted={deleted}, kept={kept}")
        return decayed, deleted, kept

    except Exception as e:
        print(f"[Forgetting] LTM decay failed: {e}")
        return 0, 0, 0


def run_forgetting(user_id: str):
    """
    Run full forgetting cycle for a user.
    Called in background on session end.
    """
    print(f"[Forgetting] Running for user: {user_id}")
    decay_stm(user_id)
    decay_ltm(user_id)

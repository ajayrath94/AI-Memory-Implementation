"""
PROACTIVE LOG
Writes every proactive decision to proactive_events. This is the seed corn for
all later intelligence — weekly/monthly/quarterly patterns, per-user rhythm,
adherence trends — so each row is timestamped, typed, and outcome-ready.

Lifecycle: decided -> delivered -> engaged|dismissed|ignored (or suppressed).
The decision is logged immediately; outcomes are stamped on later as they happen.
"""
from datetime import datetime, timezone


def _idem_key(user_id: str, action: str) -> str:
    """user + THEIR-LOCAL-day + action — one fire per user's own day, so a
    redeploy/retry can't double-send. Uses the user's timezone (not UTC), or a
    daily reminder near midnight could double-fire across the UTC date boundary."""
    try:
        from memory.time_context import get_user_timezone
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(get_user_timezone(user_id))
        day = datetime.now(tz).strftime("%Y-%m-%d")
    except Exception:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{user_id}:{day}:{action}"


def log_decision(decision: dict, sources: dict = None) -> dict:
    """
    Record a proactive decision. Idempotent per user/day/action.
    Returns {logged: bool, id: ..., duplicate: bool}.
    SILENCE decisions are logged too (as 'suppressed') — every 'no' is data.
    """
    from supabase_store import get_client
    db = get_client()

    action = decision.get("action", "UNKNOWN")
    outcome = "suppressed" if action == "SILENCE" else "decided"
    idem = _idem_key(decision.get("user_id", ""), action)

    row = {
        "user_id":        decision.get("user_id"),
        "action":         action,
        "reason":         decision.get("reason"),
        "detail":         decision.get("detail"),
        "priority":       decision.get("priority"),
        "slot":           decision.get("slot"),
        "mode":           decision.get("mode"),
        "away_from_home": decision.get("away_from_home"),
        "sources":        sources or {},
        "outcome":        outcome,
        "idempotency_key": idem,
    }

    try:
        res = db.table("proactive_events").insert(row).execute()
        return {"logged": True, "id": res.data[0]["id"] if res.data else None,
                "duplicate": False}
    except Exception as e:
        # unique index on idempotency_key -> duplicate same-day fire
        if "duplicate" in str(e).lower() or "23505" in str(e):
            return {"logged": False, "duplicate": True, "id": None}
        print(f"[ProactiveLog] insert failed: {e}")
        return {"logged": False, "duplicate": False, "id": None}


def record_outcome(event_id: str, outcome: str) -> bool:
    """
    Stamp what happened to a delivered event: delivered | engaged | dismissed
    | ignored. This is the half that makes adherence/engagement stats possible —
    without it we'd know what we SENT but not what LANDED.
    """
    from supabase_store import get_client
    valid = {"delivered", "engaged", "dismissed", "ignored"}
    if outcome not in valid:
        return False
    stamp = {"outcome": outcome}
    if outcome == "delivered":
        stamp["delivered_at"] = datetime.now(timezone.utc).isoformat()
    else:
        stamp["responded_at"] = datetime.now(timezone.utc).isoformat()
    try:
        get_client().table("proactive_events").update(stamp).eq("id", event_id).execute()
        return True
    except Exception as e:
        print(f"[ProactiveLog] outcome update failed: {e}")
        return False

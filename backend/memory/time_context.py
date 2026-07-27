"""
TIME CONTEXT
The single source of temporal truth for a user. Every proactive decision —
medication, night-safety, silence check-ins — reads from here rather than
calling datetime.now() directly (which is server UTC, wrong for IST users).

Answers: what time is it FOR THIS USER, what window are they in, how long
since they last spoke, and is that silence unusual.
"""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo


def _slot(hour: int) -> str:
    if   6  <= hour < 10: return "morning"
    elif 10 <= hour < 14: return "midday"
    elif 14 <= hour < 17: return "afternoon"
    elif 17 <= hour < 20: return "evening"
    elif 20 <= hour < 23: return "night"
    else:                 return "late_night"


def _mode(hour: int, minute: int) -> str:
    """Explore vs safety switch for location-aware recommendations.
    Day 07:00-22:00 -> explore. Night 22:01-06:59 -> safety."""
    mins = hour * 60 + minute
    return "explore" if (7 * 60) <= mins <= (22 * 60) else "safety"


def get_user_timezone(user_id: str) -> str:
    """Stored IANA zone the phone reported; defaults to IST."""
    try:
        from supabase_store import get_client
        rows = (get_client().table("user_context").select("timezone")
                .eq("user_id", user_id).limit(1).execute()).data or []
        if rows and rows[0].get("timezone"):
            return rows[0]["timezone"]
    except Exception as e:
        print(f"[TimeContext] tz fetch failed: {e}")
    return "Asia/Kolkata"


def _last_interaction(user_id: str):
    """Most recent session activity — the silence signal. Returns aware dt or None."""
    try:
        from supabase_store import get_client
        rows = (get_client().table("sessions").select("updated_at")
                .eq("user_id", user_id).order("updated_at", desc=True)
                .limit(1).execute()).data or []
        if rows and rows[0].get("updated_at"):
            return datetime.fromisoformat(rows[0]["updated_at"].replace("Z", "+00:00"))
    except Exception as e:
        print(f"[TimeContext] last-interaction fetch failed: {e}")
    return None


def time_context(user_id: str) -> dict:
    """The full temporal picture for one user, in THEIR timezone."""
    tz_name = get_user_timezone(user_id)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")

    now_local = datetime.now(tz)
    hour, minute = now_local.hour, now_local.minute
    slot = _slot(hour)

    # Silence: minutes since last interaction
    last = _last_interaction(user_id)
    if last:
        gap_min = int((datetime.now(timezone.utc) - last).total_seconds() // 60)
    else:
        gap_min = None

    # Is this silence unusual? Overnight silence is EXPECTED; daytime is not.
    unusual = False
    if gap_min is not None:
        if slot in ("night", "late_night"):
            unusual = gap_min > 12 * 60          # only if truly very long
        else:
            unusual = gap_min > 6 * 60           # 6h quiet in waking hours
        # never flag if it's currently sleeping hours (they're asleep, not silent)
        if slot == "late_night":
            unusual = False

    return {
        "user_id":        user_id,
        "timezone":       tz_name,
        "local_time":     now_local.strftime("%Y-%m-%d %H:%M"),
        "hour":           hour,
        "minute":         minute,
        "slot":           slot,
        "mode":           _mode(hour, minute),      # explore | safety
        "minutes_since_last": gap_min,
        "unusual_silence": unusual,
    }

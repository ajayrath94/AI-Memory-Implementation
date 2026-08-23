"""
ROUTINE OBSERVATION — what their day actually looks like.

Everything the companion notices is currently about what someone SAYS. Sleeping
later, going quiet at a time they are normally chatty, drifting off a routine —
none of that reaches anything, because there is no baseline to deviate from.
This builds the baseline.

Two sources, kept separate rather than merged:

  declared  — what they told us at onboarding. Authoritative until they change
              it. Someone saying "I wake at 6:30" is better evidence than a
              fortnight of inference.
  observed  — what the timestamps show. Never overwrites declared; when the two
              diverge the difference is recorded, and the companion asks about
              it rather than deciding on their behalf.

The divergence is the valuable part. "She says 6:30 but has been talking at 8
for a week" is either a routine change or a decline, and only she knows which.

SPREAD MATTERS AS MUCH AS THE CENTRE. Someone up between 6:00 and 6:30 has a
routine; someone between 5:00 and 11:00 does not, and a "deviation" from the
second means nothing. Confidence is built from both.
"""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from statistics import median
from typing import Optional
from zoneinfo import ZoneInfo

# Below this many days with data, a pattern is a guess rather than a routine.
MIN_DAYS = 4

# How far back to look. Long enough to be stable, short enough to follow a real
# change in their life.
WINDOW_DAYS = 21

# A drift smaller than someone's own variability is not a drift.
MIN_DRIFT_MIN = 45


def _tz(user_id: str) -> ZoneInfo:
    try:
        from memory.time_context import get_user_timezone
        return ZoneInfo(get_user_timezone(user_id))
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def _user_messages(user_id: str, days: int = WINDOW_DAYS) -> list:
    """Their own messages, with timestamps, over the window.

    User turns only: the companion's proactive messages would otherwise make it
    look as though someone was awake at 8am when it was the system talking.
    """
    try:
        from supabase_store import get_client
        db = get_client()
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        sess = (db.table("sessions").select("id")
                .eq("user_id", user_id).gte("updated_at", since)
                .execute()).data or []
        ids = [s["id"] for s in sess]
        if not ids:
            return []
        rows = (db.table("messages").select("timestamp,role")
                .in_("session_id", ids).eq("role", "user")
                .gte("timestamp", since).execute()).data or []
        return [r["timestamp"] for r in rows if r.get("timestamp")]
    except Exception as e:
        print(f"[Patterns] message read failed: {e}")
        return []


def _by_local_day(stamps: list, tz: ZoneInfo) -> dict:
    """Group timestamps into local calendar days, as minutes past midnight."""
    days = defaultdict(list)
    for s in stamps:
        try:
            dt = datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(tz)
        except Exception:
            continue
        days[dt.date()].append(dt.hour * 60 + dt.minute)
    return days


def _centre_and_spread(values: list) -> tuple:
    """Median rather than mean: one 3am insomnia night should not move a wake
    time by an hour. Spread is the interquartile-ish range, in minutes."""
    if not values:
        return None, 0
    vals = sorted(values)
    centre = int(median(vals))
    if len(vals) < 3:
        return centre, abs(vals[-1] - vals[0])
    lo = vals[len(vals) // 4]
    hi = vals[(3 * len(vals)) // 4]
    return centre, int(hi - lo)


def _confidence(n_days: int, spread_min: int) -> float:
    """More days is better; a tighter routine is better. A fortnight of
    consistent mornings is near-certain; four scattered days is not."""
    if n_days < MIN_DAYS:
        return 0.0
    day_part    = min(n_days / 14.0, 1.0)
    spread_part = max(0.0, 1.0 - (spread_min / 180.0))    # 3h spread -> 0
    return round(min(day_part * 0.6 + spread_part * 0.4, 1.0), 2)


def _mins_to_time(m: Optional[int]) -> Optional[str]:
    if m is None:
        return None
    m = max(0, min(int(m), 24 * 60 - 1))
    return f"{m // 60:02d}:{m % 60:02d}:00"


def _time_to_mins(t) -> Optional[int]:
    if not t:
        return None
    try:
        parts = str(t).split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return None


def observe(user_id: str) -> list:
    """Derive wake, sleep and active-window patterns. Returns what it wrote."""
    tz     = _tz(user_id)
    stamps = _user_messages(user_id)
    days   = _by_local_day(stamps, tz)
    if len(days) < MIN_DAYS:
        print(f"[Patterns] {user_id}: only {len(days)} day(s) of data, "
              f"need {MIN_DAYS}")
        return []

    firsts = [min(v) for v in days.values() if v]
    lasts  = [max(v) for v in days.values() if v]

    derived = []
    for kind, values in (("wake", firsts), ("sleep", lasts)):
        centre, spread = _centre_and_spread(values)
        if centre is None:
            continue
        derived.append({
            "kind":         kind,
            "label":        None,
            "observed_at":  _mins_to_time(centre),
            "spread_min":   spread,
            "observations": len(values),
            "confidence":   _confidence(len(days), spread),
        })

    # How much of the day they are actually around for — the span between the
    # two, useful for knowing when NOT to reach out.
    if firsts and lasts:
        derived.append({
            "kind":         "active_window",
            "label":        None,
            "observed_at":  _mins_to_time(int(median(firsts))),
            "spread_min":   int(median(lasts) - median(firsts)),
            "observations": len(days),
            "confidence":   _confidence(len(days), 0),
        })

    return [_upsert(user_id, d) for d in derived]


def _upsert(user_id: str, d: dict) -> dict:
    """Write the observation WITHOUT touching what they declared.

    declared_at and observed_at are separate columns on purpose: recording what
    someone does must never erase what they said, or the divergence — the
    interesting part — is lost.
    """
    from supabase_store import get_client
    db = get_client()

    try:
        existing = (db.table("user_patterns").select("*")
                    .eq("user_id", user_id).eq("kind", d["kind"])
                    .is_("label", "null" if d["label"] is None else d["label"])
                    .limit(1).execute()).data or []
    except Exception:
        existing = []

    row = {
        "user_id":      user_id,
        "kind":         d["kind"],
        "label":        d["label"],
        "observed_at":  d["observed_at"],
        "spread_min":   d["spread_min"],
        "observations": d["observations"],
        "confidence":   d["confidence"],
        "last_seen":    datetime.now(timezone.utc).isoformat(),
        "updated_at":   datetime.now(timezone.utc).isoformat(),
    }

    prev = existing[0] if existing else None
    declared = _time_to_mins(prev.get("declared_at")) if prev else None
    observed = _time_to_mins(d["observed_at"])

    if declared is not None and observed is not None:
        drift = observed - declared
        # Only a drift larger than their own variability counts. Someone whose
        # mornings range over two hours has not "drifted" by forty minutes.
        if abs(drift) >= max(MIN_DRIFT_MIN, d["spread_min"]):
            row["drift_min"] = drift
            if not (prev and prev.get("drift_since")):
                row["drift_since"] = datetime.now(timezone.utc).isoformat()
        else:
            row["drift_min"]   = None
            row["drift_since"] = None

    if prev:
        # Never downgrade a declared or corrected row to "observed".
        if (prev.get("source") or "declared") == "observed":
            row["source"] = "observed"
        db.table("user_patterns").update(row).eq("id", prev["id"]).execute()
        row["id"] = prev["id"]
    else:
        row["source"] = "observed"
        created = db.table("user_patterns").insert(row).execute().data
        row["id"] = created[0]["id"] if created else None

    return row


def observe_all(min_days: int = MIN_DAYS) -> int:
    """Run for everyone with enough history. Cheap — no model calls."""
    try:
        from supabase_store import get_client
        rows = (get_client().table("user_memory").select("user_id")
                .execute()).data or []
    except Exception as e:
        print(f"[Patterns] user list failed: {e}")
        return 0
    n = 0
    for r in rows:
        try:
            if observe(r["user_id"]):
                n += 1
        except Exception as e:
            print(f"[Patterns] observe failed for {r.get('user_id')}: {e}")
    return n


def get_patterns(user_id: str) -> list:
    """Everything known about their day, declared and observed."""
    try:
        from supabase_store import get_client
        return (get_client().table("user_patterns").select("*")
                .eq("user_id", user_id).order("kind").execute()).data or []
    except Exception as e:
        print(f"[Patterns] read failed: {e}")
        return []

"""
CARE READER
Bridges the care_schedule / care_facts tables into the proactive engine.

The engine used to guess ("subah ki dawai leni hai"). Now it reads the real
schedule a caregiver entered — actual medications, times, doses — and the
standing facts that constrain what Nancy may suggest.
"""
from datetime import datetime, timezone, timedelta


def _parse_hhmm(t: str) -> tuple:
    """'08:00:00' or '08:00' -> (8, 0). Returns (-1,-1) on bad input."""
    try:
        parts = str(t).split(":")
        return int(parts[0]), int(parts[1])
    except Exception:
        return -1, -1


def _day_matches(days: str, weekday: int) -> bool:
    """days = 'daily' or 'mon,wed,fri'. weekday: Mon=0..Sun=6."""
    if not days or days.strip().lower() == "daily":
        return True
    names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    want = {d.strip().lower()[:3] for d in days.split(",")}
    return names[weekday] in want


def get_due_schedule_items(user_id: str, hour: int = None,
                           window_min: int = 45, weekday: int = None) -> list:
    """
    Items scheduled within +/- window_min of `hour` (defaults to now, IST),
    filtered by day-of-week. Returns the list the engine turns into reminders.
    """
    # IST is the user timezone; the server runs UTC, so resolve explicitly.
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist)
    if hour is None:
        hour = now.hour
    if weekday is None:
        weekday = now.weekday()
    now_min = hour * 60 + now.minute if hour == now.hour else hour * 60

    try:
        from supabase_store import get_client
        rows = (get_client().table("care_schedule").select("*")
                .eq("user_id", user_id).eq("active", True).execute()).data or []
    except Exception as e:
        print(f"[CareReader] fetch failed: {e}")
        return []

    due = []
    for r in rows:
        if not _day_matches(r.get("days", "daily"), weekday):
            continue
        h, m = _parse_hhmm(r.get("time_of_day", ""))
        if h < 0:
            continue
        item_min = h * 60 + m
        if abs(item_min - now_min) <= window_min:
            due.append({
                "type":  r.get("type"),
                "label": r.get("label"),
                "dose":  r.get("dose"),
                "notes": r.get("notes"),
                "time":  f"{h:02d}:{m:02d}",
                "delta_min": item_min - now_min,   # negative = overdue
            })
    due.sort(key=lambda x: abs(x["delta_min"]))
    return due


def get_care_facts(user_id: str) -> dict:
    """
    Standing facts grouped for the engine: guardrails it must respect.
    Returns {critical: [...], important: [...], normal: [...], dietary: [...]}.
    """
    try:
        from supabase_store import get_client
        rows = (get_client().table("care_facts").select("*")
                .eq("user_id", user_id).eq("active", True).execute()).data or []
    except Exception as e:
        print(f"[CareReader] facts fetch failed: {e}")
        return {}

    out = {"critical": [], "important": [], "normal": [], "dietary": []}
    for r in rows:
        fact = r.get("fact", "")
        sev  = r.get("severity", "normal")
        out.setdefault(sev, []).append(fact)
        if r.get("type") == "dietary":
            out["dietary"].append(fact)
    return out

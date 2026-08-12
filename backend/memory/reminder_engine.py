"""
REMINDER ENGINE — the first module of the reactive engine.

User says "kal 12 baje doctor yaad dilana" -> we detect the reminder intent,
resolve the relative time against the user's REAL local clock (time_context),
store an absolute fire_at, and return a structured event the app shows as a
card. The heartbeat later fires it deterministically.

Reminders are EXACT and costly-if-wrong (a missed appointment), so this is a
focused, single-purpose call — not folded into the fuzzy memory extraction.
"""
import os, json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_MODEL = "claude-haiku-4-5-20251001"


def detect_and_store_reminder(user_id: str, text: str, session_id: str = "") -> dict | None:
    """Returns a structured reminder event if the message asked to be reminded
    of something, else None. Stores it with an absolute UTC fire_at."""
    try:
        from memory.time_context import time_context, get_user_timezone
    except Exception:
        return None

    tc = time_context(user_id)
    now_local = tc.get("local_time", "")
    tz_name = tc.get("timezone", "Asia/Kolkata")

    # ---- focused extraction: is this a reminder? what + when ----
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    except Exception as e:
        print(f"[Reminder] no anthropic client: {e}")
        return None

    prompt = f"""The user's current local time is {now_local} ({tz_name}).

User message: "{text}"

Does the user ask to be REMINDED of something at a future time (e.g. "kal 12
baje yaad dilana", "remind me tomorrow", "shaam ko yaad karana")? Only count an
explicit request to be reminded / notified later — NOT general mentions of
future plans.

If YES, resolve the time to an absolute local datetime based on the current
local time above. Return ONLY JSON:
{{"is_reminder": true, "what": "short description of what to remind about", "fire_at_local": "YYYY-MM-DD HH:MM"}}

If NO reminder request, return ONLY: {{"is_reminder": false}}

No prose, only JSON."""

    try:
        resp = client.messages.create(
            model=_MODEL, max_tokens=300,
            messages=[{"role": "user", "content": prompt}])
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].replace("json", "", 1).strip()
        data = json.loads(raw)
    except Exception as e:
        print(f"[Reminder] extraction failed: {e}")
        return None

    if not data.get("is_reminder"):
        return None

    what = (data.get("what") or "").strip()
    fire_local_str = (data.get("fire_at_local") or "").strip()
    if not what or not fire_local_str:
        return None

    # ---- resolve local -> UTC ----
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")
    try:
        # accept "YYYY-MM-DD HH:MM"
        naive = datetime.strptime(fire_local_str, "%Y-%m-%d %H:%M")
        fire_local = naive.replace(tzinfo=tz)
        fire_utc = fire_local.astimezone(timezone.utc)
    except Exception as e:
        print(f"[Reminder] time parse failed ({fire_local_str}): {e}")
        return None

    # don't store reminders in the past
    if fire_utc <= datetime.now(timezone.utc):
        print(f"[Reminder] resolved time is in the past, skipping: {fire_local_str}")
        return None

    # ---- store ----
    try:
        from supabase_store import get_client
        db = get_client()
        row = {
            "user_id": user_id,
            "what": what,
            "fire_at": fire_utc.isoformat(),
            "status": "pending",
            "source": "user",
            "session_id": session_id or None,
        }
        res = db.table("reminders").insert(row).execute()
        rid = (res.data or [{}])[0].get("id")
    except Exception as e:
        print(f"[Reminder] store failed: {e}")
        return None

    # nicely formatted local time for the confirmation card
    fire_at_display = fire_local.strftime("%d %b %Y, %I:%M %p")
    print(f"[Reminder] stored '{what}' for {fire_at_display} ({user_id})")
    return {
        "id": rid,
        "what": what,
        "fire_at_local": fire_at_display,
        "fire_at_utc": fire_utc.isoformat(),
        "status": "pending",
    }


def get_due_reminders(limit: int = 50) -> list:
    """Pending reminders whose fire_at has passed — for the heartbeat."""
    from supabase_store import get_client
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()
    try:
        rows = (db.table("reminders").select("*")
                .eq("status", "pending").lte("fire_at", now)
                .order("fire_at", desc=False).limit(limit).execute()).data or []
        return rows
    except Exception as e:
        print(f"[Reminder] due-query failed: {e}")
        return []


def mark_fired(reminder_id: str):
    from supabase_store import get_client
    db = get_client()
    try:
        db.table("reminders").update(
            {"status": "fired", "fired_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", reminder_id).execute()
    except Exception as e:
        print(f"[Reminder] mark-fired failed: {e}")

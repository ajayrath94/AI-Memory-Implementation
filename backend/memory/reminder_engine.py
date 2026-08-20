"""
REMINDER ENGINE — the reactive engine's first module, now with smart nudges.

User says "kal 12 baje doctor yaad dilana" -> we detect the intent, and the LLM
designs a NUDGE SCHEDULE appropriate to what it is: an appointment gets runway
(morning-of, ~an hour before, just before); medicine gets one nudge at the time.
If the user EXPLICITLY says how/when ("3 times", "only at 5", "an hour before"),
that instruction wins. Each nudge carries its own message in Nancy's voice,
escalating from informational to gently urgent.

Reminders are EXACT and costly-if-wrong, so this is a focused single call.
"""
import os, json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_MODEL = "claude-haiku-4-5-20251001"
_MAX_NUDGES = 6   # hard safety cap regardless of what the LLM/user asks


def detect_and_store_reminder(user_id: str, text: str, session_id: str = "") -> dict | None:
    """Detect a reminder request, design its nudge schedule, store it. Returns a
    structured event for the app's confirmation card, or None."""
    try:
        from memory.time_context import time_context
    except Exception:
        return None

    tc = time_context(user_id)
    now_local = tc.get("local_time", "")
    tz_name = tc.get("timezone", "Asia/Kolkata")

    from memory.persona_names import get_companion_name
    bot_name = get_companion_name(user_id)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    except Exception as e:
        print(f"[Reminder] no anthropic client: {e}")
        return None

    prompt = f"""The user's current local time is {now_local} ({tz_name}).

User message: "{text}"

NOTE: The assistant's name is {bot_name}. If the user's message starts with or
contains "{bot_name}", they are ADDRESSING the assistant — "{bot_name}" is NEVER
the subject, owner, or the user. Strip it. The reminder belongs to the USER, not
{bot_name}. Never write "{bot_name}'s appointment" and never address the user as
"{bot_name}".

Is this a request to be REMINDED of something later? (e.g. "kal 12 baje yaad
dilana", "remind me tomorrow"). Only an explicit ask to be reminded/notified —
NOT a general mention of a future plan.

If NOT a reminder, return: {{"is_reminder": false}}

If it IS, do three things:

1. WHAT it is, and the EVENT time (when the thing actually happens), as an
   absolute local datetime.

2. Design the NUDGE SCHEDULE:
   - If the user EXPLICITLY specified timing/frequency — specific times ("at 11
     and 11:45"), a count ("remind me 3 times"), an interval ("every hour"), or
     a lead ("an hour before") — HONOR IT EXACTLY. The user's instruction always
     wins over your judgment.
   - If the user gave NO nudge instruction (just the event), design a sensible
     schedule for what KIND of thing it is:
       * appointment / outing (doctor, meeting, travel) needs runway: a heads-up
         the morning of, one about an hour before (time to get ready + travel),
         and one just before.
       * medicine / a quick task: usually ONE nudge at the time.
       * something casual: one gentle nudge.
   - If partially specified (e.g. a count but not times), honor what's given and
     place the rest sensibly.
   - Never more than {_MAX_NUDGES} nudges. If the user says something like "every
     hour" for a far-off event, use judgment — don't spam. EVERY nudge time must
     be at or before the event, never after, and in the future.

3. For EACH nudge, write what {bot_name} SAYS TO the user — warm and informational
   for early nudges, gently more urgent as the event approaches. Elderly user,
   natural Hinglish, short and caring. Reference the event. {bot_name} is the
   SPEAKER (the caring companion) — do NOT start the message with "{bot_name},"
   and never address the user as "{bot_name}". Speak directly to the user (e.g. "Aaj doctor
   appointment hai 3 baje, tayyari kar lena").

Return ONLY JSON:
{{"is_reminder": true,
  "what": "short description",
  "event_at_local": "YYYY-MM-DD HH:MM",
  "nudges": [
    {{"at_local": "YYYY-MM-DD HH:MM", "message": "{bot_name}'s words for this nudge"}}
  ]}}
No prose, only JSON."""

    try:
        resp = client.messages.create(
            model=_MODEL, max_tokens=900,
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
    event_local_str = (data.get("event_at_local") or "").strip()
    raw_nudges = data.get("nudges") or []
    if not what or not raw_nudges:
        return None

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")

    def _to_utc(s):
        return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=tz).astimezone(timezone.utc)

    now_utc = datetime.now(timezone.utc)

    # event time (optional but nice for display)
    event_utc = None
    if event_local_str:
        try:
            event_utc = _to_utc(event_local_str)
        except Exception:
            event_utc = None

    # build the nudge list: convert to UTC, drop past ones, cap, sort
    nudges = []
    for n in raw_nudges:
        at_s = (n.get("at_local") or "").strip()
        msg = (n.get("message") or "").strip()
        if not at_s or not msg:
            continue
        try:
            at_utc = _to_utc(at_s)
        except Exception:
            continue
        if at_utc <= now_utc:
            continue   # skip past nudge times
        nudges.append({"at": at_utc.isoformat(), "message": msg, "fired": False})

    if not nudges:
        print(f"[Reminder] all nudge times were in the past, skipping: {what}")
        return None

    nudges.sort(key=lambda x: x["at"])
    nudges = nudges[:_MAX_NUDGES]
    first_at = nudges[0]["at"]   # earliest nudge -> fire_at (keeps sort/display working)

    try:
        from supabase_store import get_client
        db = get_client()
        row = {
            "user_id": user_id,
            "what": what,
            "fire_at": first_at,
            "event_at": event_utc.isoformat() if event_utc else None,
            "nudges": nudges,
            "status": "pending",
            "source": "user",
            "session_id": session_id or None,
        }
        # Two paths catch the same sentence. "Dawai leni hai 10 minute mein"
        # trips detect_and_store_reminder AND Nancy's add_calendar_event tool,
        # whose spawned reminder lands here seconds earlier — so the user gets
        # one calendar row and two near-identical reminders for one request.
        # calendar.py has the mirror of this check; whichever path arrives
        # second skips.
        try:
            _dupe = (db.table("reminders").select("id,what")
                     .eq("user_id", user_id)
                     .eq("fire_at", row.get("fire_at"))
                     .eq("status", "pending")
                     .execute()).data or []
        except Exception:
            _dupe = []
        if _dupe:
            print(f"[Reminder] already pending at {row.get('fire_at')} "
                  f"({_dupe[0].get('what')!r}) — not storing a second")
            return None

        res = db.table("reminders").insert(row).execute()
        rid = (res.data or [{}])[0].get("id")
    except Exception as e:
        print(f"[Reminder] store failed: {e}")
        return None

    # confirmation card: show the event (or first nudge) + how many nudges
    def _fmt(iso):
        return datetime.fromisoformat(iso).astimezone(tz).strftime("%d %b %Y, %I:%M %p")
    display_at = event_utc.isoformat() if event_utc else first_at
    print(f"[Reminder] stored '{what}' with {len(nudges)} nudge(s) ({user_id})")
    return {
        "id": rid,
        "what": what,
        "fire_at_local": _fmt(display_at),
        "fire_at_utc": display_at,
        "nudge_count": len(nudges),
        "nudges": [{"at": n["at"], "message": n["message"]} for n in nudges],
        "status": "pending",
    }


def get_due_reminders(limit: int = 50) -> list:
    """Reminders that have at least one nudge due now (at <= now, not fired).
    Returns each as {reminder, nudge_index, message} so the caller fires the
    specific nudge with its own words."""
    from supabase_store import get_client
    db = get_client()
    now = datetime.now(timezone.utc)
    out = []
    try:
        rows = (db.table("reminders").select("*")
                .eq("status", "pending").order("fire_at", desc=False)
                .limit(limit).execute()).data or []
    except Exception as e:
        print(f"[Reminder] due-query failed: {e}")
        return []

    for r in rows:
        nudges = r.get("nudges") or []
        for i, n in enumerate(nudges):
            if n.get("fired"):
                continue
            try:
                at = datetime.fromisoformat(str(n.get("at")).replace("Z", "+00:00"))
            except Exception:
                continue
            if at <= now:
                out.append({"reminder": r, "nudge_index": i, "message": n.get("message")})
                break   # one due nudge per reminder per pass
    return out


def mark_nudge_fired(reminder_id: str, nudge_index: int):
    """Mark one nudge fired; if all nudges are now fired, complete the reminder."""
    from supabase_store import get_client
    db = get_client()
    try:
        rows = (db.table("reminders").select("nudges")
                .eq("id", reminder_id).limit(1).execute()).data or []
        if not rows:
            return
        nudges = rows[0].get("nudges") or []
        if 0 <= nudge_index < len(nudges):
            nudges[nudge_index]["fired"] = True
        all_fired = all(n.get("fired") for n in nudges)
        upd = {"nudges": nudges}
        if all_fired:
            upd["status"] = "fired"
            upd["fired_at"] = datetime.now(timezone.utc).isoformat()
        db.table("reminders").update(upd).eq("id", reminder_id).execute()
    except Exception as e:
        print(f"[Reminder] mark-nudge-fired failed: {e}")


# backward-compat: some callers may still import mark_fired
def mark_fired(reminder_id: str):
    from supabase_store import get_client
    db = get_client()
    try:
        db.table("reminders").update(
            {"status": "fired", "fired_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", reminder_id).execute()
    except Exception as e:
        print(f"[Reminder] mark-fired failed: {e}")

"""
DEMO CONTROL

    python3 backend/scripts/demo.py quiet      stop the scheduler interrupting
    python3 backend/scripts/demo.py status     what state everything is in
    python3 backend/scripts/demo.py reset      clear today so beats can repeat

    python3 backend/scripts/demo.py greeting   morning message
    python3 backend/scripts/demo.py boundary   after an event, before the next
    python3 backend/scripts/demo.py medicine   a reminder, one drug
    python3 backend/scripts/demo.py offer      a suggestion
    python3 backend/scripts/demo.py alert      chest pain -> caregiver email

    python3 backend/scripts/demo.py loud       scheduler back on

Every beat runs the REAL path — the same decision, the same composer, the same
push. The only difference is that you choose the moment rather than a cron
choosing it.

WHY THIS EXISTS
Standing in front of a room waiting for a fifteen-minute cron is dead air, and
the worse failure is a medication reminder landing while you are mid-sentence
about memory. `quiet` prevents the second; the named beats prevent the first.

RUN IT TWICE
Every beat is idempotent per day — that is deliberate, and it means a second
run does nothing. `reset` clears today's decisions so a rehearsal does not
consume the performance.
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

USER = os.getenv("DEMO_USER", "default")


def _db():
    from supabase_store import get_client
    return get_client()


def _today_start():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from memory.declared import get_declared
    tz = ZoneInfo(get_declared(USER).place.timezone)
    now = datetime.now(tz)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


# ── the scheduler ─────────────────────────────────────────────────────────────

def quiet():
    """Nothing unbidden for the next hour."""
    from datetime import datetime, timezone, timedelta
    until = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    try:
        _db().table("user_profile").update(
            {"quiet_until": until}).eq("user_id", USER).execute()
        print(f"scheduler held until {until[:16]} UTC")
    except Exception as e:
        print(f"could not set quiet_until ({e})")
        print("Pause 'Nancy scheduler pass' on cron-job.org instead.")


def loud():
    try:
        _db().table("user_profile").update(
            {"quiet_until": None}).eq("user_id", USER).execute()
        print("scheduler free again")
    except Exception as e:
        print(f"could not clear ({e}) — re-enable the cron job by hand")


# ── state ─────────────────────────────────────────────────────────────────────

def status():
    from memory.cadence import todays_ledger, budget
    from memory.alert_engine import detect_alerts
    import memory.day as D

    print(f"user: {USER}")
    print(f"ledger: {json.dumps(todays_ledger(USER))}  budget={budget(USER)}")
    print()
    print("today:")
    for e in D.events(USER):
        print(f"  {e['due_at']}  {str(e['label'])[:22]:24} {e['status']}")
    print()
    a = detect_alerts(USER)
    print(f"alerts pending: {len(a)}")
    for x in a:
        print(f"  {x.get('alert_type')}/{x.get('severity')}: "
              f"{str(x.get('message'))[:80]}")


def reset():
    """Clear today, so a rehearsal does not use up the performance."""
    start = _today_start().astimezone().isoformat()
    db = _db()
    n = 0
    try:
        r = (db.table("proactive_events").delete()
             .eq("user_id", USER).gte("created_at", start).execute())
        n = len(r.data or [])
    except Exception as e:
        print(f"events: {e}")
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from memory.declared import get_declared
        d = datetime.now(ZoneInfo(get_declared(USER).place.timezone)).date().isoformat()
        db.table("day_events").update({"status": "pending"}) \
          .eq("user_id", USER).eq("date", d).execute()
    except Exception as e:
        print(f"day: {e}")
    print(f"cleared {n} decisions; today's events are pending again")


# ── beats ─────────────────────────────────────────────────────────────────────

def _fire(action: str, label: str = ""):
    """Decide nothing — compose this action and push it."""
    from memory.schedule_engine import generate_proactive_script
    from memory.push_sender import send_push
    from memory.persona_names import get_companion_name
    from supabase_store import save_message, session_for

    r = generate_proactive_script(USER, action=action) or {}
    script = r.get("script") or ""
    if not script:
        print(f"{action}: nothing composed — try `reset`")
        return

    print(f"\n{label or action}\n  {script}\n")

    # Into her conversation before the push, so tapping the notification
    # lands on the message rather than an empty screen.
    try:
        s = session_for(USER)
        save_message(s["id"], "assistant", script, "gemini-flash-latest")
    except Exception as e:
        print(f"  (session write failed: {e})")

    n = send_push(USER, title=get_companion_name(USER), body=script,
                  data={"type": "proactive", "action": action})
    print(f"  pushed to {n} device(s)")


def greeting():   _fire("GREETING", "GREETING — opens her day")
def boundary():   _fire("BOUNDARY", "BOUNDARY — looks back, then forward")
def medicine():   _fire("MEDICATION_REMINDER", "REMINDER — one drug, named")
def offer():      _fire("RECOMMENDATION", "OFFER — something she likes")


def alert():
    """She says it, it is detected, her son is emailed.

    The whole chain, live: her words into a session, the summarizer flags it,
    the engine types it, the dispatcher sends. Takes about twenty seconds.
    """
    from supabase_store import save_message, session_for
    from memory.user_memory_store import process_session_end
    from memory.alert_engine import run_alert_engine

    text = "Meko seene mein dard ho raha hai, saans lene mein bhi dikkat hai"
    s = session_for(USER)
    save_message(s["id"], "user", text, "gemini-flash-latest")
    print(f"she said: {text}")

    # process_session_end runs the alert engine itself, so this is the whole
    # chain. Calling run_alert_engine afterwards found it already sent and
    # reported "cooldown" — which reads like a failure while the email is
    # already in the inbox.
    process_session_end(s["id"], USER)
    print("\nread, flagged, and sent — check the caregiver inbox")


def clear_alert():
    """Close the incident so the beat can run again."""
    db = _db()
    rows = (db.table("sessions").select("id")
            .eq("user_id", USER).eq("acute", True).execute()).data or []
    for r in rows:
        db.table("sessions").update(
            {"acute": False, "soft_flags": []}).eq("id", r["id"]).execute()
    print(f"closed {len(rows)} incident(s)")


BEATS = {
    "quiet": quiet, "loud": loud, "status": status, "reset": reset,
    "greeting": greeting, "boundary": boundary, "medicine": medicine,
    "offer": offer, "alert": alert, "clear-alert": clear_alert,
}

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "status"
    fn = BEATS.get(what)
    if not fn:
        print("beats:", " ".join(BEATS))
        sys.exit(1)
    fn()

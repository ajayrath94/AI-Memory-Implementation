"""
Two days of boundaries, with the conversation in between.

    railway run python3 -u backend/tests/sim_boundary_day.py
    railway run python3 -u backend/tests/sim_boundary_day.py --keep

One day tests whether a boundary looks back a few hours. Two days test whether
it looks back to YESTERDAY — which is the point of the thread, and which
nothing has exercised end to end.

WHAT THE SECOND DAY ADDS

    continuity        she made chicken curry on Sunday. Monday morning should
                      be able to reach for that without her raising it.

    a denial that is over
                      she skipped her walk on Sunday because of her knee.
                      Monday's walk is a fresh question, not yesterday's no
                      repeated.

    settled resets    food was settled on Sunday. On Monday it is open again
                      until she says otherwise.

    not the same twice
                      something offered on Sunday should not be offered again
                      on Monday.

WHAT TO READ FOR
The pairing — she says at breakfast she is making chicken, and the lunch
boundary asks how the chicken was rather than "khana kaisa tha". A boundary
that never mentions a tablet. One that does not open with her knee. And two
short sentences, because she reads this on a phone.

THERE ARE NO ASSERTIONS
Every one of those is a judgement about tone, and a message can be factually
correct and still wrong for her. Read them.
"""
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "bdaysim"

# (day, hour, minute, what she says or None, what to fire or None)
DAYS = [
    # ── Sunday: she cooks chicken and skips her walk ─────────────────────
    (0, 8, 35,  "Good morning. Nashta ho gaya, poha khaya", None),
    (0, 8, 40,  "Aaj Sunday hai, market se chicken laungi, curry banaungi lunch mein", None),
    (0, 9, 15,  None, "BOUNDARY"),
    (0, 11, 0,  None, "RECOMMENDATION"),      # food is settled — what is offered?
    (0, 13, 30, None, "BOUNDARY"),            # did it ask about the chicken?
    (0, 13, 45, "Haan chicken curry acchi bani, sab ne pasand kiya", None),
    (0, 16, 0,  "Ghutne mein thoda dard hai aaj", None),
    (0, 17, 45, "Aaj sair pe nahi jaungi, ghutna dukh raha hai", None),
    (0, 18, 15, None, "BOUNDARY"),            # she DENIED the walk
    (0, 20, 30, None, "BOUNDARY"),            # dinner, never mentioned

    # ── Monday: quieter, and the question is what survived ───────────────
    (1, 7, 30,  None, "GREETING"),            # does it know about yesterday?
    (1, 8, 40,  "Subah ki chai ho gayi", None),
    (1, 9, 15,  None, "BOUNDARY"),
    (1, 11, 0,  None, "RECOMMENDATION"),      # open again, and not Sunday's offer
    (1, 13, 30, None, "BOUNDARY"),            # she said nothing about lunch
    (1, 17, 45, None, "BOUNDARY"),            # her walk — a fresh question
]


def teardown():
    db = get_client()
    for t in ("suggestions", "memory_stm", "memory_cache", "memory_ltm",
              "subject_mentions", "user_behavioral_events", "interest_clusters",
              "messages", "sessions", "user_patterns", "day_events",
              "user_memory", "user_profile", "proactive_events"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass
    try:
        from memory.suggestions import _SETTLED
        _SETTLED.clear()
    except Exception:
        pass


def setup():
    teardown()
    db = get_client()
    db.table("user_profile").insert({
        "user_id": UID, "name": "Kamala", "language_pref": "hinglish",
        "location": "Jaipur",
        "health": {"conditions": ["knee pain"],
                   "medications": ["thyronorm", "amlodipine"]},
    }).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 5}).execute()

    for kind, label, at in (("wake", None, "06:30"),
                            ("meal", "breakfast", "08:30"),
                            ("meal", "lunch", "13:00"),
                            ("meal", "dinner", "19:30"),
                            ("routine", "Evening walk", "17:30"),
                            ("sleep", None, "22:00")):
        db.table("user_patterns").insert({
            "user_id": UID, "kind": kind, "label": label,
            "declared_at": at, "source": "declared",
        }).execute()

    for label, cat, pillar, s in (("Kishore Kumar", "sangeet", "ENTERTAINMENT", 6.0),
                                  ("khichdi", "khana", "GENERAL", 4.0),
                                  ("Sholay", "dekhna", "ENTERTAINMENT", 3.0),
                                  ("Lata Mangeshkar", "sangeet", "ENTERTAINMENT", 3.5)):
        db.table("interest_clusters").insert({
            "user_id": UID, "label": label, "pillar": pillar, "kind": "interest",
            "status": "active", "strength": s,
            "attributes": {"category": cat},
        }).execute()


def at_hour(hour: int, minute: int):
    """Pretend it is this time, for the day chain and for the picker."""
    import memory.day as D
    import memory.suggestions as S
    saved = (D.boundary, S._moment)
    real_day, real_moment = saved

    D.boundary = lambda uid, now_min=None: real_day(uid, now_min=hour * 60 + minute)

    def fake_moment(user_id):
        m = real_moment(user_id)
        m["now_min"] = hour * 60 + minute
        return m
    S._moment = fake_moment
    return saved


def restore(saved):
    import memory.day as D
    import memory.suggestions as S
    D.boundary, S._moment = saved


def close_the_day(sid: str, day_index: int):
    """End the session, and date what it wrote to the day it belongs to.

    The writes stamp today; Sunday's have to look like Sunday or Monday cannot
    reach back to them.
    """
    from memory.user_memory_store import process_session_end
    from datetime import date
    try:
        process_session_end(sid, UID)
    except Exception as e:
        print(f"  session end: {str(e)[:80]}")

    if day_index == 0:
        db = get_client()
        today = date.today().isoformat()
        y = (date.today() - timedelta(days=1)).isoformat()
        for t in ("memory_stm", "memory_cache", "subject_mentions"):
            try:
                db.table(t).update({"happened_on": y}).eq("user_id", UID) \
                  .eq("happened_on", today).execute()
            except Exception:
                pass
        try:
            db.table("suggestions").update({
                "created_at": (datetime.now(timezone.utc)
                               - timedelta(days=1)).isoformat()
            }).eq("user_id", UID).execute()
        except Exception:
            pass
        print("  (Sunday's writes dated to yesterday)")


async def run():
    from engine.engine_router import process_input
    from supabase_store import session_for
    from memory.schedule_engine import generate_proactive_script

    setup()
    names = {0: "SUNDAY", 1: "MONDAY"}
    current_day, sid = None, None

    for day, hour, minute, said, fire in DAYS:
        if day != current_day:
            if sid is not None:
                print(f"\n— {names[current_day]} ends —")
                close_the_day(sid, current_day)
                try:
                    from memory.suggestions import _SETTLED
                    _SETTLED.clear()          # a new day settles nothing
                except Exception:
                    pass
            current_day = day
            print(f"\n{'=' * 66}\n{names[day]}\n{'=' * 66}")
            sid = session_for(UID)["id"]

        stamp = f"{hour:02d}:{minute:02d}"

        if said:
            print(f"\n{stamp}  she    {said}")
            try:
                r = await process_input(said, "gemini-flash-latest", sid, UID)
                print(f"       nancy  {(r or {}).get('reply', '')[:190]}")
            except Exception as e:
                print(f"       failed: {str(e)[:90]}")

        if fire:
            saved = at_hour(hour, minute)
            try:
                out = generate_proactive_script(UID, action=fire) or {}
                print(f"\n{stamp}  [{fire}]")
                print(f"       {out.get('script', '')[:230] or '(nothing composed)'}")
            except Exception as e:
                print(f"\n{stamp}  [{fire}] failed: {str(e)[:90]}")
            finally:
                restore(saved)

    print(f"\n— {names[current_day]} ends —")
    close_the_day(sid, current_day)

    db = get_client()
    print("\nWHAT THE TWO DAYS LEFT")
    for r in (db.table("memory_stm").select("happened_on,text,untagged")
              .eq("user_id", UID).order("happened_on").execute()).data or []:
        print(f"  {r['happened_on']}  {str(r['text'])[:100]}")
        if r.get("untagged"):
            print(f"              untagged: {r['untagged']}")

    print("\n  subjects and their dates:")
    try:
        from memory.mentions import recurring
        for m in recurring(UID, min_days=1, window=7, unresolved_only=False):
            print(f"    {m['subject'][:24]:26} {m['days']} day(s)  {m['dates']}")
    except Exception as e:
        print(f"    {e}")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        try:
            asyncio.run(run())
        finally:
            if "--keep" not in sys.argv:
                print()
                teardown()
                print("torn down")

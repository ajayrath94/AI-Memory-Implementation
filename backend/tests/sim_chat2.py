"""
A longer conversation, with the things that break memory.

    railway run python3 -u backend/tests/sim_chat2.py
    railway run python3 -u backend/tests/sim_chat2.py --keep

The first chat test proved dates survive: "pichle hafte" became 5 September and
came back as 5 September. This one pushes on what it did not cover.

WHAT IS NEW HERE

  three sessions   not two. Something said on day one has to survive two
                   summarisations, not one.

  corrections      she says her son is in Delhi, then that he has moved to
                   Pune. The wrong answer is remembering both, or the first.

  relative dates   "parso", "pichle mahine", "do hafte pehle". Each has to
                   become a real day, and a real day has to come back.

  repetition       the knee mentioned four times across three sessions. The
                   trajectory should form; the reply should not recite it.

  the traps        a friend never mentioned, a date never given, a condition
                   she does not have. All three should be met with "aapne
                   bataya nahi" rather than an answer.

  restraint        she says something sad. The reply should not turn it into
                   a health report or offer to book anything.

READ THE REPLIES
No assertions. A correct fact delivered like a chart is still a failure, and
that judgement is yours.
"""
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "chatsim2"

# (kind, text). "end" closes the session and ages it.
#
#   tell   ordinary conversation
#   ask    has an answer in what came before
#   trap   has no answer; the right reply says so
#   care   emotional weight; watch the register, not the facts
TURNS = [
    ("tell", "Namaste, main Kamala. Jaipur mein rehti hoon."),
    ("tell", "Mera beta Vikram Delhi mein engineer hai."),
    ("tell", "Parso meri poti Ishita ka janamdin tha, paanch saal ki ho gayi."),
    ("tell", "Ghutne mein dard rehta hai aajkal, chalne mein dikkat hoti hai."),
    ("end",  ""),

    ("tell", "Pichle mahine Vikram Pune shift ho gaya, naya job mila hai."),
    ("tell", "Lata Mangeshkar ke gaane sunti hoon roz shaam ko."),
    ("tell", "Do hafte pehle doctor ke paas gayi thi, ghutne ke liye."),
    ("tell", "Aaj phir ghutna dukh raha hai, baarish ki wajah se lagta hai."),
    ("end",  ""),

    # ── across two session boundaries now ────────────────────────────────
    ("ask",  "Ishita ka janamdin kab tha?"),
    ("ask",  "Vikram kahan rehta hai ab?"),
    ("ask",  "Doctor ke paas kab gayi thi main?"),
    ("ask",  "Mujhe kya problem hai aajkal?"),

    # ── things it cannot know ────────────────────────────────────────────
    ("trap", "Mere pati ka naam kya tha?"),
    ("trap", "Sunita ke saath kab mili thi main?"),
    ("trap", "Meri sugar ki report kaisi thi?"),

    # ── register, not facts ──────────────────────────────────────────────
    ("care", "Aaj bahut akela lag raha hai. Koi baat karne wala nahi hai."),
]


def teardown():
    db = get_client()
    for t in ("entity_relations", "user_behavioral_events", "interest_clusters",
              "suggestions", "messages", "sessions", "user_patterns",
              "user_memory", "day_events", "care_alerts", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def setup():
    teardown()
    db = get_client()
    db.table("user_profile").insert({
        "user_id": UID, "name": "Kamala", "language_pref": "hinglish",
        "location": "Jaipur",
    }).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 0}).execute()
    try:
        from memory.testing import mark_user_as_test
        mark_user_as_test(UID)
    except Exception:
        pass


async def talk():
    from engine.engine_router import process_input
    from supabase_store import session_for
    from memory.user_memory_store import process_session_end

    today = datetime.now(timezone.utc)
    print(f"today is {today.date().isoformat()}\n")

    sid = session_for(UID)["id"]
    ended = 0

    for kind, text in TURNS:
        if kind == "end":
            ended += 1
            print(f"  — session {ended} ends —\n")
            try:
                process_session_end(sid, UID)
            except Exception as e:
                print(f"  (session end: {e})")
            # Age it so the next turn opens a new one rather than continuing.
            get_client().table("sessions").update({
                "updated_at": (today - timedelta(hours=24)).isoformat()
            }).eq("id", sid).execute()
            sid = session_for(UID)["id"]
            continue

        mark = {"tell": " ", "ask": "?", "trap": "!", "care": "~"}[kind]
        print(f"{mark} she    {text}")
        try:
            r = await process_input(text, "gemini-flash-latest", sid, UID)
            reply = (r or {}).get("reply", "") if isinstance(r, dict) else str(r)
        except Exception as e:
            reply = f"[failed: {e}]"
        print(f"  nancy  {reply[:320]}\n")

    try:
        process_session_end(sid, UID)
    except Exception:
        pass


def show():
    db = get_client()
    print("=" * 72)
    print("WHAT IT KEPT")
    print("=" * 72)

    rows = (db.table("interest_clusters").select("*")
            .eq("user_id", UID).order("strength", desc=True).execute()).data or []

    evs = [r for r in rows if r.get("kind") == "event"]
    print(f"\nevents, {len(evs)}")
    for e in sorted(evs, key=lambda x: str(x.get("happened_on") or "")):
        a = e.get("attributes") or {}
        said = a.get("said_on") or "?"
        drift = "" if said == str(e.get("happened_on")) else f"   (said {said})"
        print(f"  {e.get('happened_on')}  {str(e.get('label'))[:44]}{drift}")

    print(f"\nclusters, {len(rows) - len(evs)}")
    for r in rows:
        if r.get("kind") == "event":
            continue
        a = r.get("attributes") or {}
        print(f"  {str(r.get('label'))[:30]:32} {str(a.get('category') or '-'):9} "
              f"str={round(float(r.get('strength') or 0), 2)} n={r.get('event_count')}")

    from memory.profile_store import get_user_profile
    import json
    p = get_user_profile(UID) or {}
    print("\nprofile")
    for k in ("family", "health", "life_context"):
        if p.get(k):
            print(f"  {k}: {json.dumps(p[k], ensure_ascii=False)[:160]}")

    print("\nthe question that matters: does it think Vikram is in Delhi or Pune?")


def main():
    setup()
    asyncio.run(talk())
    show()
    if "--keep" in sys.argv:
        print(f"\n(kept as {UID})")
    else:
        print()
        teardown()
        print("torn down")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        main()

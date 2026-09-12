"""
A conversation, and then asking it what it remembers.

    railway run python3 -u backend/tests/sim_chat.py
    railway run python3 -u backend/tests/sim_chat.py --keep

Everything built today changed what the system STORES. This is the first test
of whether any of it reaches what she actually reads.

Two halves. She talks for a while, mentioning things with dates and things
without. Then she asks about them, and the replies are the answer — not the
database.

WHAT IS BEING TESTED
  dates      "pichle hafte" and "kal" have to become real days, and the reply
             has to give them back as days rather than as "recently"
  recall     something said in turn 2 has to be available in turn 9, across
             the session boundary the summariser writes
  events     "kab gayi thi" is a traversal question and the answer is a date
  restraint  it should NOT claim to remember something that was never said —
             the invented-friend failure, where a thin profile got filled in

READ THE REPLIES, NOT THE TICKS
There are no assertions. A reply can be factually right and still wrong for
her — too long, too eager, reciting a fact back like a chart. That judgement
is yours.
"""
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "chatsim"

# She talks, then she asks. The second half is the point — every question has
# an answer that only exists because of something in the first half.
TURNS = [
    # ── telling ──────────────────────────────────────────────────────────
    ("tell", "Namaste. Main Shobha, Surat se."),
    ("tell", "Mera beta Arjun Delhi mein rehta hai, doctor hai wahan."),
    ("tell", "Kal Arjun aaya tha ghar. Do din ruka."),
    ("tell", "Pichle hafte doctor ke paas gayi thi, ghutne ka check-up tha."),
    ("tell", "Kishore Kumar ke gaane bahut pasand hain mujhe."),
    ("tell", "Aaj subah mandir gayi thi, Janmashtami ka vrat tha."),
    ("tell", "Ananya, Arjun ki beti, chaar saal ki ho gayi hai."),

    # ── asking ───────────────────────────────────────────────────────────
    # each of these has an answer in what she said above, and the reply
    # should give it back as a DAY, not as "recently" or "kuch din pehle"
    ("ask",  "Arjun kab aaya tha? Yaad nahi aa raha."),
    ("ask",  "Doctor ke paas kab gayi thi main?"),
    ("ask",  "Arjun kya karta hai Delhi mein?"),
    ("ask",  "Ananya kitne saal ki hai?"),

    # ── and what it must NOT do ──────────────────────────────────────────
    # nothing was said about a daughter or about Meena. The right answer is
    # that it does not know — an invented one is the Sunita failure, where a
    # thin profile got filled in with a friend who does not exist.
    ("trap", "Meri beti ka naam kya hai?"),
    ("trap", "Meena se baat hui thi na kal?"),
]


def teardown():
    db = get_client()
    for t in ("entity_relations", "user_behavioral_events", "interest_clusters",
              "suggestions", "messages", "sessions", "user_patterns",
              "user_memory", "day_events", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def setup():
    teardown()
    db = get_client()
    db.table("user_profile").insert({
        "user_id": UID, "name": "Shobha", "language_pref": "hinglish",
        "location": "Surat",
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

    for i, (kind, text) in enumerate(TURNS):
        # Close the session halfway, so the second half has to recall across
        # a boundary rather than reading the same conversation it is in.
        if i == 7:
            print("  … session ends, summarised, extracted …\n")
            try:
                process_session_end(sid, UID)
            except Exception as e:
                print(f"  (session end: {e})")
            get_client().table("sessions").update({
                "updated_at": (today - timedelta(hours=20)).isoformat()
            }).eq("id", sid).execute()
            sid = session_for(UID)["id"]

        mark = {"tell": " ", "ask": "?", "trap": "!"}[kind]
        print(f"{mark} she    {text}")
        try:
            r = await process_input(text, "gemini-flash-latest", sid, UID)
            reply = (r or {}).get("reply", "") if isinstance(r, dict) else str(r)
        except Exception as e:
            reply = f"[failed: {e}]"
        print(f"  nancy  {reply[:300]}\n")

    try:
        process_session_end(sid, UID)
    except Exception:
        pass


def show():
    from memory.relations import timeline_for
    db = get_client()

    print("=" * 72)
    print("WHAT IT KEPT")
    print("=" * 72)

    rows = (db.table("interest_clusters").select("*")
            .eq("user_id", UID).order("strength", desc=True).execute()).data or []

    evs = [r for r in rows if r.get("kind") == "event"]
    print(f"\nevents, {len(evs)} — the day it happened")
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
              f"str={round(float(r.get('strength') or 0), 2)}")

    arjun = next((r for r in rows if r.get("label") == "Arjun"
                  and r.get("kind") != "event"), None)
    if arjun:
        tl = timeline_for(UID, arjun["id"])
        print(f"\nArjun's timeline, {len(tl)}")
        for e in tl:
            print(f"  {e.get('happened_on')}  {str(e.get('label'))[:40]}")

    from memory.profile_store import get_user_profile
    import json
    p = get_user_profile(UID) or {}
    print("\nprofile")
    for k in ("family", "health"):
        if p.get(k):
            print(f"  {k}: {json.dumps(p[k], ensure_ascii=False)[:140]}")


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

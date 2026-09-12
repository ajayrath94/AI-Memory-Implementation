"""
A month, and then a look at what it knows.

    railway run python3 -u backend/tests/sim_month.py
    railway run python3 -u backend/tests/sim_month.py --keep    leave the data
    railway run python3 -u backend/tests/sim_month.py --purge

Not assertions. A simulation, so you can read what accumulated and judge it.

Thirty days of one woman's conversation, dated backwards from today. Some
subjects recur, some are mentioned once. Her son visits, a festival passes,
her knee flares and settles, a grandson turns four. Then it prints what the
system believes, and the question is whether a stranger reading that output
would recognise her.

WHAT TO LOOK FOR
  events     dates that are the day it HAPPENED, not the day she said it
  clusters   a shape — songs under their film, dishes under a cuisine
  strength   things she returns to standing above things she mentioned once
  dormant    the single mentions sinking, ready to compress
  retrieval  "kab aaya tha beta" finding the visit and not the interest
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "monthsim"

# Thirty days back to today. (days_ago, what she said)
#
# Written to have the shapes that matter: a subject she returns to weekly
# (Arjun), one mentioned once and never again (the sari), a festival with a
# date, a health episode that resolves, and three songs named in one breath.
DAYS = [
    (30, "Namaste. Main Shobha, Surat se. Ghutne mein thoda dard rehta hai."),
    (29, "Aaj subah puja ki, phir thodi der TV dekha. Kishore Kumar ke gaane sune."),
    (28, "Mera beta Arjun Delhi mein doctor hai. Roz phone karta hai."),
    (26, "Kal padosan ke saath bazaar gayi thi, ek sari pasand aayi lekin li nahi."),
    (25, "Arjun ka phone aaya, bahut acha laga. Uski beti Ananya ki baat hui."),
    (23, "Aaj khichdi banayi. Halka khana acha lagta hai raat ko."),
    (22, "Ghutna aaj zyada dukh raha hai. Doctor ne kaha tha chalna kam karo."),
    (21, "Sholay dekhi phir se TV pe. Kitni baar dekhi hai, phir bhi acha lagta hai."),
    (19, "Arjun ne bataya wo Diwali pe aayega. Bahut khushi hui sunke."),
    (18, "Zinda, Mera Yaar, O Rangrez — Bhaag Milkha Bhaag ke gaane sun rahi thi."),
    (16, "Aaj mandir gayi thi subah. Janmashtami ka vrat rakha tha."),
    (15, "Ghutne ka dard ab thoda kam hai. Dawai kaam kar rahi hai."),
    (13, "Ananya ka janamdin tha kal. Chaar saal ki ho gayi. Video call pe baat hui."),
    (12, "South Indian khana bahut pasand hai mujhe. Dosa idli sab."),
    (10, "Arjun ka phone aaya subah. Kaam mein busy hai lekin theek hai."),
    (9,  "Shaam ko sair pe gayi thi. Mausam acha tha."),
    (7,  "Kumar Sanu ke gaane bhi acche lagte hain. Purane wale."),
    (6,  "Kal Arjun aaya tha Delhi se! Do din rukega. Bahut acha lag raha hai."),
    (5,  "Arjun ke saath baithkar purani filmein dekhin. Achha time bita."),
    (3,  "Arjun chala gaya. Ghar khali lag raha hai thoda."),
    (2,  "Aaj khichdi hi banayi. Mann nahi tha zyada kuch karne ka."),
    (1,  "Kal doctor ke paas jaana hai. Ghutne ka check-up."),
]


def teardown():
    db = get_client()
    for t in ("user_behavioral_events", "interest_clusters", "suggestions",
              "messages", "sessions", "user_patterns", "user_memory",
              "day_events", "user_profile"):
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


def live_a_month():
    """One session per day, aged backwards, extraction run on each."""
    from supabase_store import save_message
    from memory.profile_store import update_profile_from_session
    from memory.events import extract_events
    from memory.clusters import reactivate, group_session

    db = get_client()
    now = datetime.now(timezone.utc)

    for days_ago, text in DAYS:
        when = now - timedelta(days=days_ago)
        s = (db.table("sessions").insert({
            "user_id": UID, "model": "gemini-flash-latest",
            "created_at": when.isoformat(), "updated_at": when.isoformat(),
        }).execute()).data[0]

        save_message(s["id"], "user", text, "gemini-flash-latest")
        # process_session_end wants at least two messages, and a real
        # conversation has a reply. The content does not matter for
        # extraction — only hers is read — but its absence stopped the whole
        # session from being processed.
        save_message(s["id"], "assistant", "Achha, samajh gayi.",
                     "gemini-flash-latest")
        # Backdate it too, or every message looks like today.
        db.table("messages").update({"timestamp": when.isoformat()}) \
          .eq("session_id", s["id"]).execute()

        print(f"  day -{days_ago:2}  {text[:58]}")

        # What the real path does on a message, minus the reply.
        try:
            reactivate(UID, text)
        except Exception as e:
            print(f"        reactivate: {e}")
        # The real path: mood, clusters, events, profile, summary. Calling
        # the pieces by hand is what made this show no interests for an hour —
        # it was testing a path that does not exist in production.
        try:
            from memory.user_memory_store import process_session_end
            process_session_end(s["id"], UID)
        except Exception as e:
            print(f"        session end: {e}")
        try:
            group_session(UID, s["id"])
        except Exception:
            pass


def show():
    db = get_client()
    print("\n" + "=" * 72)
    print("WHAT IT KNOWS")
    print("=" * 72)

    rows = (db.table("interest_clusters").select("*")
            .eq("user_id", UID).order("strength", desc=True)
            .execute()).data or []

    events = [r for r in rows if r.get("kind") == "event"]
    things = [r for r in rows if r.get("kind") != "event"]

    print(f"\n— events, {len(events)} —  (the day it happened)")
    for e in sorted(events, key=lambda x: str(x.get("happened_on") or "")):
        a = e.get("attributes") or {}
        said = a.get("said_on") or "?"
        drift = "" if said == str(e.get("happened_on")) else f"  said {said}"
        who = ", ".join(a.get("people") or []) or "—"
        print(f"  {e.get('happened_on')}  {str(e.get('label'))[:40]:42} "
              f"{str(a.get('event_kind') or '-'):10} {who}{drift}")

    print(f"\n— what she likes, {len(things)} —")
    by_id = {t["id"]: t for t in things}
    roots = [t for t in things if not t.get("parent_id")]
    for t in sorted(roots, key=lambda x: -(x.get("strength") or 0)):
        a = t.get("attributes") or {}
        print(f"  {str(t.get('label'))[:34]:36} {str(a.get('category') or '-'):9} "
              f"str={round(float(t.get('strength') or 0), 2)}")
        for k in things:
            if k.get("parent_id") == t["id"]:
                ka = k.get("attributes") or {}
                print(f"      └ {str(k.get('label'))[:30]:32} "
                      f"str={round(float(k.get('strength') or 0), 2)}")

    orphaned = [t for t in things
                if t.get("parent_id") and t["parent_id"] not in by_id]
    if orphaned:
        print(f"  ({len(orphaned)} with a parent outside this list)")

    print("\n— what has gone quiet —  (28 days untouched, ready to compress)")
    try:
        from memory.clusters import dormant
        for d in dormant(UID):
            print(f"  {str(d.get('label'))[:34]:36} "
                  f"last {str(d.get('last_event'))[:10]}")
    except Exception as e:
        print(f"  {e}")

    print("\n— her profile —")
    from memory.profile_store import get_user_profile
    p = get_user_profile(UID) or {}
    for key in ("family", "health", "life_context"):
        v = p.get(key)
        if v:
            print(f"  {key}: {json.dumps(v, ensure_ascii=False)[:150]}")

    print("\n— asking it things —")
    from memory.events import find_events
    for q in ("kab aaya tha Arjun",
              "Ananya ka janamdin kab tha",
              "mandir kab gayi thi",
              "doctor ke paas kab jaana hai"):
        hits = find_events(UID, q, limit=2)
        ans = "; ".join(f"{h.get('happened_on')} {str(h.get('label'))[:32]}"
                        for h in hits) or "nothing"
        print(f"  {q:34} -> {ans}")


def main():
    setup()
    print("living a month\n")
    live_a_month()
    show()
    if "--keep" in sys.argv:
        print(f"\n(kept as user {UID})")
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

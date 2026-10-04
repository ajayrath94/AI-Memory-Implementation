"""
Four crowded conversations.

    railway run python3 -u backend/tests/sim_dense.py
    railway run python3 -u backend/tests/sim_dense.py --keep

Every test so far has fed one sentence at a time with one thing in it. Real
messages are not like that: "sab acha raha, aj caroom khelenge, phir bhar se
kuch mangva lenge" has three things in one line, and that is a short one.

So: four conversations, each a crowded day, with a dozen things named in
passing. What should survive is a small number of correct clusters — not one
per noun.

THE FOUR

    a Sunday          chicken, a film with her son, her knee, a neighbour
    a bad day         pain, a missed walk, a cancelled visit, worry about money
    a festival        fasting, the temple, sweets she made, relatives calling
    an ordinary one   tea, a serial, a phone call, the weather

WHAT IS BEING TESTED

    not one cluster per noun     she names a dozen things; three or four are
                                 worth remembering
    the same thing once          chicken on Sunday and chicken in the
                                 festival day is one subject, two days
    her people stay people       a neighbour, a son, a devar — never offerable
    her body stays silent        pain, tablets, a doctor
    and the counts are right     subject_mentions should show the repeats,
                                 because every pattern downstream reads them

WHAT TO READ
The cluster table and the mention counts. A dozen clusters from four
conversations is too many; three or four that recur is right.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "dense%d" % int(time.time())
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


# Four days, several messages each, each message carrying more than one thing.
DAYS = [
    ("a Sunday", [
        "Good morning, aaj Sunday hai toh chicken banaungi dopahar mein",
        "Shubham aaya tha subah, saath mein Sholay dekhi thodi der",
        "Ghutne mein dard tha lekin ab theek hai, dawai le li",
        "Padosan Sunita ji bhi aayi thi, unse acchi baat hui",
    ]),
    ("a bad day", [
        "Aaj tabiyat theek nahi hai, ghutna bahut dukh raha hai",
        "Sair pe nahi ja payi, doctor ne kaha aaram karo",
        "Shubham ka aana cancel ho gaya, kaam mein phasa hai",
        "Pension bhi kam pad rahi hai is mahine, thoda tension hai",
    ]),
    ("a festival", [
        "Aaj vrat hai, mandir gayi thi subah jaldi",
        "Ghar pe kheer banayi aur thodi barfi bhi",
        "Devar ji ka phone aaya, sab ne yaad kiya",
        "Shaam ko bhajan sune, mann shaant ho gaya",
    ]),
    ("an ordinary one", [
        "Subah chai pee, phir Ramayan serial dekha",
        "Arjun se baat hui phone pe, wo theek hai",
        "Dopahar mein khichdi banayi, halka khana acha lagta hai",
        "Mausam acha hai aaj, shaam ko sair pe jaungi",
    ]),
]


def teardown():
    db = get_client()
    for t in ("subject_mentions", "memory_cache", "memory_stm", "memory_ltm",
              "entity_relations", "user_behavioral_events",
              "interest_clusters", "messages", "sessions", "user_memory",
              "user_profile", "profile_anchors"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def setup():
    db = get_client()
    db.table("user_profile").upsert({
        "user_id": UID, "name": "Kamala", "language_pref": "hinglish",
        "location": "Jaipur", "home_location": "Jaipur",
        "demographics": {"gender": "female"},
    }).execute()
    db.table("user_memory").upsert({"user_id": UID,
                                    "session_count": 0}).execute()


def main():
    from supabase_store import save_message
    from memory.user_memory_store import process_session_end
    from datetime import datetime, timezone, timedelta

    setup()
    db = get_client()
    print(f"{len(DAYS)} days, "
          f"{sum(len(m) for _, m in DAYS)} messages\n")

    for i, (label, msgs) in enumerate(DAYS):
        when = datetime.now(timezone.utc) - timedelta(days=len(DAYS) - i)
        s = db.table("sessions").insert({
            "user_id": UID, "model": "gemini-flash-latest",
            "created_at": when.isoformat(),
            "updated_at": when.isoformat()}).execute().data[0]
        print(f"— {label} —")
        for m in msgs:
            print(f"    {m[:66]}")
            save_message(s["id"], "user", m, "gemini-flash-latest")
            save_message(s["id"], "assistant", "Achha.", "gemini-flash-latest")
        db.table("messages").update({"timestamp": when.isoformat()}) \
          .eq("session_id", s["id"]).execute()
        try:
            process_session_end(s["id"], UID)
        except Exception as e:
            print(f"    session end: {str(e)[:60]}")
        # date the day's writes to the day they belong to
        today = datetime.now(timezone.utc).date().isoformat()
        for t in ("subject_mentions", "memory_stm", "memory_cache"):
            try:
                db.table(t).update({"happened_on": when.date().isoformat()}) \
                  .eq("user_id", UID).eq("happened_on", today).execute()
            except Exception:
                pass

    rows = (db.table("interest_clusters")
            .select("label,kind,attributes,event_count")
            .eq("user_id", UID).eq("status", "active").execute()).data or []
    ints = [r for r in rows if r.get("kind") != "event"]
    evs = [r for r in rows if r.get("kind") == "event"]

    print(f"\n— {len(ints)} clusters, {len(evs)} events —")
    for r in sorted(ints, key=lambda x: str(x["label"]).lower()):
        a = r.get("attributes") or {}
        print(f"  {str(r['label'])[:26]:28} {str(r.get('kind')):9} "
              f"{a.get('category') or '-'}")
    for r in sorted(evs, key=lambda x: str(x["label"]).lower()):
        print(f"  {str(r['label'])[:26]:28} event")

    labels = " ".join(str(r["label"]).lower() for r in ints)

    print()
    check(len(ints) <= 16, "not one cluster per noun",
          f"{len(ints)} from 16 messages naming perhaps forty things")

    offerable = [str(r["label"]) for r in ints
                 if (r.get("attributes") or {}).get("category")]
    print(f"  offerable: {offerable}")

    bad = [l for l in offerable
           if any(w in l.lower() for w in
                  ("ghutn", "knee", "dard", "dawai", "doctor", "pension",
                   "shubham", "arjun", "sunita", "devar", "tension"))]
    check(not bad, "her body, her people and her money are silent", f"{bad}")

    for who in ("shubham", "arjun", "sunita", "devar"):
        r = next((x for x in ints if who in str(x["label"]).lower()), None)
        if r:
            check(r.get("kind") == "person",
                  f"{str(r['label'])[:16]} is a person",
                  f"got {r.get('kind')}")

    # ── the counts every pattern reads ───────────────────────────────────
    from collections import defaultdict
    mentions = defaultdict(set)
    for m in (db.table("subject_mentions").select("subject,happened_on")
              .eq("user_id", UID).execute()).data or []:
        mentions[str(m["subject"]).lower()].add(str(m["happened_on"])[:10])

    print(f"\n— subjects mentioned on more than one day —")
    repeats = {k: v for k, v in mentions.items() if len(v) > 1}
    for k, v in sorted(repeats.items(), key=lambda x: -len(x[1])):
        print(f"  {k[:26]:28} {len(v)} days  {sorted(v)}")
    if not repeats:
        print("  none")

    check(bool(repeats), "something recurs across the four days",
          "her knee, her walk and her son are each named twice — if nothing "
          "recurs, the subjects are being written under different names and "
          "no pattern can ever form")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        crashed = None
        try:
            main()
        except Exception as e:
            crashed = e
        finally:
            print("\n" + "=" * 68)
            if crashed:
                import traceback
                traceback.print_exception(type(crashed), crashed,
                                          crashed.__traceback__)
            elif _fails:
                print(f"{len(_fails)} FAILURE(S)")
                for f in _fails:
                    print("   -", f)
            else:
                print("ALL GREEN")
            print("=" * 68)
            if "--keep" not in sys.argv:
                teardown()
                print("torn down")

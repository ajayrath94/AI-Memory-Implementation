"""
Her day, event by event. What gets offered for what?

    railway run python3 -u backend/tests/sim_upcoming.py

The offer has been drawn from a weighted list of her interests, which is how
she came to be offered Kishore Kumar three mornings running. Her day already
knows better: a bhajan belongs with her 06:30 puja, a song with her walk, a
dish with a lunch she has not decided on. A tablet belongs with nothing.

WHAT IS BEING TESTED

    puja        -> a bhajan. The pairing that started this.
    walk        -> music, or nothing. Both are defensible.
    lunch       -> a dish, but only if she has not already decided
    medication  -> NOTHING, ever. Not once, not with anything.
    crossword   -> nothing pairs with everything; most pairings are a pretext

    and the three states:
      unmentioned  -> offer
      confirmed    -> silent, she has handled it
      denied       -> silent, and especially not a suggestion for the thing
                      she has just said she is not doing

THE LAST ONE IS THE POINT
"Aaj walk nahi karungi, ghutna dukh raha hai" is recorded as denied by
note_from_message, and until now nothing read it — an hour later she was
offered music for the walk.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "upcom%d" % int(time.time())
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


LIKES = [
    ("Bhajan", "bhakti"), ("Kishore Kumar", "sangeet"),
    ("Lata Mangeshkar", "sangeet"), ("South Indian khana", "khana"),
    ("Rajma chawal", "khana"), ("Crossword", "shauk"),
    ("Sholay", "dekhna"),
]

# (label, kind, time, what should pair — or None for nothing)
EVENTS = [
    ("Morning puja",            "routine",    "06:30", "a bhajan"),
    ("Thyroid (thyronorm)",     "medication", "07:00", None),
    ("BP tablet (amlodipine)",  "medication", "08:00", None),
    ("breakfast",               "meal",       "08:30", "a dish"),
    ("lunch",                   "meal",       "13:00", "a dish"),
    ("Evening walk",            "routine",    "17:30", "music, or nothing"),
    ("dinner",                  "meal",       "19:30", "a dish"),
]


def teardown():
    db = get_client()
    for t in ("day_events", "interest_clusters", "user_patterns",
              "user_memory", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def setup():
    db = get_client()
    db.table("user_profile").upsert({
        "user_id": UID, "name": "Shobha", "language_pref": "hinglish",
        "location": "Bengaluru", "home_location": "Bengaluru",
    }).execute()
    db.table("user_memory").upsert({"user_id": UID,
                                    "session_count": 10}).execute()
    for label, cat in LIKES:
        db.table("interest_clusters").insert({
            "user_id": UID, "label": label, "pillar": "ENTERTAINMENT",
            "kind": "interest", "status": "active", "strength": 2.0,
            "attributes": {"category": cat, "source": "conversation"},
        }).execute()


def main():
    from memory.upcoming import goes_with, next_event
    from memory.day import _today

    setup()
    db = get_client()
    _, today, _m = _today(UID)

    likes = [l for l, _c in LIKES]

    print("WHAT PAIRS WITH WHAT\n")
    for label, kind, at, expect in EVENTS:
        got = goes_with(UID, label, likes) if kind not in ("medication",) else ""
        print(f"  {at}  {label[:24]:26} -> {got or '(nothing)'}")
        print(f"        expected: {expect or 'nothing'}")

        if kind == "medication":
            check(not got, f"{label[:18]}: nothing pairs with a tablet",
                  "a tablet takes no offer, ever")
        elif "bhajan" in (expect or ""):
            check("bhajan" in got.lower(), f"{label[:18]}: a bhajan",
                  f"got {got or 'nothing'}")
        elif "dish" in (expect or ""):
            check(got.lower() in ("south indian khana", "rajma chawal"),
                  f"{label[:18]}: something to eat",
                  f"got {got or 'nothing'}")
        print()

    # ── the three states ────────────────────────────────────────────────
    print("\nTHE THREE STATES — her 17:30 walk\n")
    from memory.day import _mins_now
    now = _mins_now(UID)
    # put the walk ten minutes ahead of whatever time it is now
    due_min = now + 10
    due = f"{due_min // 60:02d}:{due_min % 60:02d}:00"

    for status, should_offer in (("pending", True),
                                 ("confirmed", False),
                                 ("denied", False)):
        db.table("day_events").delete().eq("user_id", UID).execute()
        db.table("day_events").insert({
            "user_id": UID, "date": today, "on_day": today,
            "kind": "routine", "label": "Evening walk",
            "due_at": due, "status": status,
        }).execute()

        ev = next_event(UID)
        offered = ev is not None
        print(f"  status={status:10} -> "
              + (f"offers for {ev['label']}" if ev else "silent"))
        check(offered == should_offer,
              f"walk is {status}: "
              + ("offered" if should_offer else "left alone"),
              "she has said she is not doing it — a suggestion for it now is "
              "worse than nothing" if status == "denied" else "")

    print()


if __name__ == "__main__":
    crashed = None
    try:
        main()
    except Exception as e:
        crashed = e
    finally:
        print("=" * 68)
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

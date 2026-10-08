"""
Her day, hour by hour. Where are the opportunities, and how sure are we?

    railway run python3 -u backend/tests/sim_opportunity.py

Fifteen gates, every one a reason to say no, and not one message got
through in three weeks. This asks the other question — is there an
opportunity here — and keeps the parts so a bad answer can be traced to the
signal that produced it.

WHAT TO READ
The score per hour, and what it is made of. Specifically:

    the hours around her tablets  should be ZERO, not low. A dose due is
                                  not outweighed by a good hour.
    mid-conversation              also zero. She is already here.
    her free stretch              the highest scores of the day
    and the missing list          four or five things nothing measures,
                                  named rather than defaulted to a half

WHAT THIS IS NOT
A decision. The budget and the spacing still have the last word, and
someone who has not replied in a week should be hearing less whatever the
score says.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "opp%d" % int(time.time())
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


ROUTINE = [("wake", None, "06:30"), ("routine", "Morning puja", "06:45"),
           ("meal", "breakfast", "08:30"), ("meal", "lunch", "13:00"),
           ("routine", "Evening walk", "17:30"), ("meal", "dinner", "19:30"),
           ("sleep", None, "22:00")]

MEDS = [("Thyroid (thyronorm)", "07:00"), ("BP tablet (amlodipine)", "20:00")]

LIKES = [("Bhajan", "bhakti"), ("Kishore Kumar", "sangeet"),
         ("Rajma chawal", "khana"), ("bagwani", "shauk")]


def teardown():
    db = get_client()
    for t in ("suggestions", "day_events", "subject_mentions",
              "interest_clusters", "observances", "profile_anchors",
              "user_patterns", "care_schedule", "proactive_events",
              "messages", "sessions", "user_memory", "user_profile"):
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
                                    "session_count": 20}).execute()
    for kind, label, at in ROUTINE:
        db.table("user_patterns").insert({
            "user_id": UID, "kind": kind, "label": label,
            "declared_at": at, "source": "declared"}).execute()
    for label, at in MEDS:
        db.table("care_schedule").insert({
            "user_id": UID, "label": label, "type": "medication",
            "time_of_day": at, "days": "daily", "active": True}).execute()
    for label, cat in LIKES:
        db.table("interest_clusters").insert({
            "user_id": UID, "label": label, "pillar": "ENTERTAINMENT",
            "kind": "interest", "status": "active", "strength": 2.0,
            "attributes": {"category": cat, "source": "conversation"},
        }).execute()


def main():
    import memory.day as D
    from memory.opportunity import score, WORTH_SAYING

    setup()
    # The patterns are in user_patterns; nothing has instantiated them into
    # today. proactive_check calls this; score() does not.
    from memory.day import rebuild as _rebuild
    _rebuild(UID)
    real = D._mins_now

    print("HER DAY, HOUR BY HOUR\n")
    print(f"  {'hour':6} {'score':7} {'say?':6} why")
    best_hours, zero_hours = [], []

    for h in range(6, 23):
        D._mins_now = lambda uid, _n=h * 60: _n
        o = score(UID, "Bhajan")
        say = "yes" if o.score >= WORTH_SAYING else "no"
        if o.score == 0.0:
            zero_hours.append(h)
        elif o.score >= WORTH_SAYING:
            best_hours.append(h)
        print(f"  {h:02d}:00  {o.score:5.2f}  {say:6} {o.because[:54]}")

    D._mins_now = real

    print("\nWHAT THE 11:00 SCORE IS MADE OF\n")
    D._mins_now = lambda uid: 11 * 60
    o = score(UID, "Bhajan")
    for s in o.signals:
        if s.known:
            print(f"    {s.name:16} {s.value:5.2f}  conf {s.confidence:4.0%}  {s.why[:44]}")
        else:
            print(f"    {s.name:16}    —          —      {s.why[:44]}")
    print(f"\n    {o.explain()}")
    D._mins_now = real

    print()
    check(bool(zero_hours), "some hours score zero",
          f"zero at {zero_hours} — a dose due is not outweighed by a good hour")
    check(bool(best_hours), "some hours are worth speaking into",
          f"{best_hours}")
    check(bool(o.missing), "what is unmeasured is named, not invented",
          f"{o.missing}")

    # the two that must be absolute
    print("\nTHE TWO THAT ARE NOT VOTES\n")
    D._mins_now = lambda uid: 7 * 60          # thyronorm at 07:00
    o7 = score(UID, "Bhajan")
    print(f"    a tablet due     {o7.score:.2f}  {o7.because[:50]}")
    check(o7.score == 0.0, "a tablet due is zero, not low")

    db = get_client()
    s = db.table("sessions").insert({
        "user_id": UID, "model": "gemini-flash-latest"}).execute().data[0]
    from supabase_store import save_message
    save_message(s["id"], "user", "abhi baat kar rahi hoon",
                 "gemini-flash-latest")
    D._mins_now = lambda uid: 11 * 60
    o11 = score(UID, "Bhajan")
    print(f"    mid-conversation {o11.score:.2f}  {o11.because[:50]}")
    check(o11.score == 0.0, "mid-conversation is zero",
          "she is already here; the reply should carry it")

    D._mins_now = real


if __name__ == "__main__":
    crashed = None
    try:
        main()
    except Exception as e:
        crashed = e
    finally:
        print("\n" + "=" * 70)
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
        print("=" * 70)
        if "--keep" not in sys.argv:
            teardown()
            print("torn down")

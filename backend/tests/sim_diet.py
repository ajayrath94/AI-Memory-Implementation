"""
Six people, six diets.

    railway run python3 -u backend/tests/sim_diet.py

"Is she vegetarian" has no good answer for most of India. Shravan is a month
without meat in a great many households, and then it resumes. Navratri, twice
a year. Tuesdays for Hanuman. And for others Sunday is the meat day and the
rest of the week is not.

A boolean cannot hold any of that, and the adjacency work was reading one —
it suggested Chilli Chicken because the word "chicken" appeared in a profile
list, on evidence nobody could trace.

WHO IS HERE

    Shobha      eats chicken on Sundays, never otherwise. Neither
                vegetarian nor not.
    Lakshmi     said outright she is vegetarian.
    Ramesh      eats meat, keeps Tuesdays.
    Fatima      eats meat, keeps Ramadan.
    Prakash     eats meat whenever, says nothing about days.
    Nobody      brand new. Nothing known about her at all.

WHAT IS CHECKED
What each can be offered today, and on the days that matter to them — a
Tuesday for Ramesh, a Sunday and a Wednesday for Shobha.

THE ASYMMETRY
Offering dal to someone who eats meat costs nothing. Offering mutton during
Navratri, or to someone who gave it up after a heart scare, ends trust in one
message. So the default is no, and yes has to be earned — which is why
"Nobody" must come back no.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

_fails = []
PEOPLE = ("dietA", "dietB", "dietC", "dietD", "dietE", "dietF")


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def teardown():
    db = get_client()
    for uid in PEOPLE:
        for t in ("subject_mentions", "profile_anchors", "user_memory",
                  "user_profile"):
            try:
                db.table(t).delete().eq("user_id", uid).execute()
            except Exception:
                pass


def setup():
    teardown()
    db = get_client()
    from memory.anchors import record

    today = date.today()
    sun = today - timedelta(days=(today.weekday() + 1) % 7)
    tue = today - timedelta(days=(today.weekday() - 1) % 7)

    for uid, name in zip(PEOPLE, ("Shobha", "Lakshmi", "Ramesh", "Fatima",
                                  "Prakash", "Nobody")):
        db.table("user_profile").insert({
            "user_id": uid, "name": name, "language_pref": "hinglish",
        }).execute()
        db.table("user_memory").insert({"user_id": uid,
                                        "session_count": 5}).execute()

    # Shobha — chicken on four Sundays, said nothing about diet
    for w in range(4):
        db.table("subject_mentions").insert({
            "user_id": "dietA", "subject": "chicken curry", "pillar": "GENERAL",
            "sentiment": 0.7,
            "happened_on": (sun - timedelta(weeks=w)).isoformat(),
        }).execute()

    # Lakshmi — said so
    record("dietB", "eats_meat", "no", "said", "Main shudh shakahari hoon")

    # Ramesh — eats meat, keeps Tuesdays
    record("dietC", "eats_meat", "yes", "said", "Non-veg khata hoon")
    record("dietC", "avoids_meat_on", "tuesday", "said",
           "Mangalvar ko nahi khata")
    for d in (3, 10, 17):
        db.table("subject_mentions").insert({
            "user_id": "dietC", "subject": "mutton", "pillar": "GENERAL",
            "sentiment": 0.6,
            "happened_on": (today - timedelta(days=d)).isoformat(),
        }).execute()

    # Fatima — eats meat, keeps Ramadan
    record("dietD", "eats_meat", "yes", "said", "Gosht khati hoon")
    record("dietD", "avoids_meat_on", "ramadan", "said", "Ramzan mein nahi")

    # Prakash — eats meat, no days named
    record("dietE", "eats_meat", "yes", "said", "Sab khata hoon")

    # Nobody — nothing at all
    return sun, tue


def main():
    from memory.diet import can_eat_meat_today, observed_meat_days

    sun, tue = setup()
    today = date.today()
    wed = today - timedelta(days=(today.weekday() - 2) % 7)

    print(f"today is {today.strftime('%A')}\n")

    who = dict(zip(PEOPLE, ("Shobha  (Sunday chicken)", "Lakshmi (vegetarian)",
                            "Ramesh  (keeps Tuesdays)", "Fatima  (keeps Ramadan)",
                            "Prakash (eats anything)", "Nobody  (brand new)")))

    print("— today —")
    for uid in PEOPLE:
        v = can_eat_meat_today(uid)
        print(f"  {who[uid]:28} {'meat ok' if v['ok'] else 'no meat':9} "
              f"{v['why'][:46]}")

    print("\n— on a Sunday —")
    for uid in ("dietA", "dietB", "dietC"):
        v = can_eat_meat_today(uid, sun)
        print(f"  {who[uid]:28} {'meat ok' if v['ok'] else 'no meat':9} "
              f"{v['why'][:46]}")

    print("\n— on a Tuesday —")
    for uid in ("dietA", "dietC", "dietE"):
        v = can_eat_meat_today(uid, tue)
        print(f"  {who[uid]:28} {'meat ok' if v['ok'] else 'no meat':9} "
              f"{v['why'][:46]}")

    print()
    # Shobha: her Sunday, and not a Wednesday
    check(can_eat_meat_today("dietA", sun)["ok"],
          "Shobha can have chicken on a Sunday",
          "four Sundays, nothing said — learned, not asked")
    check(not can_eat_meat_today("dietA", wed)["ok"],
          "and not on a Wednesday",
          "she is neither vegetarian nor not")

    # Lakshmi: never
    check(not can_eat_meat_today("dietB", sun)["ok"],
          "Lakshmi is never offered meat", "she said so outright")

    # Ramesh: yes, except Tuesdays
    check(can_eat_meat_today("dietC", sun)["ok"],
          "Ramesh can have mutton on a Sunday")
    check(not can_eat_meat_today("dietC", tue)["ok"],
          "and not on a Tuesday", "he keeps them")

    # Prakash: any day
    check(can_eat_meat_today("dietE", tue)["ok"],
          "Prakash is offered meat on a Tuesday",
          "Ramesh's Tuesday is not everyone's")

    # Nobody: the default
    check(not can_eat_meat_today("dietF")["ok"],
          "someone brand new is offered no meat",
          "the default is no, and yes has to be earned")

    seen = observed_meat_days("dietA")
    print(f"\n  Shobha's meat days: {seen['days']}")
    check(len(seen["weekdays"]) == 1, "her pattern is one weekday",
          f"weekdays seen: {seen['weekdays']}")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        crashed = None
        try:
            main()
        except Exception as e:
            crashed = e          # a crash is not a pass
        finally:
            print("\n" + "=" * 68)
            if crashed:
                print(f"CRASHED: {crashed}")
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

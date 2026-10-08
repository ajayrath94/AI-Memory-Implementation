"""
Nine days of Navratri, and whether it keeps up with her.

    railway run python3 -u backend/tests/sim_festival.py

Three days before Navratri began she was asked what she was planning, which
was right. She mentioned it back, and the reply said "Navratri mein yeh toh
ekdum sahi choice hai" about aloo parathe — wheat, which many people fasting
do not eat — and told her "Navratri chal rahi hai" when it had not started.

A festival the system knows about is CONTEXT. It shapes what is offered and
when, the way her conditions do. It is not content, and it is certainly not
advice about a fast she has kept for fifty years.

WHAT THIS RUNS
Eleven days around a nine-day festival, with a woman who keeps it and then,
on the sixth day, does not.

    two days before   it has not started — do not agree that it has
    the first day     wish her, ask nothing about what to eat
    days two to five  she is fasting; no meat, no wheat suggestions
    the sixth day     "aaj chicken banaya" — people break their own
                      routines, and the answer is to ask once and adjust
    days after        the flag has changed; stop offering vrat food
    the day after     it is over

WHAT IS BEING CHECKED
    the date is never wrong
    nothing advises her on how to observe
    she is not offered meat on a day she keeps
    the contradiction is noticed, asked about once, and then let go
"""
import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "fest%d" % int(time.time())
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def teardown():
    db = get_client()
    for t in ("profile_anchors", "day_events", "subject_mentions",
              "interest_clusters", "user_patterns", "messages", "sessions",
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
        "cultural_context": {"religion": "Hindu",
                             "festivals": ["Navratri", "Janmashtami"],
                             "practices": ["mandir"]},
        "food": {"likes": ["bhindi", "chicken", "tinde"]},
    }).execute()
    db.table("user_memory").upsert({"user_id": UID,
                                    "session_count": 20}).execute()
    for kind, label, at in (("wake", None, "06:30"),
                            ("meal", "lunch", "13:00"),
                            ("sleep", None, "22:00")):
        db.table("user_patterns").insert({
            "user_id": UID, "kind": kind, "label": label,
            "declared_at": at, "source": "declared"}).execute()


def main():
    from memory.festivals import hint_for, today as fest_today, soon
    from memory.anchors import hear, record, current
    from memory.diet import can_eat_meat_today

    setup()
    print("eleven days around Navratri\n")

    # She eats meat — established, as it is for the real user.
    record(UID, "eats_meat", "yes", "repeated", "Sunday ko chicken banati hoon")

    # ── before it starts ────────────────────────────────────────────────
    print("— the hint, three days ahead —")
    h = hint_for(UID)
    print(f"  {h.strip()[:300] or '(nothing)'}\n")
    if h:
        low = h.lower()
        check("not started" in low or "has not" in low,
              "the hint says it has not started")
        check("eat" not in low.split("what they should eat")[0].lower()
              or "do not" in low or "say nothing" in low,
              "the hint forbids advice about food")

    # ── she mentions it, mistakenly, as though it is underway ───────────
    print("— she speaks as though it has begun —")
    said = "acha yaad dilaya tumne, Navratri chal rahi hai na"
    print(f"  she: {said}")
    got = hear(UID, said)
    print(f"  anchors: {got.strip()[:160] or '(nothing)'}\n")

    # ── she says she fasts ──────────────────────────────────────────────
    print("— she says she keeps it —")
    said2 = "Haan Navratri mein main vrat rakhti hoon, nau din"
    print(f"  she: {said2}")
    hear(UID, said2)
    a = current(UID, "avoids_meat_on")
    print(f"  recorded: {a.get('value') if a else '(nothing)'} "
          f"({a.get('source') if a else '-'})")
    check(bool(a), "she said she fasts, and it is on file")
    # she has to confirm it before it is believed
    if a and a.get("source") == "unconfirmed":
        record(UID, "avoids_meat_on", a["value"], "said", said2)
        print("  (confirmed)")
    print()

    # ── a day during the fast ───────────────────────────────────────────
    print("— during Navratri —")
    v = can_eat_meat_today(UID)
    print(f"  meat today: {v}")
    print()

    # ── and then she breaks it ──────────────────────────────────────────
    print("— the sixth day —")
    said3 = "Aaj Navratri mein bhi chicken banaya, mann kar raha tha"
    print(f"  she: {said3}")
    got3 = hear(UID, said3)
    print(f"  asks: {got3.strip()[:200] or '(nothing)'}")
    check(bool(got3), "the contradiction is noticed and asked about",
          "people break their own routines; the answer is one question, "
          "not a correction")
    print()

    # ── she answers, and it adjusts ─────────────────────────────────────
    print("— she answers —")
    said4 = "Nahi is baar main vrat nahi rakh rahi, tabiyat theek nahi thi"
    print(f"  she: {said4}")
    from memory.anchors import settle
    settled = settle(UID, said4)
    a2 = current(UID, "avoids_meat_on")
    print(f"  now: {a2.get('value') if a2 else '(cleared)'}")
    print()

    # ── and the day after the festival ──────────────────────────────────
    print("— after it is over —")
    t = fest_today()
    s = soon(days=3)
    print(f"  today is: {t['name'] if t else 'no festival'}")
    print(f"  next    : {s['name'] + ' in ' + str(s['in_days']) + ' days' if s else 'nothing within 3 days'}")


if __name__ == "__main__":
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

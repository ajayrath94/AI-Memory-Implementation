"""
Does the meal check-in know what the chat already asked?

    railway run python3 -u backend/tests/sim_boundary_asked.py

Built from Shobha's real day, 12 Oct:

    09:03  chat      "subah ka nashta ho gaya aapka?"
    09:09  boundary  "subah ka nashta kaisa raha aapka?"         asked twice
    13:05  chat      "aapka lunch ka time ho gaya kya?"
    14:08  boundary  "...yeh kya naya mila hai aapko? Lunch kaisa gaya?"
                     asked twice, and read "Mila hai" (she had rested) as news

Two judgement calls are checked against those exact lines, then the wiring
of boundary() with the database replaced by the same conversation. Nothing
is written anywhere. Model calls only; takes about a minute.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import memory.day as day

_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def N(t, at="2026-10-12T00:00:00"):
    return {"who": "nancy", "text": t, "at": at}


def T(t, at="2026-10-12T00:00:00"):
    return {"who": "them", "text": t, "at": at}


# ── the conversations ────────────────────────────────────────────────────────

MORNING = [
    N("Kaise gaya aapka subah ka puja, Shobha ji? Aur bataiye, nashte mein kya "
      "socha hai kuch banane ka?"),
    N("Subah ki roshni mein aapki amlodipine wali tablet ka waqt ho gaya hai, "
      "Shobha ji. Ek baar ise le lijiye."),
    T("Are aj pooja ki taiyari krli,  abhi bass baki sab theek hai"),
    N("Wah, Shobha ji — pooja ki taiyari pehle hi kar liya, yeh toh bahut achhi "
      "baat hai! Aur haan, subah ka nashta ho gaya aapka? Kuch kha liya?"),
]

MIDDAY = [
    N("Subah ka nashta kaisa raha aapka? Pooja ke baad abhi thoda aaram karne "
      "ka mauka mila ya nahi?"),
    T("Mila hai"),
    N("Achha, achha — sukoon mila toh best. Thoda pair faila ke baithiye."),
    T("Ab kafi aram mehsoos horaha hai"),
    N("Yeh sunke bahut achha laga, Shobha ji. Aur aapka lunch ka time ho gaya "
      "kya? Thoda time se halka kha lena."),
]

# Nancy talked, but never about breakfast. The tablet message names it only
# as a time, and is marked a reminder the way _conversation() marks it from
# the decision log.
NOT_ASKED = [
    N("Subah ka mausam thoda thanda hai, chai ke saath Kishore Kumar ki koi "
      "purani dhun lagaiye."),
    dict(N("Nashte ke baad apni BP wali goli yaad se le lijiyega, Shobha ji."),
         kind="medication"),
    T("Haan le lungi"),
]

LUNCH_ANSWERED = MIDDAY + [T("Acha raha fal khaya hai aj")]

OTHER_MEAL = [
    N("Subah ka nashta kaisa raha?"),
    T("aloo ke parathe khaye"),
    N("Wah! Aur dopahar ko kya plan hai?"),
]


# ── 1. has Nancy already asked? ──────────────────────────────────────────────

def test_raised():
    print("\n── has Nancy already asked about it?")
    got = day._raised(MORNING, ["breakfast"])
    check(0 in got, "09:03 chat asked about breakfast: counted", f"got {got}")

    got = day._raised(MIDDAY, ["lunch"])
    check(0 in got, "13:05 chat asked about lunch: counted", f"got {got}")

    got = day._raised(NOT_ASKED, ["breakfast"])
    check(0 not in got, "a tablet reminder 'after breakfast' is not asking "
          "about breakfast", f"got {got}")

    got = day._raised(MORNING, ["breakfast", "Evening walk"])
    check(got == {0}, "of two, only the one asked about", f"got {got}")

    got = day._raised([T("Namaste")], ["lunch"])
    check(not got, "nothing from Nancy, nothing asked", f"got {got}")


def test_tagging():
    print("\n── reminders are found from the decision log")

    class _Q:
        def __init__(self, rows): self.rows = rows
        def __getattr__(self, name): return lambda *a, **k: self
        def execute(self):
            class R: pass
            r = R(); r.data = self.rows; return r

    class _DB:
        def table(self, name):
            return _Q([{"created_at": "2026-10-12T01:51:00+00:00",
                        "delivered_at": "2026-10-12T01:51:20+00:00"}])

    real = day._db
    try:
        day._db = lambda: _DB()
        convo = [N("Nashte ke baad goli le lijiye", at="2026-10-12T01:51:30+00:00"),
                 N("Nashta ho gaya aapka?", at="2026-10-12T03:33:00+00:00")]
        day._tag_reminders("sim", "2026-10-12T00:00:00+00:00", convo)
        check(convo[0].get("kind") == "medication" and not convo[1].get("kind"),
              "the reminder is tagged, the chat question is not",
              f"kinds: {[m.get('kind') for m in convo]}")
    finally:
        day._db = real


# ── 2. did SHE say anything about it? ────────────────────────────────────────

def test_their_line():
    print("\n── did she say anything about it?")
    got = day._their_line(MIDDAY, "lunch")
    check(got == "", "'Mila hai' after a question about rest is not lunch",
          f"got {got!r}")

    got = day._their_line(LUNCH_ANSWERED, "lunch")
    check("fal" in got.lower(), "'fal khaya hai aj' after lunch was asked is lunch",
          f"got {got!r}")

    got = day._their_line(OTHER_MEAL, "lunch")
    check(got == "", "breakfast parathas are not lunch", f"got {got!r}")

    got = day._their_line(MORNING, "Morning puja")
    check("pooja" in got.lower(), "'pooja ki taiyari krli' is the puja",
          f"got {got!r}")

    got = day._their_line(LUNCH_ANSWERED, "lunch", spent=["acha raha fal khaya hai aj"])
    check(got == "", "a line already used for another event is spent",
          f"got {got!r}")


# ── 3. the wiring, with no database ──────────────────────────────────────────

def test_boundary_wiring():
    print("\n── boundary() with the chat in view")
    evs = [
        {"id": "e1", "kind": "routine", "label": "Morning puja", "due_at": "07:00",
         "status": "confirmed"},
        {"id": "e2", "kind": "meal", "label": "breakfast", "due_at": "08:30",
         "status": "pending"},
        {"id": "e3", "kind": "meal", "label": "lunch", "due_at": "13:30",
         "status": "pending"},
        {"id": "e4", "kind": "routine", "label": "Evening walk", "due_at": "17:30",
         "status": "pending"},
    ]
    real = (day.events, day._conversation, day._at_iso)
    try:
        day.events = lambda uid: evs
        day._at_iso = lambda uid, mins: "2026-10-12T00:00:00+00:00"

        day._RAISED.clear()
        day._conversation = lambda uid, since: MORNING
        b = day.boundary("sim", now_min=9 * 60 + 8)
        check(b is None, "09:08: breakfast asked at 09:03, so no boundary",
              f"got {b and (b['done'].get('label'), (b.get('next') or {}).get('label'))}")

        day._RAISED.clear()
        day._conversation = lambda uid, since: MIDDAY
        b = day.boundary("sim", now_min=14 * 60 + 8)
        check(b is None, "14:08: lunch asked at 13:05, so no boundary",
              f"got {b and b['done'].get('label')}")

        day._RAISED.clear()
        day._conversation = lambda uid, since: NOT_ASKED
        b = day.boundary("sim", now_min=9 * 60 + 8)
        check(b is not None and b["done"].get("id") == "e2",
              "09:08 with breakfast never asked: the boundary still goes",
              f"got {b and b['done'].get('label')}")

        day._RAISED.clear()
        day._conversation = lambda uid, since: []
        b = day.boundary("sim", now_min=14 * 60 + 8)
        check(b is not None and b["done"].get("id") == "e3",
              "a quiet day: the lunch boundary goes as before",
              f"got {b and b['done'].get('label')}")
    finally:
        day.events, day._conversation, day._at_iso = real
        day._RAISED.clear()


if __name__ == "__main__":
    try:
        test_raised()
        test_tagging()
        test_their_line()
        test_boundary_wiring()
    finally:
        print("\n" + "=" * 70)
        print(f"{len(_fails)} FAILURE(S)" if _fails else "ALL GREEN")
        for f in _fails:
            print("   -", f)
        print("=" * 70)

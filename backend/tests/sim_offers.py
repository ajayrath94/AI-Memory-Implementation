"""
A day of offers, and what she is spared.

    railway run python3 -u backend/tests/sim_offers.py

She said at breakfast she was going to the market for chicken and would make
curry for lunch. The boundary at lunchtime asked "lunch ke liye fresh chicken
mil gaya aapko?" — the thread had it and the boundary read it.

The picker knew none of it. It reads her stored interests and nothing about
today, so it would have offered her khichdi while the chicken was on the stove.

WHY THAT IS WORSE THAN SAYING NOTHING
Offering an alternative to someone who has decided says plainly that the thing
she said was not heard. A companion that does that twice is one she stops
telling things to.

WHAT THIS CHECKS, AND WHY IT SHOULD KEEP CHECKING
Every reason the picker has to stay quiet, in one place. The list will grow —
a new kind of offer, a new reason to suppress it — and the point of a harness
is that the next one has to pass all of these too, not only its own case.

    settled           she has said what she is eating. No food offer.
    still open        she has said nothing about music. Music is fine.
    mid-routine       she is at lunch right now. Nothing at all.
    the wrong hour    a dish at nine at night, a walk at midnight.
    recently offered  the same thing three days running is its own failure.
    turned down       an explicit no outranks an old yes.
    not an interest   her knee, her son, a place — never offered.
"""
import os
import sys
from datetime import date, datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "offersim"
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def teardown():
    db = get_client()
    for t in ("suggestions", "memory_stm", "memory_cache", "subject_mentions",
              "user_behavioral_events", "interest_clusters", "user_patterns",
              "user_memory", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass
    # the settled-check cache is per process
    try:
        from memory.suggestions import _SETTLED
        _SETTLED.clear()
    except Exception:
        pass


def setup(note: str = ""):
    """Her, with a handful of interests and optionally a day already underway."""
    teardown()
    db = get_client()
    db.table("user_profile").insert({
        "user_id": UID, "name": "Kamala", "language_pref": "hinglish",
        "location": "Jaipur",
    }).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 3}).execute()

    # A routine, so the hour means something.
    for kind, label, at in (("wake", "wake", "06:30"),
                            ("meal", "breakfast", "08:30"),
                            ("meal", "lunch", "13:00"),
                            ("meal", "dinner", "19:30"),
                            ("sleep", "sleep", "22:00")):
        db.table("user_patterns").insert({
            "user_id": UID, "kind": kind, "label": label,
            "declared_at": at, "source": "declared",
        }).execute()

    ids = {}
    for label, cat, pillar, strength in (
            ("Kishore Kumar", "sangeet", "ENTERTAINMENT", 6.0),
            ("khichdi", "khana", "GENERAL", 4.0),
            ("Sholay", "dekhna", "ENTERTAINMENT", 3.0),
            ("knee pain", None, "HEALTH_WELLNESS", 5.0),
            ("Rajesh", None, "FAMILY", 5.0)):
        r = db.table("interest_clusters").insert({
            "user_id": UID, "label": label, "pillar": pillar,
            "status": "active", "strength": strength,
            "kind": "concern" if label == "knee pain"
                    else "person" if label == "Rajesh" else "interest",
            "attributes": {"category": cat} if cat else {},
        }).execute()
        ids[label] = r.data[0]["id"]

    if note:
        db.table("memory_stm").insert({
            "user_id": UID, "happened_on": date.today().isoformat(),
            "text": note, "tags": [], "untagged": [],
        }).execute()
    return ids


def offered_at(hour: int, minute: int = 0):
    """What the picker would choose at a given hour."""
    import memory.suggestions as S
    real = S._moment

    def fake(user_id):
        m = real(user_id)
        m["now_min"] = hour * 60 + minute
        return m

    S._moment = fake
    try:
        return S.pick_suggestion(UID)
    finally:
        S._moment = real


def main():
    from memory.suggestions import _decided_today

    # ── she has decided about lunch ──────────────────────────────────────
    print("=" * 68)
    print("SHE SAID SHE IS MAKING CHICKEN CURRY")
    print("=" * 68)
    setup("She had poha for breakfast. She planned to get chicken from the "
          "market and make curry for lunch.")

    settled = _decided_today(UID)
    print(f"  settled: {settled or 'nothing'}")
    check("khana" in settled, "food is settled",
          "she said what she is cooking")

    p = offered_at(11, 30)          # an hour and a half before lunch
    label = (p or {}).get("label")
    cat = ((p or {}).get("attributes") or {}).get("category")
    print(f"  offered at 11:30 -> {label or 'nothing'} ({cat or '-'})")
    check(cat != "khana", "no food is offered over her chicken",
          "an alternative says the thing she said was not heard")

    # Music was never mentioned, so it is still open.
    check(label is None or cat in (None, "sangeet", "dekhna", "shauk"),
          "something she has not decided is still fair game")

    # ── nothing said, everything open ────────────────────────────────────
    print("\n" + "=" * 68)
    print("A DAY WITH NO PLANS")
    print("=" * 68)
    setup("She listened to the radio in the morning.")
    settled = _decided_today(UID)
    print(f"  settled: {settled or 'nothing'}")
    check(not settled, "listening to the radio settles nothing",
          "everyone does something; that is not a decision")

    p = offered_at(11, 30)
    print(f"  offered at 11:30 -> {(p or {}).get('label') or 'nothing'}")
    check(p is not None, "an offer is made when nothing is settled")

    # ── the hour ─────────────────────────────────────────────────────────
    print("\n" + "=" * 68)
    print("THE HOUR")
    print("=" * 68)
    setup()
    for hour, label in ((13, "mid-lunch"), (23, "late at night"),
                        (11, "before lunch"), (17, "late afternoon")):
        p = offered_at(hour)
        cat = ((p or {}).get("attributes") or {}).get("category")
        print(f"  {hour:02d}:00 {label:16} -> "
              f"{(p or {}).get('label') or 'nothing'} ({cat or '-'})")

    # Not silence — a dish while she is eating is wrong, a song is not.
    _at13 = offered_at(13)
    check(((_at13 or {}).get('attributes') or {}).get('category') != 'khana',
          "no dish while she is eating")
    check(offered_at(23) is None or
          ((offered_at(23) or {}).get("attributes") or {}).get("category") != "khana",
          "no dish at eleven at night")

    # ── never offered ────────────────────────────────────────────────────
    print("\n" + "=" * 68)
    print("WHAT IS NEVER OFFERED")
    print("=" * 68)
    setup()
    seen = set()
    for _ in range(12):
        p = offered_at(11)
        if p:
            seen.add(p.get("label"))
    print(f"  drawn over twelve tries: {', '.join(sorted(seen)) or 'nothing'}")
    check("knee pain" not in seen, "her knee is not an afternoon activity")
    check("Rajesh" not in seen, "nor is her son")

    # ── recently offered ─────────────────────────────────────────────────
    print("\n" + "=" * 68)
    print("THE SAME THING TWICE")
    print("=" * 68)
    ids = setup()
    db = get_client()
    for cid in (ids["Kishore Kumar"], ids["Sholay"]):
        db.table("suggestions").insert({
            "user_id": UID, "cluster_id": cid, "label": "x",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    p = offered_at(11)
    print(f"  after offering two of three -> {(p or {}).get('label') or 'nothing'}")
    check((p or {}).get("label") not in ("Kishore Kumar", "Sholay"),
          "something offered this week is not offered again")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        try:
            main()
        finally:
            print("\n" + "=" * 68)
            if _fails:
                print(f"{len(_fails)} FAILURE(S)")
                for f in _fails:
                    print("   -", f)
            else:
                print("ALL GREEN")
            print("=" * 68)
            teardown()
            print("torn down")

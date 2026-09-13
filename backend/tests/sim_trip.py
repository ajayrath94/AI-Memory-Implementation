"""
Ten days in a city she does not know.

    railway run python3 -u backend/tests/sim_trip.py
    railway run python3 -u backend/tests/sim_trip.py --keep

Time is the whole thing here. The same woman in the same city needs different
messages on day zero, day three and day eight, and the current phases — orient
for the first two days, local until seven, nothing after — were written without
ever being run against a real trip.

WHAT THIS SIMULATES

  day 0    she lands. One practical thing, in passing. The chemist, not the
           cinema. She has been travelling and does not want a tour.

  day 1-2  still orienting. What she needs, not what she enjoys.

  day 3+   settled. Her own interests, one at a time, drawn across everything
           she likes rather than the first entry every day.

  day 8+   nothing. She lives there now, and a companion still pointing out
           landmarks has not noticed.

  the ask  somewhere in the middle, offer to plan something. If she says yes,
           the plan goes in a temp table — provisional, dated, and expiring
           when she goes home. A plan is not a memory and storing it in her
           interests would pollute what she likes with what she was offered.

WHAT IS NOT HERE
Background location. The gap between "she lands at three" and "she opens the
app at seven" is a few hours, and closing it would mean a permanent "Nancy is
using your location" notification on an elderly woman's phone. That is the one
thing in this product that would watch her rather than listen to her.
"""
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "default"           # her real profile, restored at the end
AWAY = ("Theosophical Housing Colony, Mumbai", 19.0330, 72.8560)
HOME = ("Bengaluru", 12.9716, 77.5946)

DAYS = [0, 1, 3, 5, 8, 11]


def _set_day(days_ago: int):
    """Put her in Mumbai, having arrived N days ago."""
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    get_client().table("user_profile").update({
        "current_location": AWAY[0],
        "current_lat": AWAY[1], "current_lng": AWAY[2],
        "arrived_at": when.isoformat(),
    }).eq("user_id", UID).execute()


def restore():
    get_client().table("user_profile").update({
        "current_location": HOME[0],
        "current_lat": HOME[1], "current_lng": HOME[2],
        "arrived_at": None,
    }).eq("user_id", UID).execute()
    print("\nback in Bengaluru, arrival cleared")


def main():
    from memory.away import phase, suggestion, hint
    from memory.schedule_engine import generate_proactive_script

    print(f"she is in {AWAY[0]}\n")

    for d in DAYS:
        _set_day(d)
        ph = phase(UID)
        s = suggestion(UID)

        print("=" * 68)
        print(f"DAY {d}   phase={ph or 'none — she lives here now'}")
        print("=" * 68)

        if not ph:
            print("  nothing. She is settled, and a companion still pointing")
            print("  out landmarks has not noticed.\n")
            continue

        subj = s.get("subject") or "(what she needs, not what she likes)"
        place = (s.get("place") or {}).get("name") or "nothing found"
        print(f"  drawn: {subj}")
        print(f"  place: {place}")

        try:
            r = generate_proactive_script(UID, action="GREETING") or {}
            print(f"\n  {r.get('script', '')[:280]}\n")
        except Exception as e:
            print(f"  compose failed: {e}\n")

    # ── the ask, and what follows ────────────────────────────────────────
    _set_day(4)
    print("=" * 68)
    print("ASKING WHETHER SHE WANTS A PLAN")
    print("=" * 68)

    from memory.away import _interests_by_category
    by_cat = _interests_by_category(UID)
    likes = [l for ls in by_cat.values() for l in ls][:3]
    print(f"  she likes: {', '.join(likes) or 'nothing recorded'}\n")

    ask = ("Shobha ji, Mumbai mein kuch ghoomne ka mann hai? Yahan aapki "
           "pasand ki kaafi cheezein hain. Bataiye toh kuch soch ke rakhun.")
    print(f"  nancy  {ask}")
    print(f"  she    Haan, kuch acha sa bata dijiye\n")

    print("  → and then, one place per interest, dated:\n")
    for cat, labels in by_cat.items():
        if not labels:
            continue
        from memory.away import _PLACE_FOR, _nearby
        place_type, _ = _PLACE_FOR[cat]
        found = _nearby(UID, place_type, limit=1)
        if found:
            print(f"     {labels[0][:22]:24} -> {found[0]['name']}")

    print("\n  These go in a temp table, not her interests: a plan is")
    print("  provisional, it has a date, and it expires when she goes home.")
    print("  What she ACCEPTS becomes something the boundary can ask about —")
    print("  'Cafe Madras gayi thi?' — which is the offer-then-boundary")
    print("  pairing, applied to a trip.")


if __name__ == "__main__":
    try:
        main()
    finally:
        if "--keep" not in sys.argv:
            restore()

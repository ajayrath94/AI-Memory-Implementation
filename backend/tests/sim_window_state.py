"""
Three days of her saying what she is doing, and the windows following.

    railway run python3 -u backend/tests/sim_window_state.py

She said "thoda aaram karungi" at two and the afternoon shut, which was
right. It stayed shut through the five o'clock walk boundary where she said
"haan sair kar aayi" — which plainly means the resting is over, and nothing
ever cleared it.

And a completed errand — "bazar ho aayi" at one in the morning, about the
day before — shut four hours of the following morning, because the reading
saw an errand and not that it was over.

So the shut is written down now, with the boundary it expires at. A
boundary goes whatever she has said: her lunch happens whether she is
resting or not, and her answer to it is what decides the rest of the day.

WHAT EACH DAY TESTS

    Monday     she rests, then the walk boundary finds her up again
    Tuesday    a completed errand shuts nothing at all
    Wednesday  she rests and stays resting — the shut survives one
               boundary that does not contradict it, and expires anyway

WHAT MATTERS
That nothing stays wrong for more than one boundary. A shut window that
outlives the next question is the bug this exists to prevent.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "wst%d" % int(time.time())
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


ROUTINE = [("wake", None, "06:00"), ("meal", "breakfast", "09:00"),
           ("meal", "lunch", "13:00"), ("routine", "Evening walk", "17:30"),
           ("meal", "dinner", "20:00"), ("sleep", None, "22:00")]


def teardown():
    db = get_client()
    for t in ("window_state", "day_events", "user_patterns", "messages",
              "sessions", "user_memory", "user_profile"):
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
    from memory.day import rebuild
    rebuild(UID)


def _open_at(uid, hour):
    """Is she free, as far as the system knows, at this hour?"""
    import memory.day as D
    from memory.windows import current
    real = D._mins_now
    D._mins_now = lambda u, _n=hour * 60: _n
    try:
        return current(uid, hour * 60) is not None
    finally:
        D._mins_now = real


def _say(uid, text, hour):
    import memory.day as D
    from memory.windows import hear_status
    real = D._mins_now
    D._mins_now = lambda u, _n=hour * 60: _n
    try:
        return hear_status(uid, text)
    finally:
        D._mins_now = real


def main():
    from memory.windows import clear_shut, describe
    import memory.day as D

    setup()
    real = D._mins_now
    D._mins_now = lambda u: 10 * 60
    print("her windows:\n" + describe(UID) + "\n")
    D._mins_now = real

    # ── Monday: she rests, then the boundary finds her up ──────────────
    print("=" * 66)
    print("MONDAY — she rests, and then she does not")
    print("=" * 66)
    clear_shut(UID)

    print(f"  14:00  free before she says anything: {_open_at(UID, 14)}")
    got = _say(UID, "Dopahar ko thoda aaram karungi", 14)
    print(f"  14:05  she: 'dopahar ko thoda aaram karungi'  -> {got}")
    shut_now = not _open_at(UID, 15)
    print(f"  15:00  afternoon shut: {shut_now}")
    check(shut_now, "resting shuts the afternoon")

    print(f"  17:30  the walk boundary goes anyway — a boundary is not")
    print(f"         governed by this, her walk happens either way")
    got = _say(UID, "Haan sair kar aayi, acha laga", 18)
    print(f"  18:00  she: 'haan sair kar aayi'  -> {got}")
    open_now = _open_at(UID, 18)
    print(f"  18:15  evening open again: {open_now}")
    check(open_now, "her answer to the boundary reopens the day",
          "the reset that was missing — it stayed shut all evening")

    # ── Tuesday: something she has already done ────────────────────────
    print()
    print("=" * 66)
    print("TUESDAY — a finished errand shuts nothing")
    print("=" * 66)
    clear_shut(UID)
    got = _say(UID, "Bazar ho aayi, sab le liya", 10)
    print(f"  10:00  she: 'bazar ho aayi, sab le liya'  -> {got}")
    still_open = _open_at(UID, 11)
    print(f"  11:00  morning still open: {still_open}")
    check(still_open, "a completed errand shuts nothing",
          "it shut four hours of her morning for a trip already made")

    # ── Wednesday: she rests and stays resting ─────────────────────────
    print()
    print("=" * 66)
    print("WEDNESDAY — and when she is still resting")
    print("=" * 66)
    clear_shut(UID)
    _say(UID, "Aaj ghar pe hi aaram karungi", 14)
    print(f"  14:00  she: 'aaj ghar pe hi aaram karungi'")
    print(f"  15:00  shut: {not _open_at(UID, 15)}")
    got = _say(UID, "Haan abhi bhi let hi hoon", 18)
    print(f"  18:00  she: 'haan abhi bhi let hi hoon'  -> {got or 'neither'}")
    print(f"  18:15  still shut: {not _open_at(UID, 18)}")
    check(got != "free", "staying put does not reopen anything")

    # ── and the expiry ─────────────────────────────────────────────────
    print()
    print("=" * 66)
    print("AND NOTHING STAYS WRONG FOR LONG")
    print("=" * 66)
    clear_shut(UID)
    _say(UID, "Thodi der aaram karungi", 14)
    db = get_client()
    row = (db.table("window_state").select("starts,until,why")
           .eq("user_id", UID).execute()).data or []
    for r in row:
        u = int(r.get("until") or 0)
        print(f"  shut {int(r['starts'])//60:02d}:00 until "
              f"{u//60:02d}:{u%60:02d} — {str(r.get('why'))[:40]}")
        check(u <= 18 * 60,
              "a shut window expires at the next boundary",
              f"until {u//60:02d}:{u%60:02d}, her walk is at 17:30")


if __name__ == "__main__":
    crashed = None
    try:
        main()
    except Exception as e:
        crashed = e
    finally:
        print("\n" + "=" * 66)
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
        print("=" * 66)
        if "--keep" not in sys.argv:
            teardown()
            print("torn down")

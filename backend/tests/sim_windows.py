"""
Her day's windows — and what she said that shut them.

    railway run python3 -u backend/tests/sim_windows.py

Her day is a sequence and the gaps between the fixed points are where
everything else belongs. Nine to one is four hours; six to seven is twenty
minutes and not a window at all.

That part is arithmetic on her own schedule — no fixed hours, no learned
hour. open_hours and best_hour were trying to compute this and came back
with 10, 11 and 15 as her free time while the hours she actually answers at
are 9, 13 and 18.

THE PART THAT MATTERS
What she says about her own time. The schedule says the afternoon is free;
she said she was going to rest. A message arriving after "thoda aaram
karungi" is the kind of thing that makes someone feel unheard, and no
amount of good timing makes up for it.

WHAT IS CHECKED

    the gaps are hers         from her schedule, not from a clock
    twenty minutes is not     her two morning tablets are not a window
    a window
    "aaram karungi"           shuts the afternoon
    "bazar jana hai sham ko"  shuts the evening
    "thak gayi hoon"          does NOT shut anything — tired is not resting
    "lunch acha tha"          says nothing about her time
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "win%d" % int(time.time())
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


# Her real day, from the board.
ROUTINE = [("wake", None, "06:00"),
           ("meal", "breakfast", "09:00"),
           ("meal", "lunch", "13:00"),
           ("routine", "Evening walk", "17:30"),
           ("meal", "dinner", "20:00"),
           ("sleep", None, "22:00")]

MEDS = [("Thyroid (thyronorm)", "06:30"), ("BP tablet (amlodipine)", "07:00")]


def teardown():
    db = get_client()
    for t in ("day_events", "user_patterns", "care_schedule", "messages",
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
    for label, at in MEDS:
        db.table("care_schedule").insert({
            "user_id": UID, "label": label, "type": "medication",
            "time_of_day": at, "days": "daily", "active": True}).execute()
    from memory.day import rebuild
    rebuild(UID)


def _say(text):
    db = get_client()
    s = (db.table("sessions").select("id").eq("user_id", UID)
         .limit(1).execute()).data
    if not s:
        s = db.table("sessions").insert({
            "user_id": UID, "model": "gemini-flash-latest"}).execute().data
    from supabase_store import save_message
    save_message(s[0]["id"], "user", text, "gemini-flash-latest")


def main():
    from memory.windows import windows_today, current, widest, describe

    setup()

    print("HER DAY, AND THE GAPS IN IT\n")
    ws = windows_today(UID, read_her_words=False)
    for w in ws:
        print(f"  {w}")

    print()
    check(bool(ws), "her day has windows in it")
    check(all(w.minutes >= 75 for w in ws),
          "twenty minutes between two tablets is not a window",
          f"narrowest is {min((w.minutes for w in ws), default=0)}m")

    # The morning tablets are half an hour apart and must not appear.
    tablet_gap = [w for w in ws if 390 <= w.starts <= 430]
    check(not tablet_gap, "nothing between her two morning tablets")

    wide = max(ws, key=lambda w: w.minutes) if ws else None
    if wide:
        print(f"  widest: {wide.clock()} ({wide.minutes}m, "
              f"after {wide.after})")

    # ── and then she speaks ─────────────────────────────────────────────
    print("\nWHAT SHE SAYS ABOUT HER OWN TIME\n")

    CASES = [
        ("Thoda aaram karungi dopahar mein", True,
         "resting shuts the afternoon"),
        ("Bazar jana hai sham ko", True, "out shuts the evening"),
        ("Thak gayi hoon", False, "tired is not resting"),
        ("Lunch acha tha aaj", False, "about a meal, not about her time"),
    ]

    db = get_client()
    for text, should_shut, why in CASES:
        # one statement at a time, on a clean slate
        for s in (db.table("sessions").select("id")
                  .eq("user_id", UID).execute()).data or []:
            db.table("messages").delete().eq("session_id", s["id"]).execute()
        _say(text)

        ws2 = windows_today(UID)
        shut = [w for w in ws2 if not w.open]
        print(f"  she: {text}")
        if shut:
            for w in shut:
                print(f"       shut {w.clock()} — {w.why_shut}")
        else:
            print(f"       nothing shut")
        check(bool(shut) == should_shut, why,
              f"{len(shut)} window(s) shut")
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

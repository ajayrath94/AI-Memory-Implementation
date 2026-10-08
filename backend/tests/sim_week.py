"""
A week of her days. Every message, in order.

    railway run python3 -u backend/tests/sim_week.py
    railway run python3 -u backend/tests/sim_week.py --keep

Everything until now has been tested a piece at a time, and the pieces have
each passed while the whole produced Kishore Kumar three mornings running, a
tablet reminder with a dosa attached, and a cold nobody asked after.

So: seven days, her real routine, stepped hour by hour. Every message printed
in the order she would receive it.

WHAT TO READ
Not the assertions. The messages — whether a week of them reads like someone
who knows her, or like a system with a schedule.

WHAT THE ASSERTIONS CATCH
Only the things that are flatly wrong:

    the same subject offered twice in one week
    a tablet reminder carrying anything but the tablet
    her conditions recited back at her
    a follow-up for something she said she was not doing
    more messages in a day than the budget allows

SHE REPLIES ON SOME DAYS AND NOT OTHERS
Which is the real test of the fade: the budget should narrow when she goes
quiet and widen when she comes back. Tuesday she has a cold, Thursday she is
out all day, Saturday she says nothing at all.
"""
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "week%d" % int(time.time())
_fails = []
IST = timezone(timedelta(hours=5, minutes=30))


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


ROUTINE = [
    ("wake",    None,                       "06:30"),
    ("routine", "Morning puja",             "06:45"),
    ("meal",    "breakfast",                "08:30"),
    ("meal",    "lunch",                    "13:00"),
    ("routine", "Evening walk",             "17:30"),
    ("meal",    "dinner",                   "19:30"),
    ("sleep",   None,                       "22:00"),
]

MEDS = [("Thyroid (thyronorm)", "07:00"), ("BP tablet (amlodipine)", "08:00"),
        ("BP tablet (amlodipine)", "20:00")]

LIKES = [("Bhajan", "bhakti"), ("Kishore Kumar", "sangeet"),
         ("Lata Mangeshkar", "sangeet"), ("South Indian khana", "khana"),
         ("Rajma chawal", "khana"), ("bagwani", "shauk"), ("Sholay", "dekhna")]

# What she says, and when. Empty days are deliberate.
WEEK = {
    0: [("09:10", "Subah puja kar li, ab nashta kar rahi hoon")],
    1: [("09:04", "Haan le li. Sardi hogai hai mujhe"),
        ("13:40", "Lunch hogaya, thodi kamzori hai")],
    2: [("09:30", "Aaj thoda behtar lag raha hai")],
    3: [("13:38", "Aaj bahar ja rahe hain Shubham ke saath"),
        ("20:10", "Bahut thak gaye, abhi aaye hain")],
    4: [("17:00", "Aaj walk nahi karungi, ghutna dukh raha hai")],
    5: [],                                    # nothing at all
    6: [("09:15", "Aaj Sunday hai, chicken banaungi dopahar mein")],
}


def teardown():
    db = get_client()
    for t in ("day_events", "suggestions", "proactive_events",
              "subject_mentions", "memory_stm", "memory_cache",
              "interest_clusters", "user_patterns", "care_schedule",
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
        "demographics": {"gender": "female"},
        "health": {"conditions": ["Chronic knee pain", "Back pain"],
                   "medications": ["Thyronorm", "Amlodipine"]},
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
    import memory.suggestions as S
    from memory.proactive_engine import proactive_check
    from memory.schedule_engine import generate_proactive_script
    from memory.cadence import may_send
    from supabase_store import save_message

    setup()
    db = get_client()
    print(f"seven days, her routine, every message\n")

    sent_subjects, per_day, all_msgs = [], Counter(), []
    real_mins_now = D._mins_now
    real_moment = S._moment

    for d in range(7):
        day_name = ["Monday", "Tuesday", "Wednesday", "Thursday",
                    "Friday", "Saturday", "Sunday"][d]
        print(f"\n{'=' * 62}\n{day_name}\n{'=' * 62}")

        # her words for the day, so a message at 13:00 has seen 09:04
        said = {t: txt for t, txt in WEEK[d]}
        sess = None

        # A fresh day. Without this, day one spends every boundary and the
        # six days after it have none left — the whole week came back as
        # nothing but tablet reminders.
        db.table("day_events").delete().eq("user_id", UID).execute()
        try:
            from memory.day import rebuild as _day_rebuild
            _day_rebuild(UID)
        except Exception:
            pass

        # A fresh day. Without this, day one spends every boundary and the
        # six days after it have none left — the whole week came back as
        # nothing but tablet reminders.
        db.table("day_events").delete().eq("user_id", UID).execute()
        try:
            from memory.day import rebuild as _day_rebuild
            _day_rebuild(UID)
        except Exception:
            pass

        for hour in range(6, 22):
            now_min = hour * 60
            D._mins_now = lambda uid, _n=now_min: _n
            S._moment = lambda uid, _n=now_min: {**real_moment(uid),
                                                 "now_min": _n}

            # anything she said this hour goes in first
            for t, txt in WEEK[d]:
                if int(t[:2]) == hour:
                    if sess is None:
                        sess = db.table("sessions").insert({
                            "user_id": UID,
                            "model": "gemini-flash-latest"}).execute().data[0]
                    save_message(sess["id"], "user", txt, "gemini-flash-latest")
                    print(f"  {t} SHE   {txt}")
                    try:
                        from memory.day import note_from_message
                        note_from_message(UID, txt)
                    except Exception:
                        pass

            try:
                dec = proactive_check(UID, override_hour=hour)
            except Exception as e:
                print(f"  {hour:02d}:00 check failed: {str(e)[:60]}")
                continue
            action = dec.get("action")
            if not action or action == "SILENCE":
                continue

            gate = may_send(UID, action)
            if not gate.get("allow"):
                continue

            try:
                out = generate_proactive_script(
                    UID, action=action, hour=hour,
                    detail=str(dec.get("detail") or "")) or {}
            except Exception as e:
                print(f"  {hour:02d}:00 compose failed: {str(e)[:70]}")
                continue
            msg = (out.get("script") or "").replace("\n", " ").strip()
            if not msg:
                continue

            print(f"  {hour:02d}:00 {action[:12]:14} {msg[:120]}")
            all_msgs.append((d, hour, action, msg))
            per_day[d] += 1
            if action == "RECOMMENDATION":
                sent_subjects.append(str(dec.get("detail") or ""))

            # record it, so cadence and the cooldown see it
            try:
                db.table("proactive_events").insert({
                    "user_id": UID, "action": action,
                    "detail": str(dec.get("detail") or ""),
                    "outcome": "delivered",
                    "delivered_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception:
                pass

        # the evening pass
        D._mins_now = lambda uid: 22 * 60 + 30
        try:
            from memory.carry import write as carry_write
            got = carry_write(UID, force=True)
            if got and got.get("carry"):
                print(f"  22:30 carry  -> {got['carry'][:100]}")
            elif got:
                print(f"  22:30 carry  -> (nothing to carry)")
        except Exception as e:
            print(f"  22:30 carry failed: {str(e)[:70]}")

    D._mins_now = real_mins_now
    S._moment = real_moment

    # ── what a week of it looks like ────────────────────────────────────
    print(f"\n{'=' * 62}\nTHE WEEK\n{'=' * 62}")
    print(f"  {len(all_msgs)} messages over 7 days")
    for d in range(7):
        print(f"    day {d + 1}: {per_day[d]}")

    kinds = Counter(a for _d, _h, a, _m in all_msgs)
    print(f"  by kind: {dict(kinds)}")

    if sent_subjects:
        print(f"  offered: {sent_subjects}")
        dupes = [s for s, n in Counter(sent_subjects).items() if n > 1]
        check(not dupes, "nothing offered twice in a week", f"{dupes}")
    else:
        print("  offered: nothing all week")

    # a tablet reminder carries only the tablet
    bad_meds = [m for _d, _h, a, m in all_msgs
                if a == "MEDICATION_REMINDER"
                and any(w in m.lower() for w in
                        ("gaana", "song", "dosa", "khana", "film", "sun "))]
    check(not bad_meds, "a tablet reminder carries only the tablet",
          (bad_meds[0][:90] if bad_meds else ""))

    # her conditions are never recited
    recited = [m for _d, _h, _a, m in all_msgs
               if "chronic" in m.lower() or "back pain" in m.lower()]
    check(not recited, "her conditions are not read back to her",
          (recited[0][:90] if recited else ""))

    # Friday she said she would not walk
    fri = [m for d, _h, _a, m in all_msgs if d == 4 and "walk" in m.lower()
           or (d == 4 and "sair" in m.lower())]
    after = [m for d, h, _a, m in all_msgs
             if d == 4 and h >= 17 and ("sair" in m.lower() or "walk" in m.lower())]
    check(not after, "nothing about the walk after she said she would not",
          (after[0][:90] if after else ""))

    busiest = max(per_day.values()) if per_day else 0
    check(busiest <= 7, "no day is overwhelming", f"busiest day: {busiest}")


if __name__ == "__main__":
    crashed = None
    try:
        main()
    except Exception as e:
        crashed = e
    finally:
        print("\n" + "=" * 62)
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
        print("=" * 62)
        if "--keep" not in sys.argv:
            teardown()
            print("torn down")

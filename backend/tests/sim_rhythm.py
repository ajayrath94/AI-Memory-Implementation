"""
Four weeks, and what becomes a Sunday.

    railway run python3 -u backend/tests/sim_rhythm.py
    railway run python3 -u backend/tests/sim_rhythm.py --keep

Rhythms were built against seeded dates. This runs them against four weeks of
real conversation — written through the live session-end path, so the subjects
come from the topics extractor rather than from a list someone typed.

WHAT SHOULD FORM

    chicken       four Sundays. A rhythm, and the thing a companion would
                  notice: "aaj Sunday hai, chicken banayengi?"

    khichdi       five scattered days. Often, but tied to no day — a habit,
                  not a Sunday.

    dal           three days in one week early on, nothing since. A spell.
                  She was doing it and stopped, and promoting it as a habit
                  would be the opposite of what it is.

    the temple    three Tuesdays. A second rhythm, to check one subject is
                  not hard-coded into the logic.

WHAT SHOULD NOT

    poha          she eats it most mornings but rarely says so. Two mentions
                  is not a pattern, however true it is.

WHAT TO READ
The offers at the end. A rhythm is a reason to offer, and a reason should
produce a different message from a weighted draw — the day named, the subject
once, lightly. If it recites "four of the last four Sundays", the count has
leaked from the decision into the words.
"""
import os
import sys
import asyncio
from datetime import date, datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "rhythmsim"
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def teardown():
    db = get_client()
    for t in ("subject_mentions", "memory_cache", "memory_stm", "memory_ltm",
              "suggestions", "user_behavioral_events", "interest_clusters",
              "messages", "sessions", "user_patterns", "day_events",
              "user_memory", "user_profile", "proactive_events"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass
    try:
        from memory.suggestions import _SETTLED
        _SETTLED.clear()
    except Exception:
        pass


def setup():
    teardown()
    db = get_client()
    db.table("user_profile").insert({
        "user_id": UID, "name": "Kamala", "language_pref": "hinglish",
        "location": "Jaipur",
    }).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 0}).execute()
    for kind, label, at in (("wake", None, "06:30"),
                            ("meal", "breakfast", "08:30"),
                            ("meal", "lunch", "13:00"),
                            ("meal", "dinner", "19:30"),
                            ("sleep", None, "22:00")):
        db.table("user_patterns").insert({
            "user_id": UID, "kind": kind, "label": label,
            "declared_at": at, "source": "declared",
        }).execute()
    try:
        from memory.testing import mark_user_as_test
        mark_user_as_test(UID)
    except Exception:
        pass


def _days():
    """Four weeks of conversation, dated backwards from the last Sunday."""
    today = date.today()
    sun = today - timedelta(days=(today.weekday() + 1) % 7)
    tue = today - timedelta(days=(today.weekday() - 1) % 7)

    said = []
    # Sundays — chicken
    for w in range(4):
        said.append((sun - timedelta(weeks=w),
                     "Aaj Sunday hai, chicken curry banayi"))
    # Tuesdays — the temple
    for w in range(3):
        said.append((tue - timedelta(weeks=w),
                     "Aaj mandir gayi thi subah"))
    # khichdi, scattered
    for d in (2, 9, 16, 23, 27):
        said.append((today - timedelta(days=d), "Khichdi banayi aaj"))
    # dal — three days in one week, early, nothing since
    for d in (24, 26, 28):
        said.append((today - timedelta(days=d), "Dal banayi thi aaj"))
    # poha — twice only
    for d in (5, 20):
        said.append((today - timedelta(days=d), "Nashte mein poha khaya"))

    said.sort(key=lambda x: x[0])
    return said


async def live():
    """Through the real path, so subjects come from the extractor."""
    from supabase_store import save_message
    from memory.user_memory_store import process_session_end

    db = get_client()
    today_iso = date.today().isoformat()

    for when, text in _days():
        ts = datetime.combine(when, datetime.min.time(),
                              tzinfo=timezone.utc) + timedelta(hours=8)
        s = db.table("sessions").insert({
            "user_id": UID, "model": "gemini-flash-latest",
            "created_at": ts.isoformat(), "updated_at": ts.isoformat(),
        }).execute().data[0]
        save_message(s["id"], "user", text, "gemini-flash-latest")
        save_message(s["id"], "assistant", "Achha.", "gemini-flash-latest")
        db.table("messages").update({"timestamp": ts.isoformat()}) \
          .eq("session_id", s["id"]).execute()

        print(f"  {when} {when.strftime('%a')}  {text[:44]}")
        try:
            process_session_end(s["id"], UID)
        except Exception as e:
            print(f"        session end: {str(e)[:70]}")

        # The writes stamp today; move them to the day they belong to.
        for t in ("subject_mentions", "memory_stm", "memory_cache"):
            try:
                db.table(t).update({"happened_on": when.isoformat()}) \
                  .eq("user_id", UID).eq("happened_on", today_iso).execute()
            except Exception:
                pass


def main():
    from memory.rhythms import rhythms_for, due_today, hint
    from memory.promotion import habits
    from memory.mentions import count_for
    from memory.schedule_engine import generate_proactive_script
    import memory.rhythms as R

    setup()
    print(f"{len(_days())} conversations over four weeks\n")
    asyncio.run(live())

    print("\n— what she said, and when —")
    for subj in ("chicken", "khichdi", "dal", "mandir", "poha"):
        c = count_for(UID, subj)
        days = [d[5:] for d in c["dates"]]
        print(f"  {subj:10} {c['days']} day(s)  {' '.join(days[:8])}")

    print("\n— rhythms —")
    found = rhythms_for(UID)
    for r in found:
        print(f"  {r['subject'][:22]:24} {r['weekday']:10} "
              f"{r['on_that_day']}/{r['of']}  ({r['share']})")
    if not found:
        print("  none")

    names = " ".join(r["subject"].lower() for r in found)
    days_of = {r["subject"].lower(): r["weekday"] for r in found}

    check("chicken" in names, "chicken is a Sunday",
          f"{[r['weekday'] for r in found if 'chicken' in r['subject'].lower()]}")
    check(any("mandir" in n or "temple" in n for n in names.split()),
          "the temple is a Tuesday",
          "a second rhythm, so nothing is hard-coded")
    check("khichdi" not in names, "khichdi is not tied to a day",
          "five days, spread out — a habit, not a Sunday")
    check("dal" not in names, "dal is not a rhythm", "it was a spell")
    check("poha" not in names, "poha is not a pattern", "twice is not a habit")

    print("\n— what promotion would take —")
    for h in habits(UID):
        print(f"  {h['subject'][:22]:24} {h['days']} days  {h.get('rhythm','')}")
    promoted = " ".join(h["subject"].lower() for h in habits(UID))
    check("dal" not in promoted, "a spell does not promote as a habit",
          "three in one week, nothing since — she stopped")

    # ── and what she would be sent, on each day ──────────────────────────
    today = date.today()
    sun = today - timedelta(days=(today.weekday() + 1) % 7)
    tue = today - timedelta(days=(today.weekday() - 1) % 7)
    wed = tue + timedelta(days=1)

    real = R.due_today
    for label, day in (("a Sunday", sun), ("a Tuesday", tue),
                       ("a Wednesday", wed)):
        R.due_today = lambda uid, t=None, _d=day: real(uid, _d)
        try:
            out = generate_proactive_script(UID, action="RECOMMENDATION") or {}
            print(f"\n— {label} —")
            print(f"  {out.get('script','')[:220] or '(nothing)'}")
        except Exception as e:
            print(f"\n— {label} — failed: {str(e)[:80]}")
        finally:
            R.due_today = real


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
            if "--keep" not in sys.argv:
                teardown()
                print("torn down")

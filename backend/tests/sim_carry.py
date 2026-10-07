"""
Five evenings. What does each leave for the morning?

    railway run python3 -u backend/tests/sim_carry.py

She said on Tuesday morning that she had caught a cold. The companion asked
after it at lunch, which was right, and on Wednesday asked about her breakfast
and offered her a Kishore Kumar song. The cold was never mentioned again,
because nothing has ever looked at a day whole.

THE FIVE DAYS
Real conversations, lightly trimmed, plus two constructed to test the edges.

    the cold          she says it in the morning, it is asked about at lunch,
                      she never says whether it got better
    the zoo           out all day, short answers, nothing to follow up
    answered          the morning asks, she says she is better — it is
                      finished, and tonight must leave nothing
    asked and ignored raised once, no answer. One more is fair. A third is
                      supervision.
    the suggestion    the companion suggested paneer, she said another time.
                      She never raised it. Asking tomorrow is nagging.

WHAT TO READ
The carry line for each. Three of the five should be EMPTY — if every day
leaves something, the prompt is too generous and she will learn to ignore the
morning.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "carry%d" % int(time.time())
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


DAYS = [
    ("the cold", [
        ("companion", "Subah ka pyaar, Shobha ji, apna Thyronorm le lijiye."),
        ("user", "Haan le li. Sardi hogai hai mujhe"),
        ("companion", "Ohh sardi ho gayi? Garam paani piyiye aur shawl le lijiye."),
        ("user", "Krliya"),
        ("companion", "Aapki sardi kaisi hai abhi, aur lunch kaisa raha?"),
        ("user", "Lunch hogaya"),
        ("companion", "Thak gayi hongi, ab aaram kariye."),
    ], "should carry — the cold, never resolved"),

    ("the zoo", [
        ("companion", "Lunch kaisa raha aapka?"),
        ("user", "Biryani kha rahe hai and then zoo"),
        ("companion", "Arre wah! Zoo se aake bataiye kaunse jaanwar pasand aaye."),
        ("user", "Okay"),
    ], "should NOT carry — a day out, finished"),

    ("answered", [
        ("companion", "Sardi kaisi hai aaj, thodi behtar?"),
        ("user", "Haan ab theek hoon, bukhar nahi hai"),
        ("companion", "Chalo accha hai. Nashta ho gaya?"),
        ("user", "Haan poha khaya"),
    ], "should NOT carry — she said she is better"),

    ("the suggestion", [
        ("companion", "Aaj kuch alag banane ka mann hai? Paneer ho jaye?"),
        ("user", "Nahi aaj nahi, phir kabhi"),
        ("companion", "Theek hai, jab mann ho tab."),
        ("user", "Haan"),
    ], "should NOT carry — she never raised it"),

    ("bad news", [
        ("companion", "Shaam kaisi rahi aapki?"),
        ("user", "Shubham ka aana cancel ho gaya, kaam mein phasa hai"),
        ("companion", "Ohh, aapko bura laga hoga."),
        ("user", "Haan bahut intezaar kar rahi thi"),
    ], "should carry — a disappointment has a tomorrow"),
]


def teardown():
    db = get_client()
    for t in ("day_events", "messages", "sessions", "user_memory",
              "user_profile", "user_patterns"):
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
                                    "session_count": 10}).execute()
    for kind, label, at in (("wake", None, "06:30"),
                            ("sleep", None, "22:00")):
        db.table("user_patterns").insert({
            "user_id": UID, "kind": kind, "label": label,
            "declared_at": at, "source": "declared"}).execute()


def main():
    from memory.carry import write, yesterdays
    from supabase_store import save_message
    from memory.day import _today

    setup()
    db = get_client()
    _, today, _m = _today(UID)
    print(f"{len(DAYS)} days\n")

    for name, turns, expect in DAYS:
        # each day fresh: one day's talk, one evening pass
        db.table("day_events").delete().eq("user_id", UID).execute()
        for s in (db.table("sessions").select("id")
                  .eq("user_id", UID).execute()).data or []:
            db.table("messages").delete().eq("session_id", s["id"]).execute()
        db.table("sessions").delete().eq("user_id", UID).execute()

        s = db.table("sessions").insert({
            "user_id": UID, "model": "gemini-flash-latest"}).execute().data[0]
        for role, text in turns:
            save_message(s["id"], "user" if role == "user" else "assistant",
                         text, "gemini-flash-latest")

        got = write(UID, force=True) or {}
        carry = (got.get("carry") or "").strip()
        shape = (got.get("shape") or "").strip()

        print(f"— {name} —")
        print(f"    {expect}")
        print(f"    carry: {carry or '(nothing)'}")
        print(f"    shape: {shape or '(nothing)'}")

        wants_carry = expect.startswith("should carry")
        check(bool(carry) == wants_carry, name,
              f"carry={'yes' if carry else 'no'}, expected "
              f"{'yes' if wants_carry else 'no'}")
        check(bool(shape), f"{name}: a shape either way")
        print()

    # and the morning's line, from the last day that carried
    db.table("day_events").delete().eq("user_id", UID).execute()
    for role, text in DAYS[0][1]:
        pass
    print("— what the morning would say —")
    from memory.carry import hint
    # write yesterday's carry by hand, dated yesterday
    from datetime import datetime, timedelta
    import json as _j
    y = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
    db.table("day_events").insert({
        "user_id": UID, "date": y, "on_day": y, "kind": "carry",
        "label": "cold", "due_at": "22:00:00", "status": "pending",
        "detail": _j.dumps({"carry": "She said she had caught a cold and did "
                                     "not say whether it got better.",
                            "shape": "Quiet day, unwell, stayed in."}),
    }).execute()
    h = hint(UID)
    print(f"  {h.strip()[:260] or '(nothing)'}")
    check(bool(h), "the morning has something to ask")

    # raised once, no answer — one more is fair
    h2 = hint(UID)
    print(f"\n  asked again, same day: {'still offered' if h2 else 'silent'}")


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

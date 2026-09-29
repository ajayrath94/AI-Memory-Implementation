"""
Does an emergency reach her son?

    railway run python3 -u backend/tests/sim_urgent.py

This is the path that matters most and it had two faults. It ran only at
session end, so "saans nahi aa rahi" at two in the morning reached her son
when the session closed — hours later. And the backstop was a word list:
chest pain, gir gaya, saans nahi. It missed "saans nahi aa rahi", a woman
saying she cannot breathe, because the list had the phrase and not the
sentence.

WHAT THIS CHECKS

    it reads danger         a fall, chest pain, breathlessness, in Hindi,
                            Hinglish, Tamil, Bengali and English. No list.

    it leaves her alone     a knee she has lived with for years, a bad
                            afternoon, someone ELSE being unwell. A false
                            alarm is cheap, but a companion that panics at
                            every mention of pain is one she stops telling
                            things to.

    it fires on the message they are told in seconds, not when the session
                            closes.

    once per incident       someone who has fallen says so three times. That
                            is one emergency and one phone call.

    and it is recorded      so a caregiver saying "I never heard anything"
                            can be checked.

NOTHING IS SENT
The caregiver's address is replaced for the run, so no real email goes out.
What is measured is whether it WOULD have.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "urgentsim"
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


# (what she said, should it alarm, why it is here)
CASES = [
    # ── she is in trouble now ────────────────────────────────────────────
    ("Bathroom mein gir gayi, uth nahi pa rahi", True,
     "a fall, and she cannot get up"),
    ("saans nahi aa rahi", True,
     "the exact sentence the word list missed"),
    ("Chest mein bahut dard ho raha hai abhi", True, "chest pain, now"),
    ("மூச்சு விட முடியவில்லை", True, "Tamil — cannot breathe"),
    ("আমি পড়ে গেছি, উঠতে পারছি না", True, "Bengali — fallen, cannot rise"),
    ("I've fallen and I can't get up", True, "plain English"),
    ("Bahut ghabrahat ho rahi hai, dil tez chal raha hai", True,
     "frightened, heart racing"),

    # ── she is not ───────────────────────────────────────────────────────
    ("Ghutne mein dard rehta hai aajkal", False,
     "a knee she has had for years"),
    ("Aaj thoda thak gayi hoon", False, "tired, which is Tuesday"),
    ("Beta ki tabiyat theek nahi hai", False, "someone ELSE is unwell"),
    ("Pichle hafte gir gayi thi, ab theek hoon", False,
     "last week, and she is fine now"),
    ("Aaj mausam bahut acha hai", False, "nothing at all"),
    ("Doctor ne kaha operation karana padega", False,
     "serious, and not happening this minute — the caregiver hears via the "
     "weekly path, not a 2am phone call"),
]


def teardown():
    db = get_client()
    for t in ("care_alerts", "messages", "sessions", "user_memory",
              "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass
    try:
        db.table("care_relationships").delete().eq("user_id", UID).execute()
    except Exception:
        pass


def setup():
    teardown()
    db = get_client()
    db.table("user_profile").insert({
        "user_id": UID, "name": "Kamala", "language_pref": "hinglish",
        "health": {"conditions": ["knee pain"]},
    }).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 3}).execute()

    # A caregiver, or the send loop finds nobody and the whole path is
    # untested — which is how this first ran: two alerts fired, no email, no
    # record, and the cooldown never exercised.
    cg = db.table("caregivers").insert({
        "name": "Test Son", "email": "nobody@example.invalid",
        "org_type": "family",
    }).execute().data[0]
    db.table("care_relationships").insert({
        "user_id": UID, "caregiver_id": cg["id"],
        "relationship": "beta", "active": True,
    }).execute()
    globals()["_CG_ID"] = cg["id"]


def main():
    from memory.alert_engine import in_danger_now
    import memory.alert_engine as A

    setup()
    print(f"{len(CASES)} things she might say\n")

    right = 0
    for said, should, why in CASES:
        r = in_danger_now(said, UID)
        got = bool(r["danger"])
        mark = "ok  " if got == should else "FAIL"
        if got == should:
            right += 1
        else:
            _fails.append(said[:30])
        print(f"{mark} {said[:38]:40} {str(got):5} {r['what'][:28]}")
        if got != should:
            print(f"       expected {should} — {why}")

    print(f"\n  {right} of {len(CASES)}")

    # ── one incident, one call ───────────────────────────────────────────
    print("\n— she says it three times in two minutes —")
    sent_to = []
    real_send = A.send_email_alert

    def pretend(to_email, caregiver_name, user_name, alerts, user_id=""):
        sent_to.append(alerts[0].get("summary"))
        return True

    A.send_email_alert = pretend
    try:
        for line in ("Gir gayi hoon", "Uth nahi pa rahi", "Koi hai kya"):
            A.alert_now(UID, line)
            print(f"    said: {line}")
    finally:
        A.send_email_alert = real_send

    print(f"    emails that would have gone: {len(sent_to)}")
    check(len(sent_to) <= 1, "one emergency is one phone call",
          f"{len(sent_to)} sent: {sent_to}")

    # ── and it was recorded ──────────────────────────────────────────────
    rows = (get_client().table("care_alerts").select("severity,message,sent_via")
            .eq("user_id", UID).execute()).data or []
    print(f"\n  recorded: {len(rows)} row(s)")
    for r in rows:
        print(f"    {r.get('severity')}  {str(r.get('message'))[:40]}  "
              f"via {r.get('sent_via')}")
    check(bool(rows), "the alert is on the record",
          "a caregiver saying 'I never heard anything' has to be checkable")


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

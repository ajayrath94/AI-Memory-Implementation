"""
The same offer, on five different kinds of day.

    railway run python3 -u backend/tests/sim_offer_day.py

Boundaries read the conversation and recommendations never did. So an offer
at three in the afternoon knew nothing about lunch — which is how "garma garm
chole" arrived two days after she had eaten chole, and why every offer read
the same whatever sort of morning she had had.

WHAT THIS RUNS
The same subject offered five times, with only one thing different each time:
what she has been saying since breakfast.

    a quiet, sore morning       tired, her knee hurts
    a cheerful one              good sleep, breakfast was nice
    already done it             she has been listening to Kishore all morning
    a sad one                   she misses her husband
    nothing at all              she has not written today

WHAT TO READ
The five messages. They should not be interchangeable.

    sore      gentler. Something she can do sitting down. And NOT a word
              about her knee — she knows it hurts, and being told is not
              company.
    cheerful  can be livelier.
    already   should not offer the thing she has spent the morning doing.
    sad       the hardest. Neither jolly nor mournful, and not a lecture
              about keeping busy.
    nothing   the plain version — which is what every one of them used to
              be.

If the sore one and the cheerful one read the same, the window is reaching
the prompt and doing nothing with it, which is what the weather did for a
week.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "offerdaysim"

DAYS = [
    ("a sore, tired morning", [
        "Aaj thoda thak gayi hoon",
        "Ghutne mein subah se dard hai",
    ]),
    ("a cheerful one", [
        "Aaj neend acchi aayi, subah fresh lag raha hai",
        "Nashte mein poha banaya tha, bahut acha bana",
    ]),
    ("she has been doing it all morning", [
        "Subah se Kishore Kumar ke gaane sun rahi hoon",
        "Purane gaane sunke mann khush ho gaya",
    ]),
    ("a sad one", [
        "Aaj unki bahut yaad aa rahi hai",
        "Ghar khali khali lagta hai",
    ]),
    ("nothing at all", []),
]


def teardown():
    db = get_client()
    for t in ("suggestions", "memory_stm", "subject_mentions",
              "user_behavioral_events", "interest_clusters", "user_patterns",
              "messages", "sessions", "user_memory", "user_profile"):
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
        "location": "Jaipur", "home_location": "Jaipur",
        "health": {"conditions": ["Knee pain"]},
    }).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 8}).execute()
    for kind, label, at in (("wake", None, "06:30"),
                            ("meal", "breakfast", "08:30"),
                            ("meal", "lunch", "13:00"),
                            ("meal", "dinner", "19:30"),
                            ("sleep", None, "22:00")):
        db.table("user_patterns").insert({
            "user_id": UID, "kind": kind, "label": label,
            "declared_at": at, "source": "declared",
        }).execute()

    # One subject, so the only thing that differs between the runs is the day.
    db.table("interest_clusters").insert({
        "user_id": UID, "label": "Kishore Kumar", "pillar": "ENTERTAINMENT",
        "kind": "interest", "status": "active", "strength": 3.0,
        "attributes": {"category": "sangeet", "source": "conversation"},
    }).execute()


def main():
    import memory.suggestions as S
    from memory.schedule_engine import generate_proactive_script

    setup()
    real = S.recent_window

    for label, said in DAYS:
        if said:
            window = ("\n\nWhat she has said today:\n"
                      + "\n".join("- " + s for s in said)
                      + "\nLet this shape WHAT you offer and HOW you say it — "
                        "a quiet day takes a gentler offer than a talkative "
                        "one, and something she has already done today is not "
                        "an offer. Do not refer back to it; she knows what she "
                        "said.")
        else:
            window = ""
        S.recent_window = lambda uid, hours=6, _w=window: _w

        try:
            out = generate_proactive_script(
                UID, action="RECOMMENDATION", force_slot="afternoon") or {}
            print(f"\n— {label} —")
            for s in said:
                print(f"    she: {s}")
            print(f"  {out.get('script', '')[:230] or '(nothing)'}")
        except Exception as e:
            print(f"\n— {label} — failed: {str(e)[:90]}")
        finally:
            S.recent_window = real

    print("\nThe five should not be interchangeable. The sore one should be")
    print("gentler and should NOT mention her knee. The one where she has")
    print("been listening all morning should offer something else.")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        try:
            main()
        finally:
            if "--keep" not in sys.argv:
                print()
                teardown()
                print("torn down")

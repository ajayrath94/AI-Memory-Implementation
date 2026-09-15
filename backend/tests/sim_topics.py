"""
Topics: does it read her right, and does a decline show?

    railway run python3 -u backend/tests/sim_topics.py

Two halves, because the feature has two halves.

EXTRACTION — twenty conversations, each with a known answer. Can it tell what
she talked about, separate a good subject from a bad one in the same
conversation, and stay quiet when she said nothing?

TRENDS — six weeks of seeded sessions where one subject sours and the rest
hold steady. Does the decline surface, and do the steady ones stay quiet?

WHAT WOULD BE A FAILURE
Reporting a decline that is not there. Four false alerts fired this morning
on the old pillar trends — "sadness increasing, may need emotional support"
about a woman whose last twelve sessions were neutral or positive, and she
replied to the resulting message with "are sab acha hai". A caregiver told his
mother is declining when she is fine stops believing the next alert, and the
next one might be real.

So: a missed decline is bad, and a false one is worse.
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "topictest"

# (what she said, [(subject-fragment, pillar, sign)])
#   sign: +1 expects positive, -1 negative, 0 either, None = nothing expected
CASES = [
    # ── one subject, clear feeling ───────────────────────────────────────
    ("Arjun ka phone aaya aaj, bahut khush hoon",
     [("arjun", "FAMILY", +1)]),
    ("Ghutne mein bahut dard hai aaj, chala nahi jaata",
     [("ghutn", "HEALTH_WELLNESS", -1)]),
    ("Kishore Kumar ke gaane sune, mann acha ho gaya",
     [("kishore", "ENTERTAINMENT", +1)]),
    ("Mandir gayi thi subah, bahut shaanti mili",
     [("mandir", "FAITH", +1)]),
    ("Bijli ka bill bahut zyada aaya is mahine, pareshan hoon",
     [("bill", "FINANCE", -1)]),

    # ── two subjects, opposite feelings in one breath ────────────────────
    # the thing session valence cannot express
    ("Arjun ka phone aaya, acha laga. Par ghutna bahut dukh raha hai",
     [("arjun", "FAMILY", +1), ("ghutn", "HEALTH_WELLNESS", -1)]),
    # It reads this as loneliness rather than food, which is the better
    # reading — she is not complaining about the cooking.
    ("Khana acha bana tha par akela lag raha tha khate waqt",
     [("akela", None, -1)]),
    ("Poti se baat hui, khush hui. Bahu se thodi ankahi ho gayi",
     [("poti", "FAMILY", +1), ("bahu", "FAMILY", -1)]),

    # ── nothing to record ────────────────────────────────────────────────
    ("theek hai", None),
    ("haan", None),
    ("Acha", None),
    ("Namaste", None),

    # ── other languages, same shapes ─────────────────────────────────────
    ("என் மகன் ராஜு அழைத்தான், மகிழ்ச்சியாக இருந்தது",
     [("raju", "FAMILY", +1)]),
    ("আমার হাঁটুতে খুব ব্যথা হচ্ছে",
     [("knee", "HEALTH_WELLNESS", -1)]),
    ("ਅੱਜ ਗੁਰਦੁਆਰੇ ਗਈ ਸੀ, ਮਨ ਸ਼ਾਂਤ ਹੋ ਗਿਆ",
     [("gurdwara", "FAITH", +1)]),

    # ── the harder readings ──────────────────────────────────────────────
    ("Beta aaya tha lekin jaldi chala gaya",
     [("beta", "FAMILY", 0)]),
    ("Doctor ne kaha sab theek hai, par mujhe abhi bhi dar lagta hai",
     [("doctor", "HEALTH_WELLNESS", 0)]),
    ("Pension abhi tak nahi aayi, dekhte hain",
     [("pension", "FINANCE", -1)]),
    ("Sochti hoon ek baar Kashmir dekh aaun",
     [("kashmir", "ASPIRATIONS", +1)]),
    ("Dukaan ab beta sambhalta hai, mujhe aaram hai",
     [("dukaan", None, 0)]),
    ("Bas TV dekha aur so gayi",
     [("tv", "ENTERTAINMENT", 0)]),
]

# Six weeks. Arjun sours; the knee holds steady; music stays good. Only the
# first should be reported.
WEEKS = [
    (42, [("Arjun", "FAMILY", 0.8), ("ghutna", "HEALTH_WELLNESS", -0.4),
          ("Kishore Kumar", "ENTERTAINMENT", 0.7)]),
    (35, [("Arjun", "FAMILY", 0.7), ("ghutna", "HEALTH_WELLNESS", -0.5)]),
    (28, [("Arjun", "FAMILY", 0.6), ("Kishore Kumar", "ENTERTAINMENT", 0.8)]),
    (21, [("Arjun", "FAMILY", 0.2), ("ghutna", "HEALTH_WELLNESS", -0.4)]),
    (14, [("Arjun", "FAMILY", -0.1), ("Kishore Kumar", "ENTERTAINMENT", 0.7)]),
    (7,  [("Arjun", "FAMILY", -0.3), ("ghutna", "HEALTH_WELLNESS", -0.5)]),
    (2,  [("Arjun", "FAMILY", -0.4), ("Kishore Kumar", "ENTERTAINMENT", 0.8)]),
]


def teardown():
    db = get_client()
    for t in ("messages", "sessions", "user_memory", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def test_extraction():
    from memory.topics import extract_topics

    print("=" * 70)
    print("EXTRACTION")
    print("=" * 70)

    right = missed = invented = 0

    for said, want in CASES:
        got = extract_topics([{"role": "user", "content": said}])
        line = f"  {said[:40]:42}"

        if want is None:
            if got:
                invented += 1
                print(f"{line} INVENTED {[t['subject'] for t in got]}")
            else:
                right += 1
                print(f"{line} quiet")
            continue

        shown = []
        for frag, pillar, sign in want:
            hit = next((t for t in got
                        if frag.lower() in str(t["subject"]).lower()), None)
            if not hit:
                missed += 1
                shown.append(f"MISSED {frag}")
                continue

            ok = True
            if pillar and hit["pillar"] != pillar:
                ok = False
                shown.append(f"{frag}→{hit['pillar']} (wanted {pillar})")
            if sign and (hit["sentiment"] * sign) <= 0:
                ok = False
                shown.append(f"{frag} {hit['sentiment']:+.1f} wrong way")
            if ok:
                right += 1
                shown.append(f"{hit['subject'][:14]} {hit['pillar'][:12]} "
                             f"{hit['sentiment']:+.1f}")
        print(f"{line} {' | '.join(shown)}")

    print(f"\n  {right} right, {missed} missed, {invented} invented")
    print("  Invented is the one that matters — it fills her memory with")
    print("  things she never said.")
    return invented


def test_trends():
    from memory.topics import declining, by_pillar, feeling_about

    print()
    print("=" * 70)
    print("TRENDS — six weeks, Arjun souring, the rest steady")
    print("=" * 70)

    teardown()
    db = get_client()
    db.table("user_profile").insert({"user_id": UID, "name": "T"}).execute()

    for days_ago, topics in WEEKS:
        when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        db.table("sessions").insert({
            "user_id": UID, "model": "gemini-flash-latest",
            "created_at": when, "updated_at": when,
            "topics": [{"subject": s, "pillar": p, "sentiment": v}
                       for s, p, v in topics],
        }).execute()

    print("\n  what she feels about each, averaged:")
    for subj in ("Arjun", "ghutna", "Kishore Kumar"):
        print(f"    {subj:16} {feeling_about(UID, subj, days=60)}")

    print("\n  by pillar:")
    for p, d in sorted(by_pillar(UID, days=60).items()):
        print(f"    {p:18} mean={d['mean']:+.2f}  n={d['mentions']}  "
              f"lowest={d['lowest']}")

    print("\n  declining:")
    dec = declining(UID, days=60)
    for d in dec:
        print(f"    {d['subject']:16} {d['was']:+.2f} → {d['now']:+.2f}  "
              f"({d['mentions']} mentions)")
    if not dec:
        print("    nothing")

    names = [d["subject"] for d in dec]
    ok_found = "Arjun" in names
    ok_quiet = not any(n in ("Kishore Kumar", "ghutna") for n in names)
    print()
    print(f"  Arjun reported:        {ok_found}")
    print(f"  steady ones quiet:     {ok_quiet}")
    if not ok_quiet:
        print("  ^ a subject that never moved was reported as declining.")
        print("    That is the failure that makes a caregiver stop reading.")

    teardown()
    return ok_found and ok_quiet


def main():
    invented = test_extraction()
    trends_ok = test_trends()

    print()
    print("=" * 70)
    print(f"invented topics: {invented}   trends correct: {trends_ok}")
    print("=" * 70)


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        main()

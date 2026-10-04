"""
Fourteen offers from six interests. Does it repeat itself?

    railway run python3 -u backend/tests/sim_variety.py

"I only see Kishore Kumar all the time" was the complaint, and it was true for
four separate reasons, each found and fixed in turn:

    her interests came from a setup form saved seven times, so Kishore sat at
    10.92 and beat everything else by two hundred to one

    every artist she mentioned in conversation became a PERSON — proper_name
    was missing from one list — so conversation could never add a singer

    the adjacency list was generated and thrown away, and the artefact was
    fetched for the subject drawn rather than the one chosen

    and when that was fixed, Kishore expanded to Padosan six times out of
    six, because "dosa" is in her mentions and "padosan" contains it

This runs the offer path fourteen times over a seeded fortnight and counts
what comes out.

WHAT GOOD LOOKS LIKE

    no subject twice in a week      the cooldown is three days, and a
                                    fortnight of offers should not be one
                                    singer in different wrappers
    several categories              music, films, food, something she does —
                                    an afternoon should not always be music
    and the adjacent ones counted   an offer that is Lata BECAUSE of Kishore
                                    is the expansion working; one that is
                                    Kishore again is not

WHAT THIS DOES NOT TEST
Whether the message reads well. That is a judgement, and the messages are
printed so you can make it.
"""
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "variety%d" % int(time.time())
ROUNDS = 14
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


# Six interests across four categories, all at the same strength — so
# anything that dominates is doing so because of the logic, not the weights.
INTERESTS = [
    ("Kishore Kumar", "sangeet"),
    ("Lata Mangeshkar", "sangeet"),
    ("Sholay", "dekhna"),
    ("South Indian", "khana"),
    ("bagwani", "shauk"),
    ("Ramayan serial", "dekhna"),
]


def teardown():
    db = get_client()
    for t in ("suggestions", "subject_mentions", "memory_stm", "memory_cache",
              "user_behavioral_events", "interest_clusters", "user_patterns",
              "proactive_events", "day_events", "user_memory", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def setup():
    db = get_client()
    db.table("user_profile").upsert({
        "user_id": UID, "name": "Kamala", "language_pref": "hinglish",
        "location": "Jaipur", "home_location": "Jaipur",
    }).execute()
    db.table("user_memory").upsert({"user_id": UID,
                                    "session_count": 10}).execute()
    for kind, label, at in (("wake", None, "06:30"),
                            ("meal", "breakfast", "08:30"),
                            ("meal", "lunch", "13:00"),
                            ("meal", "dinner", "19:30"),
                            ("sleep", None, "22:00")):
        db.table("user_patterns").insert({
            "user_id": UID, "kind": kind, "label": label,
            "declared_at": at, "source": "declared"}).execute()

    for label, cat in INTERESTS:
        db.table("interest_clusters").insert({
            "user_id": UID, "label": label, "pillar": "ENTERTAINMENT",
            "kind": "interest", "status": "active", "strength": 2.0,
            "attributes": {"category": cat, "source": "conversation"},
        }).execute()


def main():
    import memory.suggestions as S
    from memory.artefacts import what_to_offer
    from memory.schedule_engine import generate_proactive_script

    setup()
    print(f"{len(INTERESTS)} interests, all at the same strength\n")

    real_moment = S._moment
    S._moment = lambda uid: {**real_moment(uid), "now_min": 15 * 60}

    drawn, offered, kinds, messages = [], [], Counter(), []
    try:
        for i in range(ROUNDS):
            p = S.pick_suggestion(UID)
            if not p:
                print(f"  {i+1:2}. (nothing offered)")
                continue
            o = what_to_offer(UID, p)
            drawn.append(p["label"])
            offered.append(o["subject"] or p["label"])
            kinds[o["kind"]] += 1

            out = generate_proactive_script(
                UID, action="RECOMMENDATION", force_slot="afternoon") or {}
            msg = (out.get("script") or "").replace("\n", " ")[:110]
            messages.append(msg)
            print(f"  {i+1:2}. {p['label'][:18]:20} -> {str(o['subject'])[:20]:22} "
                  f"{o['kind']}")
            if msg:
                print(f"      {msg}")

            # record it, so the cooldown and the scoring see it next round
            try:
                from memory.suggestions import record_suggestion
                record_suggestion(UID, p.get("cluster_id"),
                                  o["subject"] or p["label"],
                                  intent="recommendation")
            except Exception:
                pass
    finally:
        S._moment = real_moment

    print(f"\n— what was drawn —")
    for k, n in Counter(drawn).most_common():
        print(f"  {n:2}x  {k}")
    print(f"\n— what was offered —")
    for k, n in Counter(offered).most_common():
        print(f"  {n:2}x  {k}")
    print(f"\n  shapes: {dict(kinds)}")

    if not offered:
        check(False, "anything was offered at all")
        return

    top = Counter(offered).most_common(1)[0]
    check(top[1] <= max(2, ROUNDS // 4),
          "no single thing dominates",
          f"{top[0]} came up {top[1]} times in {len(offered)}")

    check(len(set(offered)) >= 5, "several different things",
          f"{len(set(offered))} distinct from {len(offered)} offers")

    adjacent_n = sum(n for k, n in kinds.items() if k in ("paired", "alone"))
    check(adjacent_n >= len(offered) // 3,
          "the expansion is doing work",
          f"{adjacent_n} of {len(offered)} offers were one step out")

    # and the categories, which is what stops every afternoon being music
    db = get_client()
    cats = Counter()
    for lbl in drawn:
        r = (db.table("interest_clusters").select("attributes")
             .eq("user_id", UID).eq("label", lbl).limit(1).execute()).data
        if r:
            c = (r[0].get("attributes") or {}).get("category")
            if c:
                cats[c] += 1
    print(f"  categories drawn: {dict(cats)}")
    check(len(cats) >= 3, "an afternoon is not always music",
          f"{len(cats)} categories across {len(drawn)} draws")


if __name__ == "__main__":
    crashed = None
    try:
        main()
    except Exception as e:
        crashed = e
    finally:
        print("\n" + "=" * 70)
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
        print("=" * 70)
        if "--keep" not in sys.argv:
            teardown()
            print("torn down")

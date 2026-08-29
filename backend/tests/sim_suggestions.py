"""
SUGGESTION LOOP HARNESS

Two paths in this feature have never executed: no_response and accepted. They
exist only as code. The loop is also the newest thing in the system, so it has
had the least incidental exercise.

What is worth pinning here is not "does it record a row" but the behaviour that
was designed deliberately:

  - accepted is weak (+0.2) on purpose. For an elderly person talking to a
    companion styled as their son, "haan chalao" is often politeness, and
    treating it as enthusiasm would teach the system the wrong thing.
  - declined_timing is 0.0. "Abhi nahi" says something about the moment, not
    the thing; counting it would make the companion stop offering what someone
    likes because they were tired once.
  - Only a preference decline counts against it, and no single one is a verdict.
    The threshold is EMERGENT — nothing in the code says "three strikes", it
    falls out of the weighted average — so it needs a test, because an
    emergent rule can drift without anyone editing a line that states it.

Users are prefixed sugtest_ and torn down in a finally block.

Run:  railway run python3 backend/tests/sim_suggestions.py
      railway run python3 backend/tests/sim_suggestions.py --purge
"""
import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

PREFIX = "sugtest_"


# ── helpers ───────────────────────────────────────────────────────────────────

def seed(uid, likes):
    """A user who has stated some preferences, via the real extraction path."""
    from classifier.pillar_classifier import classify_input
    from memory.profile_enricher import _extract_propositions, record_propositions

    db = get_client()
    db.table("user_profile").insert({
        "user_id": uid, "name": "SugSim", "language_pref": "hinglish",
    }).execute()
    try:
        from memory.testing import mark_user_as_test
        mark_user_as_test(uid)
    except Exception:
        pass
    for m in likes:
        record_propositions(_extract_propositions(m, uid) or [],
                            classify_input(m), uid, "")


def teardown():
    db = get_client()
    try:
        users = (db.table("user_profile").select("user_id")
                 .like("user_id", f"{PREFIX}%").execute()).data or []
        for u in users:
            uid = u["user_id"]
            for t in ("suggestions", "user_behavioral_events",
                      "interest_clusters", "user_memory", "user_context",
                      "bot_personas", "user_profile"):
                try:
                    db.table(t).delete().eq("user_id", uid).execute()
                except Exception:
                    pass
    except Exception as e:
        print(f"  teardown: {str(e)[:80]}")


def _state(uid, label):
    rows = (get_client().table("interest_clusters")
            .select("label,current_state,relationship")
            .eq("user_id", uid).execute()).data or []
    for r in rows:
        if label.lower() in (r.get("label") or "").lower():
            return r
    return None


def _backdate(sug_id, minutes):
    when = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    get_client().table("suggestions").update(
        {"created_at": when}).eq("id", sug_id).execute()


# ── 1: each reaction moves sentiment the right way ────────────────────────────

def run_weights():
    from memory.suggestions import (pick_suggestion, record_suggestion,
                                    handle_reply, REACTION_WEIGHT)

    print("=" * 78)
    print("PART 1 — REACTION WEIGHTS")
    print("=" * 78)
    failures = 0

    cases = [
        ("accepted",  "haan chalao, lagao",                    "up a little"),
        ("timing",    "nahi, abhi mann nahi hai",              "unchanged"),
        ("preference", "nahi, mujhe unke gaane pasand nahi",   "down"),
    ]

    for tag, reply, expect in cases:
        uid = PREFIX + tag
        seed(uid, ["mujhe Kishore Kumar bahut pasand hai"])
        before = (_state(uid, "Kishore") or {}).get("current_state")

        pick = pick_suggestion(uid)
        if not pick:
            print(f"FAIL {tag:12} nothing to suggest")
            failures += 1
            continue
        sid = record_suggestion(uid, pick["cluster_id"], pick["label"])
        reaction = handle_reply(uid, reply)
        after = (_state(uid, "Kishore") or {}).get("current_state")

        # direction, not magnitude — the weights may be tuned, the sign must not
        # flip without someone meaning it
        if reaction == "accepted":
            # +0.2 after +1.0 pulls a recency-weighted average DOWN, and that
            # is the design: acceptance is weak because "haan chalao" is often
            # politeness. The test is that it stays positive — it must not read
            # as a rejection.
            ok = after is not None and after > 0
        elif reaction == "declined_timing":
            ok = after is not None and before is not None and after <= before
        elif reaction == "declined_preference":
            ok = after is not None and before is not None and after < before
        else:
            ok = False

        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {tag:12} {str(reaction):20} "
              f"{before} -> {after}   ({expect})")
        print(f"     replied: {reply}")

    print(f"\n{len(cases) - failures}/{len(cases)} correct")
    return failures


# ── 2: the threshold nobody wrote down ────────────────────────────────────────

def run_threshold():
    from memory.suggestions import record_suggestion, handle_reply
    from memory.interests_view import computed_interests, computed_dislikes

    print()
    print("=" * 78)
    print("PART 2 — THE EMERGENT THRESHOLD")
    print("=" * 78)

    uid = PREFIX + "threshold"
    seed(uid, ["mujhe Kishore Kumar bahut pasand hai"])
    cid = (_state(uid, "Kishore") or {}).get("label")
    cluster = (get_client().table("interest_clusters").select("id,label")
               .eq("user_id", uid).execute()).data or []
    cid = cluster[0]["id"] if cluster else None

    print(f"  start:            interests={computed_interests(uid)}")
    for i in range(3):
        sid = record_suggestion(uid, cid, "Kishore Kumar")
        handle_reply(uid, "nahi, mujhe unke gaane pasand nahi")
        st = _state(uid, "Kishore")
        print(f"  after decline {i+1}:  state={st.get('current_state') if st else None}"
              f"  interests={computed_interests(uid)}")

    dislikes = computed_dislikes(uid)
    ok = "Kishore Kumar" in " ".join(dislikes) and not computed_interests(uid)
    print(f"\n{'ok  ' if ok else 'FAIL'} repeated preference declines move it to "
          f"dislikes: {dislikes}")
    return 0 if ok else 1


# ── 3: the two paths that have never run ──────────────────────────────────────

def run_untested():
    from memory.suggestions import record_suggestion, expire_stale, pending_suggestion

    print()
    print("=" * 78)
    print("PART 3 — PATHS THAT HAVE NEVER EXECUTED")
    print("=" * 78)
    failures = 0

    # no_response: offered, ignored, expired
    uid = PREFIX + "noresp"
    seed(uid, ["mujhe Lata Mangeshkar pasand hai"])
    cl = (get_client().table("interest_clusters").select("id")
          .eq("user_id", uid).execute()).data or []
    cid = cl[0]["id"] if cl else None

    sid = record_suggestion(uid, cid, "Lata Mangeshkar")
    before = (_state(uid, "Lata") or {}).get("current_state")
    _backdate(sid, 45)                      # older than PENDING_MINUTES
    n = expire_stale(uid)
    after = (_state(uid, "Lata") or {}).get("current_state")
    row = (get_client().table("suggestions").select("reaction")
           .eq("id", sid).execute()).data
    reaction = row[0]["reaction"] if row else None

    ok = n == 1 and reaction == "no_response"
    failures += not ok
    print(f"{'ok  ' if ok else 'FAIL'} unanswered -> {reaction} "
          f"(expired {n}), state {before} -> {after}")

    # a fresh suggestion must NOT be expired
    uid2 = PREFIX + "fresh"
    seed(uid2, ["mujhe Lata Mangeshkar pasand hai"])
    cl2 = (get_client().table("interest_clusters").select("id")
           .eq("user_id", uid2).execute()).data or []
    sid2 = record_suggestion(uid2, cl2[0]["id"] if cl2 else None, "Lata Mangeshkar")
    n2 = expire_stale(uid2)
    still_open = pending_suggestion(uid2) is not None
    ok2 = n2 == 0 and still_open
    failures += not ok2
    print(f"{'ok  ' if ok2 else 'FAIL'} fresh suggestion left open "
          f"(expired {n2}, pending={still_open})")

    print(f"\n{2 - failures}/2 correct")
    return failures


# ── 4: pick_suggestion's guards ───────────────────────────────────────────────

def run_picker():
    from memory.suggestions import pick_suggestion, record_suggestion, handle_reply

    print()
    print("=" * 78)
    print("PART 4 — WHAT IT WILL AND WILL NOT OFFER")
    print("=" * 78)
    failures = 0

    # nothing to offer when nothing is liked
    uid = PREFIX + "empty"
    get_client().table("user_profile").insert(
        {"user_id": uid, "name": "Empty"}).execute()
    ok = pick_suggestion(uid) is None
    failures += not ok
    print(f"{'ok  ' if ok else 'FAIL'} no interests -> offers nothing")

    # does not repeat itself within three days
    uid2 = PREFIX + "repeat"
    seed(uid2, ["mujhe Kishore Kumar bahut pasand hai"])
    p1 = pick_suggestion(uid2)
    record_suggestion(uid2, p1["cluster_id"], p1["label"])
    p2 = pick_suggestion(uid2)
    ok2 = p1 is not None and p2 is None
    failures += not ok2
    print(f"{'ok  ' if ok2 else 'FAIL'} offered once -> not offered again "
          f"({p1['label'] if p1 else None} then {p2})")

    # never offers something they have turned down
    uid3 = PREFIX + "declined"
    seed(uid3, ["mujhe Kishore Kumar bahut pasand hai"])
    p3 = pick_suggestion(uid3)
    sid = record_suggestion(uid3, p3["cluster_id"], p3["label"])
    handle_reply(uid3, "nahi, mujhe unke gaane bilkul pasand nahi")
    # Backdate rather than delete: the three-day recency guard needs clearing
    # to test the veto, but the veto reads this same row for the reaction, so
    # deleting it erases the very evidence under test.
    _backdate(sid, 60 * 24 * 5)
    p4 = pick_suggestion(uid3)
    ok3 = p4 is None
    failures += not ok3
    print(f"{'ok  ' if ok3 else 'FAIL'} declined on preference -> never offered "
          f"again ({p4})")

    print(f"\n{3 - failures}/3 correct")
    return failures


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if "--purge" in sys.argv:
        teardown()
        print("purged")
        return
    try:
        teardown()
        failures = run_weights()
        failures += run_threshold()
        failures += run_untested()
        failures += run_picker()
        print("\n" + "=" * 78)
        print("ALL GREEN" if failures == 0 else f"{failures} FAILURE(S)")
        print("=" * 78)
    finally:
        teardown()
        print("\ntorn down")


if __name__ == "__main__":
    main()

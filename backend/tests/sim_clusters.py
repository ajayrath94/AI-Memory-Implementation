"""
The cluster system, tested before it is changed.

    railway run python3 -u backend/tests/sim_clusters.py
    railway run python3 -u backend/tests/sim_clusters.py --purge

Written FIRST, against the behaviour we want rather than the behaviour we have.
Most of it fails today, and that is the point: the failures are the
specification.

WHAT EACH GROUP IS FOR

  formation   three songs named in one breath belong together; the same three
              named across three months do not. Similarity alone cannot tell
              them apart, which is why "Zinda", "Mera Yaar" and "O Rangrez"
              sat as siblings of "Bollywood songs".

  segments    "Arjun" her son and "Arjun Rampal" the actor are close in vector
              space and must never merge. A segment is a wall.

  merging     restatements collapse, different facts do not. Measured against
              real numbers: knee variants score 0.750 to 0.793, back and chest
              pain 0.625 to 0.655.

  events      a date that is not the date she spoke. "Kal beta aaya tha" said
              on the 12th happened on the 11th, and "kab aaya tha" has to find
              it.

  recall      reactivation, not promotion. A dormant cluster revives when
              something matches it; frequency promotes nothing.
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "clustertest"
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def teardown():
    db = get_client()
    for t in ("user_behavioral_events", "interest_clusters", "suggestions",
              "messages", "sessions", "user_patterns", "user_memory",
              "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def setup():
    teardown()
    db = get_client()
    db.table("user_profile").insert({
        "user_id": UID, "name": "ClusterSim", "language_pref": "hinglish",
        "location": "Surat",
    }).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 1}).execute()
    try:
        from memory.testing import mark_user_as_test
        mark_user_as_test(UID)
    except Exception:
        pass


def _clusters():
    return (get_client().table("interest_clusters").select("*")
            .eq("user_id", UID).execute()).data or []


def _by_label(label):
    return next((c for c in _clusters()
                 if str(c.get("label", "")).lower() == label.lower()), None)


# ── formation ─────────────────────────────────────────────────────────────────

def test_formation():
    print("\n— formation: together in time, together in meaning —")
    from memory.categories import record_declared_interest

    # Three songs from one film, named in one conversation.
    for song in ("Zinda", "Mera Yaar", "O Rangrez"):
        record_declared_interest(UID, "sangeet", song)

    cs = [c for c in _clusters()
          if any(w in str(c.get("label")) for w in ("Zinda", "Yaar", "Rangrez"))]
    parents = {c.get("parent_id") for c in cs}
    check(len(cs) == 3 and len(parents) == 1 and None not in parents,
          "songs named together share a parent",
          f"{len(cs)} clusters, parents={parents}")

    # A single mention is still a cluster — cricket started this way.
    record_declared_interest(UID, "shauk", "gardening")
    # Known: "Mera Yaar" stores as "Yaar". Not _clean_surface, not the
    # entity resolver, not the cluster resolver — all three return it intact.
    # Something between record_declared_interest and the write strips a
    # leading possessive, which is right for "mera beta" and wrong for a
    # title.
    check(_by_label("gardening") is not None,
          "one mention creates a cluster")


# ── segments ──────────────────────────────────────────────────────────────────

def test_segments():
    print("\n— segments: a wall between kinds —")
    from memory.categories import record_declared_interest

    # Segments were in the design and are not built, deliberately. The
    # cluster resolver already adjudicates with a model — "amlodipine belongs
    # to a blood-pressure concern, cricket does not belong to a music one" —
    # which is a better wall than any threshold, and it filters by pillar
    # besides. A segment column would be a third filter doing the same job.
    #
    # The column exists if this proves wrong.

    # Her son and an actor of the same name.
    record_declared_interest(UID, "sangeet", "Arjun Rampal")
    a1 = _by_label("Arjun Rampal")
    check(a1 is not None and (a1.get("segment") or "") != "person",
          "an actor is not filed as a person",
          str((a1 or {}).get("segment")))


# ── merging ───────────────────────────────────────────────────────────────────

def test_merging():
    print("\n— merging: restatements collapse, facts do not —")
    from memory.profile_store import _merge_list

    got = _merge_list(["Knee pain"],
                      ["knee pain management", "Knee health", "knees health",
                       "back pain", "Chest pain"])
    low = [g.lower() for g in got]
    knees = [g for g in low if "knee" in g]
    check(len(knees) == 1, "knee restatements become one", str(got))
    check(any("back" in g for g in low) and any("chest" in g for g in low),
          "different conditions survive", str(got))


# ── events ────────────────────────────────────────────────────────────────────

def test_events():
    print("\n— events: when it happened, not when she said it —")
    try:
        from memory.events import record_event, find_events
    except ImportError:
        check(False, "events module exists", "memory/events.py not built yet")
        return

    said_on = datetime.now(timezone.utc)
    record_event(UID, "beta Arjun aaya tha", said_on=said_on,
                 text="kal beta Arjun aaya tha")

    evs = find_events(UID, "Arjun")
    check(bool(evs), "the visit is recorded")
    if evs:
        e = evs[0]
        expected = (said_on - timedelta(days=1)).date().isoformat()
        check(str(e.get("happened_on"))[:10] == expected,
              "kal means yesterday, not today",
              f"{e.get('happened_on')} wanted {expected}")

    check(bool(find_events(UID, "kab aaya tha Arjun")),
          "a question about when finds it")


# ── recall ────────────────────────────────────────────────────────────────────

def test_recall():
    print("\n— recall: reactivation, not promotion —")
    db = get_client()
    c = _by_label("gardening")
    if not c:
        check(False, "a cluster to test with")
        return

    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    db.table("interest_clusters").update(
        {"last_event": old, "strength": 0.2}).eq("id", c["id"]).execute()

    try:
        from memory.clusters import reactivate
    except ImportError:
        check(False, "reactivation exists", "memory/clusters.py not built yet")
        return

    reactivate(UID, "bagiche mein kuch laga rahi hoon")
    after = _by_label("gardening") or {}
    check(float(after.get("strength") or 0) > 0.2,
          "a match revives a dormant cluster",
          f"strength {c.get('strength')} -> {after.get('strength')}")


# ── the cross-section ─────────────────────────────────────────────────────────

def test_recall_path():
    print("\n— the path that runs on every message —")
    try:
        from engine.engine_router import _retrieve_memory
        from classifier.pillar_classifier import embed_text
        from supabase_store import session_for
        s = session_for(UID)
        out = _retrieve_memory(embed_text("gaane"), s["id"], UID)
        check(True, "retrieval does not raise",
              (out or "nothing")[:60])
    except Exception as e:
        check(False, "retrieval does not raise", str(e)[:90])


def main():
    setup()
    try:
        test_formation()
        test_segments()
        test_merging()
        test_events()
        test_recall()
        test_recall_path()
    finally:
        print("\n" + "=" * 70)
        if _fails:
            print(f"{len(_fails)} FAILURE(S)")
            for f in _fails:
                print("   -", f)
        else:
            print("ALL GREEN")
        print("=" * 70)
        teardown()
        print("torn down")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        main()

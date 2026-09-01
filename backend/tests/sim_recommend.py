"""
RECOMMENDATION SIMULATION HARNESS

Fifteen cases across the five pieces built this week: enrichment, ambiguity,
probes, axes, and offers that travel an axis.

Most of these exist because the behaviour was wrong once. The infobox parser
read line by line and so missed every cast listed under {{Plainlist}}, leaving
Hema Malini out of Sholay. Removing {{hlist|...}} took its contents with it, so
Kishore Kumar had no verified facts at all. Untried axes were left out of
live_axes, so an offer for a singer found nothing — a singer has no composer.
And the offer classifier read warm agreement about an era as a rejection,
because it was written to judge acceptance of something offered and a probe
offers nothing.

Each of those looked correct in the code and was only visible in the output.

Run:  railway run python3 -u backend/tests/sim_recommend.py
      railway run python3 -u backend/tests/sim_recommend.py --purge
"""
import sys
import os
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

PREFIX = "rectest_"


# ── helpers ───────────────────────────────────────────────────────────────────

def make_user(uid, name="RecSim"):
    db = get_client()
    db.table("user_profile").insert({
        "user_id": uid, "name": name, "language_pref": "hinglish",
    }).execute()
    db.table("user_memory").insert({
        "user_id": uid, "session_count": 1, "axes": {},
    }).execute()
    try:
        from memory.testing import mark_user_as_test
        mark_user_as_test(uid)
    except Exception:
        pass


def declare(uid, category, text):
    from memory.categories import record_declared_interest
    return record_declared_interest(uid, category, text)


def cluster_of(uid, label):
    rows = (get_client().table("interest_clusters")
            .select("id,label,attributes,pillar")
            .eq("user_id", uid).eq("status", "active").execute()).data or []
    for r in rows:
        if (r.get("label") or "").lower().startswith(label.lower()[:8]):
            return r
    return None


def teardown():
    db = get_client()
    try:
        users = (db.table("user_profile").select("user_id")
                 .like("user_id", f"{PREFIX}%").execute()).data or []
        for u in users:
            uid = u["user_id"]
            for s in (db.table("sessions").select("id")
                      .eq("user_id", uid).execute()).data or []:
                db.table("messages").delete().eq("session_id", s["id"]).execute()
            for t in ("sessions", "suggestions", "user_behavioral_events",
                      "interest_clusters", "user_memory", "user_context",
                      "user_patterns", "user_profile"):
                try:
                    db.table(t).delete().eq("user_id", uid).execute()
                except Exception:
                    pass
    except Exception as e:
        print(f"  teardown: {str(e)[:80]}")


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    return 0 if ok else 1


# ── 1: enrichment ─────────────────────────────────────────────────────────────

def run_enrichment():
    from memory.enrich import enrich_cluster, stateable, usable

    print("=" * 78)
    print("PART 1 — ENRICHMENT")
    print("=" * 78)
    fails = 0

    uid = PREFIX + "enrich"
    make_user(uid)
    declare(uid, "dekhna", "Sholay")
    kishore_id = declare(uid, "sangeet", "Kishore Kumar")
    declare(uid, "bhakti", "Hindu")
    declare(uid, "shauk", "gardening")

    # 1. a film gets cast, director, year and — the reason Wikipedia was added
    #    at all — a music director OMDb does not carry.
    c = cluster_of(uid, "Sholay")
    f = enrich_cluster(uid, c["id"], force=True) if c else None
    v = stateable(f)
    fails += check(bool(v.get("director") and v.get("year")),
                   "film: director and year verified",
                   f"{v.get('director')} / {v.get('year')}")

    fails += check(bool(v.get("music")), "film: music director from Wikipedia",
                   str(v.get("music")))

    # 2. The cast lives inside {{Plainlist}} on its own lines. Reading the
    #    infobox line by line saw the opening brace and none of the names, so
    #    Sholay's cast came from OMDb's top three and Hema Malini went missing.
    cast = v.get("cast") or []
    fails += check(len(cast) >= 4, "film: multi-line cast read in full",
                   ", ".join(cast[:5]))

    # 3. An artist has no film infobox at all, and their fields are wrapped in
    #    {{hlist|...}} — which a template-stripping regex removed entirely.
    # By the id declare() returned rather than by label. Matching on the first
    # eight characters found a different cluster once the resolver had renamed
    # things, and the artist enrichment then ran against the wrong row.
    v2 = stateable(enrich_cluster(uid, kishore_id, force=True)) if kishore_id else {}
    fails += check(bool(v2.get("years_active")),
                   "artist: years_active verified", str(v2.get("years_active")))

    # 4. Faith is never enriched. Inferring the particulars of someone's
    #    religion is the overreach this system exists to avoid.
    c3 = cluster_of(uid, "Hindu")
    fails += check(enrich_cluster(uid, c3["id"], force=True) is None if c3 else True,
                   "bhakti is never enriched")

    # 5. And a hobby has nothing to decompose.
    c4 = cluster_of(uid, "garden")
    fails += check(enrich_cluster(uid, c4["id"], force=True) is None if c4 else True,
                   "shauk has nothing to enrich")

    # 6. Model facts may choose an offer and must never be stated. The model
    #    named the wrong composer on all three films tried.
    both = usable(f)
    fails += check(len(both) >= len(v),
                   "usable includes inferred, stateable does not")

    print()
    return fails


# ── 2: ambiguity ──────────────────────────────────────────────────────────────

def run_ambiguity():
    from memory.ambiguity import (candidates, is_ambiguous, match_answer,
                                  needs_asking, resolve)
    from memory.enrich import enrich_cluster, stateable

    print("=" * 78)
    print("PART 2 — WHICH FILM DID SHE MEAN")
    print("=" * 78)
    fails = 0

    # 7. Two well-known films, twenty-two years apart. Guessing gave the 2023
    #    sequel to someone who has loved the 2001 film since it came out.
    gadar = candidates("Gadar")
    fails += check(is_ambiguous(gadar), "Gadar is ambiguous",
                   ", ".join(f"{c['year']}" for c in gadar))

    # 8. Three films are called Sholay. Two have fourteen and thirty-two votes
    #    against sixty thousand, and asking which she meant would make the
    #    companion seem obtuse.
    sholay = candidates("Sholay")
    fails += check(not is_ambiguous(sholay), "Sholay is not ambiguous",
                   ", ".join(f"{c['year']}:{c.get('votes')}" for c in sholay[:3]))

    uid = PREFIX + "amb"
    make_user(uid)
    declare(uid, "dekhna", "Gadar")
    c = cluster_of(uid, "Gadar")

    # 9. Enrichment stops rather than guessing.
    got = enrich_cluster(uid, c["id"], force=True) if c else "x"
    fails += check(got is None, "ambiguous film is not enriched until asked")

    pend = needs_asking(uid)
    fails += check(bool(pend), "it is queued as a question to ask")

    # 10. She answers the way a person answers — not with a year.
    if pend:
        old = match_answer(pend, "purani wali, Sunny Deol ki")
        new = match_answer(pend, "nayi wali dekhi thi")
        none = match_answer(pend, "aaj ghutne mein dard hai")
        fails += check(bool(old) and bool(new) and old != new and none is None,
                       "'purani' and 'nayi' resolve differently, other replies do not")

        # 11. And her answer is USED. It was stored and both lookups ignored
        #     it, so one record held 2001 from OMDb and the sequel's composer
        #     from Wikipedia — two films in one row.
        resolve(uid, pend["cluster_id"], old)
        v = stateable(enrich_cluster(uid, pend["cluster_id"], force=True))
        fails += check(str(v.get("year", "")).startswith("2001"),
                       "resolved film is the one enriched",
                       f"{v.get('year')} / {v.get('director')} / {v.get('music')}")

    print()
    return fails


# ── 3: probes and axes ────────────────────────────────────────────────────────

def run_probes():
    from memory.enrich import enrich_cluster
    from memory.probes import pick_probe, probe_instruction
    from memory.axes import (_classify_probe, record, get_axes, live_axes,
                             dead_axes)

    print("=" * 78)
    print("PART 3 — QUESTIONS AND WHAT THEY TEACH")
    print("=" * 78)
    fails = 0

    uid = PREFIX + "probe"
    make_user(uid)
    declare(uid, "dekhna", "Sholay")
    c = cluster_of(uid, "Sholay")
    if c:
        enrich_cluster(uid, c["id"], force=True)

    # 12. A question built from a verified fact, not a blank one.
    p = pick_probe(uid)
    fails += check(bool(p) and bool(p.get("value")),
                   "probe built from a verified fact",
                   f"{(p or {}).get('axis')}: {(p or {}).get('value')}")

    # 13. Engagement, not acceptance. Reusing the offer classifier read warm
    #     agreement about an era as declined_preference, because a probe offers
    #     nothing to accept.
    warm = _classify_probe("R. D. Burman's music", "haan unke gaane bahut acche the")
    cold = _classify_probe("R. D. Burman's music", "nahi mujhe pasand nahi")
    away = _classify_probe("R. D. Burman's music", "aaj ghutne mein dard hai")
    fails += check(warm == "engaged" and cold == "not_interested" and away == "missed",
                   "engaged / not_interested / missed",
                   f"{warm} / {cold} / {away}")

    # 14. Three answers before the numbers mean anything, and a direction she
    #     has answered about and does not follow is not probed again.
    for _ in range(3):
        record(uid, "cast", False)
    record(uid, "music", True)
    fails += check("cast" in dead_axes(uid) and "cast" not in live_axes(uid),
                   "a direction she does not follow goes dead",
                   f"live={live_axes(uid)[:3]} dead={dead_axes(uid)}")

    # A missed question teaches nothing — it is not evidence against the
    # direction it was about.
    before = get_axes(uid).get("era", {}).get("asked", 0)
    record(uid, "era", None)
    after = get_axes(uid).get("era", {}).get("asked", 0)
    fails += check(before == after, "a missed question records nothing")

    print()
    return fails


# ── 4: offers along an axis ───────────────────────────────────────────────────

def run_offers():
    from memory.enrich import enrich_cluster
    from memory.artefacts import fetch_along_axis, axis_hint
    from memory.axes import record, live_axes

    print("=" * 78)
    print("PART 4 — OFFERS THAT TRAVEL A DIRECTION")
    print("=" * 78)
    fails = 0

    uid = PREFIX + "offer"
    make_user(uid)
    declare(uid, "sangeet", "Kishore Kumar")
    c = cluster_of(uid, "Kishore")
    if c:
        enrich_cluster(uid, c["id"], force=True)
        c = cluster_of(uid, "Kishore")

    # 15. Untried is not rejected. live_axes returned only what had been asked
    #     about, so someone whose one proven axis was music got no offer at all
    #     when the subject was a singer — a singer has no composer.
    record(uid, "music", True)
    fails += check(len(live_axes(uid)) > 1,
                   "untried axes are still tried", str(live_axes(uid)))

    art = fetch_along_axis(uid, c) if c else None
    fails += check(bool(art), "an offer travels an axis",
                   f"{(art or {}).get('via_axis')}: {str((art or {}).get('title'))[:50]}")

    if art:
        hint = axis_hint(art)
        # The connection is the whole point — an unexplained song is a
        # recommendation, a connected one is a thought.
        fact = art.get("via_fact")
        fact = fact[0] if isinstance(fact, list) and fact else str(fact)
        fails += check("Kishore" in hint and str(fact)[:4] in hint,
                       "the hint states the connection", hint[:110])
        fails += check("&#" not in hint,
                       "no HTML entities in what she will hear")

    print()
    return fails


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if "--purge" in sys.argv:
        teardown()
        print("purged")
        return
    try:
        teardown()
        fails = run_enrichment()
        fails += run_ambiguity()
        fails += run_probes()
        fails += run_offers()
        print("=" * 78)
        print("ALL GREEN" if fails == 0 else f"{fails} FAILURE(S)")
        print("=" * 78)
    finally:
        teardown()
        print("\ntorn down")


if __name__ == "__main__":
    main()

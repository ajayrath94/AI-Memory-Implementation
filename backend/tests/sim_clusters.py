"""
Does a person end up as ONE person?

    railway run python3 -u backend/tests/sim_clusters.py

The family screen showed Shubham six times and Nancy three times, each with a
relation or a doubt stuck in the name. This feeds the exact strings that
caused it into the two places family is written, and checks what is stored.

    clusters    interest_clusters, via _upsert_cluster (what the memory reads)
    profile     user_profile.family, via save_user_profile (the family lists)

Each case uses its own throwaway user, deleted afterwards. Ends ALL GREEN or
names what failed.
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

STAMP = int(time.time())
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def teardown(uid):
    db = get_client()
    for t in ("interest_clusters", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", uid).execute()
        except Exception:
            pass


def people(uid):
    """Active rows for this user, with their attributes."""
    rows = (get_client().table("interest_clusters")
            .select("id,label,kind,attributes,status")
            .eq("user_id", uid).eq("status", "active").execute()).data or []
    for r in rows:
        if not isinstance(r.get("attributes"), dict):
            r["attributes"] = {}
    return rows


def write(uid, label, **attrs):
    from memory.profile_enricher import _upsert_cluster
    attrs.setdefault("kind", "person")
    return _upsert_cluster(uid, label, "FAMILY", 1.0, attributes=attrs)


# ── the cases ────────────────────────────────────────────────────────────────

def case_shubham_three_ways():
    """The original bug: three phrasings of one son."""
    uid = f"clus_shubham{STAMP}"
    try:
        write(uid, "Shubham", relation="son")
        write(uid, "Shubham (son)")
        write(uid, "Shubham (son, lives in Bangalore)")
        rows = people(uid)
        labels = [r["label"] for r in rows]
        check(len(rows) == 1, "Shubham said three ways is one row", f"rows: {labels}")
        if rows:
            a = rows[0]["attributes"]
            check(rows[0]["label"] == "Shubham", "the name is just the name",
                  f"label: {rows[0]['label']!r}")
            check(a.get("relation") == "son", "relation kept as an attribute",
                  f"relation: {a.get('relation')!r}")
            check(a.get("location") == "Bangalore", "place kept as an attribute",
                  f"location: {a.get('location')!r}")
    finally:
        teardown(uid)


def case_son_or_grandson():
    """The model unsure of the generation: one person, flagged."""
    uid = f"clus_gen{STAMP}"
    try:
        write(uid, "Shubham", relation="son")
        write(uid, "Shubham", relation="grandson")
        rows = people(uid)
        check(len(rows) == 1, "son or grandson is still one Shubham",
              f"rows: {[(r['label'], r['attributes'].get('relation')) for r in rows]}")
        if rows:
            a = rows[0]["attributes"]
            check(bool(a.get("needs_review")), "and flagged for someone to settle",
                  f"needs_review: {a.get('needs_review')!r}, "
                  f"candidates: {a.get('relation_candidates')!r}")
    finally:
        teardown(uid)


def case_two_priyas():
    """Same name, plainly two people: kept apart."""
    uid = f"clus_priya{STAMP}"
    try:
        write(uid, "Priya", relation="bahu")
        write(uid, "Priya", relation="neighbour")
        rows = people(uid)
        check(len(rows) == 2, "a daughter-in-law and a neighbour stay two people",
              f"rows: {[(r['label'], r['attributes'].get('relation')) for r in rows]}")
    finally:
        teardown(uid)


def case_hedges_and_fragments():
    """Doubts and fragments never become names."""
    uid = f"clus_junk{STAMP}"
    try:
        write(uid, "Nancy (appears to be a caregiver/friend)")
        write(uid, "in Bangalore")
        write(uid, "possibly Ramesh")
        rows = people(uid)
        labels = [r["label"] for r in rows]
        bad = [l for l in labels
               if "(" in l or any(h in l.lower() for h in
                                  ("appears", "possibly", "maybe", "seems"))]
        check(not bad, "no brackets or doubt words in any name", f"bad: {bad}")
        check(not any(l.lower().startswith("in ") for l in labels),
              "'in Bangalore' is not a person", f"rows: {labels}")
        nancy = [r for r in rows if r["label"] == "Nancy"]
        if nancy:
            check(nancy[0]["attributes"].get("confidence") == "low",
                  "a guessed relation is marked low confidence",
                  f"attributes: {nancy[0]['attributes']}")
    finally:
        teardown(uid)


def case_profile_one_place():
    """The family lists: each person in one list only."""
    from memory.profile_store import save_user_profile, get_user_profile
    uid = f"clus_profile{STAMP}"
    try:
        get_client().table("user_profile").upsert(
            {"user_id": uid, "name": "Shobha"}).execute()
        save_user_profile(uid, {"family": {"children": ["Shubham"]}})
        save_user_profile(uid, {"family": {"other": ["Shubham", "Arjun"]}})
        save_user_profile(uid, {"family": {"grandchildren": ["Shubham in Bangalore"]}})
        save_user_profile(uid, {"family": {"children": ["Shubham (son)"]}})
        fam = (get_user_profile(uid) or {}).get("family") or {}
        print(f"       stored: {fam}")

        everywhere = []
        for key, val in fam.items():
            for item in (val if isinstance(val, list) else [val]):
                if "shubham" in str(item).lower():
                    everywhere.append(f"{key}:{item}")
        check(len(everywhere) == 1, "Shubham appears exactly once across the lists",
              f"found: {everywhere}")
        check(any("arjun" in str(x).lower() for x in fam.get("other") or []),
              "Arjun is kept", f"other: {fam.get('other')}")
    finally:
        teardown(uid)


def main():
    for case in (case_shubham_three_ways, case_son_or_grandson, case_two_priyas,
                 case_hedges_and_fragments, case_profile_one_place):
        print(f"\n── {case.__doc__.strip()}")
        try:
            case()
        except Exception as e:
            traceback.print_exc()
            check(False, f"{case.__name__} raised", str(e)[:120])


if __name__ == "__main__":
    try:
        main()
    finally:
        print("\n" + "=" * 70)
        if _fails:
            print(f"{len(_fails)} FAILURE(S)")
            for f in _fails:
                print("   -", f)
        else:
            print("ALL GREEN")
        print("=" * 70)

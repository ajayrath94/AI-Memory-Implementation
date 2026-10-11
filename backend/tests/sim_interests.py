"""
What does she say, and what does the memory keep?

    railway run python3 -u backend/tests/sim_interests.py

Sends real sentences through the real extraction (the model call and
record_propositions, the same path the chat uses) for one throwaway user,
then shows every cluster it made: what kind of thing, which category, how
strong. An interest only reaches the offer path if it is kind=interest WITH a
category, so that is what each check looks at.

Prints the whole table whatever happens, so you can read it as well as count
the checks. The user is deleted afterwards.
"""
import os
import sys
import time
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = f"interests{int(time.time())}"
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


# What she says, and what should come of it. kind/category None means "should
# NOT become an interest".
SAYS = [
    ("Mujhe Kishore Kumar ke gaane bahut pasand hain",   "Kishore Kumar", "interest", "sangeet"),
    ("Sholay meri favourite film hai",                   "Sholay",        "interest", "dekhna"),
    ("Gardening karna mujhe accha lagta hai, gulab lagaye hain", "gardening", "interest", "shauk"),
    # A daily practice: a devotional interest or a routine are both
    # reasonable. Shown in the table, not checked.
    ("Main roz subah Hanuman Chalisa padhti hoon",       "Hanuman Chalisa", "report", None),
    ("Mera beta Shubham Bangalore mein rehta hai",       "Shubham",       "person",   None),
    ("Ghutne mein dard rehta hai aajkal",                "knee",          "concern",  None),
    ("Cricket mujhe bilkul pasand nahi",                 "cricket",       None,       None),
    ("Aaj lemon rice banaya tha lunch mein",             "lemon rice",    None,       None),
    ("Aaj thoda udaas hoon",                             None,            None,       None),
]


def classified_stub():
    """The fields the extraction reads from the classifier."""
    return types.SimpleNamespace(
        core="ENTERTAINMENT", core_score=0.8, core_priority="MEDIUM",
        core_matrix={}, emotion="neutral", emotion_priority="LOW",
        emotion_matrix={}, functional_priority="LOW", language="hinglish")


def clusters():
    rows = (get_client().table("interest_clusters")
            .select("label,kind,pillar,strength,status,attributes")
            .eq("user_id", UID).execute()).data or []
    for r in rows:
        if not isinstance(r.get("attributes"), dict):
            r["attributes"] = {}
    return rows


def find(rows, word):
    w = word.lower()
    return [r for r in rows if w in str(r["label"]).lower()]


def main():
    from memory.profile_enricher import _extract_propositions, record_propositions
    db = get_client()
    db.table("user_profile").upsert({"user_id": UID, "name": "Shobha",
                                     "language_pref": "hinglish"}).execute()

    for text, *_ in SAYS:
        print(f"\nSHE   {text}")
        try:
            props = _extract_propositions(text, UID) or []
            for p in props:
                print(f"      fact: {p.get('subject')} | {p.get('relation')} | "
                      f"{p.get('object')}  (type {p.get('entity_type') or p.get('type')})")
            if not props:
                print("      fact: (none)")
            record_propositions(props, classified_stub(), UID, "")
        except Exception as e:
            print(f"      extraction failed: {e}")

    rows = clusters()
    print("\n" + "=" * 70)
    print(f"WHAT THE MEMORY HOLDS ({len(rows)} rows)")
    print("=" * 70)
    for r in sorted(rows, key=lambda r: (r.get("kind") or "", r["label"])):
        a = r["attributes"]
        print(f"  {r['label'][:34]:34} kind={str(r.get('kind')):9} "
              f"category={str(a.get('category') or '-'):8} "
              f"strength={r.get('strength') or 0:<5} status={r.get('status')}")

    from memory.offers import hers
    offerable = {v["label"] for v in hers(UID).values() if v.get("category")}
    print(f"\n  the offer path can see: {sorted(offerable) or '(nothing)'}")

    print()
    for text, word, kind, cat in SAYS:
        if not word or kind == "report":
            continue
        hit = find(rows, word)
        got = [(r["label"], r.get("kind"), r["attributes"].get("category")) for r in hit]
        if kind == "interest":
            ok = any(r.get("kind") == "interest" and
                     r["attributes"].get("category") == cat for r in hit)
            check(ok, f"{word!r} is an interest ({cat})", f"got: {got or 'nothing'}")
        elif kind in ("person", "concern"):
            ok = any(r.get("kind") == kind for r in hit)
            check(ok, f"{word!r} is a {kind}", f"got: {got or 'nothing'}")
        else:
            bad = [r for r in hit if r.get("kind") == "interest"
                   and r["attributes"].get("category") and r.get("status") == "active"]
            check(not bad, f"{word!r} is NOT offered as an interest",
                  f"got: {got or 'nothing'}")

    check(not any("udaas" in str(r["label"]).lower() for r in rows),
          "a passing mood is not stored as a thing")


if __name__ == "__main__":
    try:
        main()
    finally:
        for t in ("interest_clusters", "user_profile", "user_behavioral_events",
                  "subject_mentions"):
            try:
                get_client().table(t).delete().eq("user_id", UID).execute()
            except Exception:
                pass
        print("\n" + "=" * 70)
        print(f"{len(_fails)} FAILURE(S)" if _fails else "ALL GREEN")
        for f in _fails:
            print("   -", f)
        print("=" * 70)

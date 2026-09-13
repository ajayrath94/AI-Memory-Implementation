"""
A whole household, and whether the graph survives it.

    railway run python3 -u backend/tests/sim_people.py
    railway run python3 -u backend/tests/sim_people.py --keep

Everything so far has tested one relationship at a time. A real family is
twelve people who get mentioned by name, by relation, by nickname, and often
by neither — "unhone kaha tha" with the subject three sentences back.

WHAT THIS PUSHES ON

  many at once    twelve people. A profile with twelve names has to keep them
                  apart, and the resolver has twelve candidates to confuse.

  relation words  beta, bahu, pota, saheli, padosan, devar, jeth. The extractor
                  returns subject_ref and the cluster stored "person" for all
                  of them until today — the system knew Rajesh was a person and
                  had forgotten he was her son.

  the same name   two Priyas, one her daughter-in-law and one a neighbour.
                  Merging them would be the expensive kind of wrong.

  moving          Rajesh moves cities twice. Both moves have to close the
                  previous edge and keep it.

  no name at all  "unki tabiyat theek nahi" — someone specific, unnamed. The
                  right behaviour is to attach it to whoever was last
                  discussed, or to nothing.

  a death         her husband. The edge should close, not be deleted, and
                  nothing should later ask how he is.

WHAT TO READ
The list at the end is the product. Twelve people with the right relation
beside each is the pass; a daughter-in-law recorded as a daughter is a small
failure and a neighbour recorded as a son is a large one.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "peopletest"

# Ordinary sentences, the way someone talks about their family. Each carries
# at least one relationship, several carry two, and some refer back.
LINES = [
    # ── the immediate family ─────────────────────────────────────────────
    "Mera beta Rajesh Mumbai mein rehta hai, engineer hai",
    "Meri bahu Priya teacher hai, bahut acchi ladki hai",
    "Unka beta yaani mera pota Aarav do saal ka ho gaya",
    "Meri beti Sunita Pune mein hai, doctor hai wo",
    "Sunita ke pati Amit bank mein kaam karte hain",
    "Unki beti Ishita paanch saal ki hai, meri poti",

    # ── the wider family ─────────────────────────────────────────────────
    "Mere devar Suresh Jaipur mein rehte hain",
    "Meri jethani Kamla ji se roz baat hoti hai",
    "Mere bhai Mohan Delhi mein settled hain",

    # ── the people who are not family ────────────────────────────────────
    "Meri saheli Lata roz shaam ko milne aati hai",
    "Padosan Priya ji ne aaj sabzi bhej di thi",
    "Doodhwala Ramu subah aata hai",

    # ── the same name twice ──────────────────────────────────────────────
    "Priya ji aur meri bahu Priya dono ka naam ek hi hai",

    # ── someone moves, twice ─────────────────────────────────────────────
    "Rajesh ab Bangalore shift ho gaya hai naukri ke liye",
    "Phir Rajesh Hyderabad chala gaya, wahan acha package mila",

    # ── referred to without a name ───────────────────────────────────────
    "Unki tabiyat aajkal theek nahi rehti",

    # ── and a loss ───────────────────────────────────────────────────────
    "Mere pati Ramesh ji ab nahi rahe, do saal ho gaye",
]

# What should exist afterwards, and how each should be recorded.
# In her words, not in English. "Devar" is what she says and translating it
# to brother-in-law was the imposition — the same one that made him her
# husband when the extractor had seven English slots to choose from.
EXPECTED = {
    "Rajesh":   "beta",
    "Priya":    "bahu",
    "Aarav":    "pota",
    "Sunita":   "beti",
    "Ishita":   "poti",
    "Suresh":   "devar",
    "Kamla":    "jethani",
    "Mohan":    "bhai",
    "Lata":     "saheli",
    "Ramu":     "doodhwala",
    "Ramesh":   "pati",
    # Sunita's husband, not hers. Stored as "pati" with nothing saying
    # WHOSE — which is what an edge would carry and an attribute cannot.
    "Amit":     "pati",
}


def teardown():
    db = get_client()
    for t in ("entity_relations", "user_behavioral_events",
              "interest_clusters", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def main():
    from memory.profile_enricher import _extract_propositions, record_propositions
    from classifier.pillar_classifier import classify_input
    from memory.relations import current, history

    teardown()
    db = get_client()
    db.table("user_profile").insert(
        {"user_id": UID, "name": "Kamala", "language_pref": "hinglish"}).execute()

    print(f"{len(LINES)} things she said\n")
    for line in LINES:
        print(f"  {line}")
        try:
            props = _extract_propositions(line, UID) or []
            if props:
                record_propositions(props, classify_input(line), UID, "")
        except Exception as e:
            print(f"     failed: {e}")

    rows = (db.table("interest_clusters").select("id,label,kind,attributes")
            .eq("user_id", UID).execute()).data or []

    people = [r for r in rows if r.get("kind") == "person"]
    others = [r for r in rows if r.get("kind") != "person"]

    print("\n" + "=" * 68)
    print(f"PEOPLE — {len(people)} of an expected {len(EXPECTED)}")
    print("=" * 68)

    found = {}
    for r in sorted(people, key=lambda x: str(x.get("label"))):
        a = r.get("attributes") or {}
        rel = a.get("relation")
        found[str(r["label"]).split()[0]] = rel
        print(f"  {str(r['label'])[:22]:24} {str(rel or '—')}")

    print("\nagainst what was said")
    right = wrong = missing = 0
    for name, want in EXPECTED.items():
        got = found.get(name, "__absent__")
        if got == "__absent__":
            missing += 1
            print(f"  absent  {name:10} expected {want or 'a person'}")
        elif want is None:
            right += 1
        elif got == want:
            right += 1
        else:
            wrong += 1
            print(f"  wrong   {name:10} {got or '—'}, expected {want}")
    print(f"\n  {right} right, {wrong} wrong, {missing} absent")

    print("\n" + "=" * 68)
    print("EVERYTHING ELSE")
    print("=" * 68)
    for r in sorted(others, key=lambda x: str(x.get("kind"))):
        a = r.get("attributes") or {}
        print(f"  {str(r['label'])[:26]:28} {str(r.get('kind')):11} "
              f"{str(a.get('category') or '-')}")

    # Rajesh moved twice. Both moves should have closed the one before.
    raj = next((r for r in people if str(r["label"]).startswith("Rajesh")), None)
    if raj:
        print("\n" + "=" * 68)
        print("RAJESH MOVED TWICE")
        print("=" * 68)
        now = current(UID, raj["id"], "lives_in")
        print(f"  lives in now: {(now or {}).get('label', '—')}")
        for h in history(UID, raj["id"]):
            print(f"    {h['type']:10} {h['label']:14} "
                  f"{'current' if h['current'] else 'ended'}")

    # The two Priyas.
    priyas = [r for r in people if "Priya" in str(r.get("label"))]
    print("\n" + "=" * 68)
    print(f"THE TWO PRIYAS — {len(priyas)} cluster(s)")
    print("=" * 68)
    for r in priyas:
        a = r.get("attributes") or {}
        print(f"  {r['label']:24} {a.get('relation') or '—'}")
    if len(priyas) == 1:
        print("  one cluster: the neighbour and the daughter-in-law merged.")
        print("  Expensive — two people became one and neither is recoverable.")

    if "--keep" in sys.argv:
        print(f"\n(kept as {UID})")
    else:
        print()
        teardown()
        print("torn down")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        main()

"""
Who survives being mentioned?

    railway run python3 -u backend/tests/sim_persons.py

The household test said her neighbour Priya and her daughter-in-law Priya had
merged into one person. They had not. The neighbour was never recorded at all —
"Padosan Priya ji ne sabzi bhej di" is a transient action, the durable-fact
gate dropped the whole proposition, and the person inside it went with it.

Three fixes chased a merge that never happened.

THE REAL QUESTION
A person is durable even when what they did is not. Sending vegetables is
Tuesday; having a neighbour called Priya is a fact about her life. These cases
separate the two.

  durable about the person    "meri bahu Priya teacher hai"
  transient about the person  "padosan Priya ji ne sabzi bhej di"
  transient, no person        "aaj bahut thak gayi"
  a person, barely            "Ramu doodh de gaya"

Every line below names someone. The question for each is whether they exist
afterwards — and the answer should be yes for all of them, because she named
them.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "persontest"

# (sentence, name that should exist, how she referred to them)
CASES = [
    # ── durable statements about a person ────────────────────────────────
    ("Meri bahu Priya teacher hai",                    "Priya",   "bahu"),
    ("Mera beta Rajesh engineer hai",                  "Rajesh",  "beta"),
    ("Meri saheli Lata Jaipur mein rehti hai",         "Lata",    "saheli"),

    # ── a person inside a transient action ───────────────────────────────
    # this is the shape that was being dropped entirely
    ("Padosan Sunita ji ne sabzi bhej di",             "Sunita",  "padosan"),
    ("Doodhwala Ramu aaj doodh de gaya",               "Ramu",    "doodhwala"),
    ("Mere devar Suresh ne phone kiya tha",            "Suresh",  "devar"),
    ("Kamla ji ke saath mandir gayi thi",              "Kamla",   None),
    ("Aarav ne aaj school mein drawing banayi",        "Aarav",   None),

    # ── a person and a feeling together ──────────────────────────────────
    ("Beta Mohan ka phone aaya, bahut acha laga",      "Mohan",   "beta"),
    ("Bahu Priya se thodi bahas ho gayi aaj",          "Priya",   "bahu"),

    # ── no person at all: nothing should appear ──────────────────────────
    ("Aaj bahut thak gayi hoon",                       None,      None),
    ("Mausam acha hai aaj",                            None,      None),
]


def teardown():
    db = get_client()
    for t in ("entity_relations", "user_behavioral_events",
              "interest_clusters", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def main():
    from memory.profile_enricher import (_extract_propositions,
                                         record_propositions, _is_durable_fact)
    from classifier.pillar_classifier import classify_input

    teardown()
    db = get_client()
    db.table("user_profile").insert(
        {"user_id": UID, "name": "K", "language_pref": "hinglish"}).execute()

    print(f"{len(CASES)} sentences\n")

    for sentence, want, _rel in CASES:
        props = _extract_propositions(sentence, UID) or []
        # What the gate would do with each, before recording — this is where
        # the neighbour was being lost.
        shown = []
        for p in props:
            subj = (p.get("object") if str(p.get("subject_ref") or "").lower()
                    in ("self", "user") else p.get("subject")) or ""
            keep = _is_durable_fact(subj, (p.get("entity_type") or "").lower(),
                                    "", (p.get("kind") or "").lower())
            shown.append(f"{subj[:16]}{'' if keep else ' DROPPED'}")
        print(f"  {sentence[:44]:46} {' | '.join(shown) or 'nothing'}")
        if props:
            record_propositions(props, classify_input(sentence), UID, "")

    rows = (db.table("interest_clusters").select("label,kind,attributes")
            .eq("user_id", UID).execute()).data or []
    people = {str(r["label"]).split()[0]: (r.get("attributes") or {}).get("relation")
              for r in rows if r.get("kind") == "person"}

    print("\n" + "=" * 66)
    print(f"PEOPLE — {len(people)}")
    print("=" * 66)
    for n, rel in sorted(people.items()):
        print(f"  {n:16} {rel or '—'}")

    print("\nagainst who was named")
    missing = []
    for _s, want, rel in CASES:
        if not want:
            continue
        if want not in people:
            missing.append(want)
            print(f"  absent  {want:10} ({rel or 'no relation given'})")
        elif rel and people[want] != rel:
            print(f"  relation {want:10} {people[want] or '—'}, she said {rel}")
    if not missing:
        print("  everyone she named exists")

    # Nobody should appear from the two sentences with no person in them.
    ghosts = [n for n in people
              if n not in {w for _s, w, _r in CASES if w}]
    if ghosts:
        print(f"\n  invented: {', '.join(ghosts)}")

    print()
    teardown()
    print("torn down")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        main()

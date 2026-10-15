"""
The one "same thing?" check, against the real model and real embeddings.

    cd backend
    PYTHONPATH=. railway run python3 -u tests/sim_concepts.py

A throwaway user with a handful of concepts, then names she might say, each
with the answer it should get. Prints every verdict; deletes the user.
Never touches "default".
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("NANCY_TEST", "1")

from supabase_store import get_client

# What each seeded concept is called in English (the stored matching key),
# printed so a wrong translation is visible.

UID = "conceptsim%d" % int(time.time())

SEED = [  # label, kind, pillar, status, attributes
    ("Knee pain", "concern", "HEALTH_WELLNESS", "active", {}),
    ("Kishore Kumar", "interest", "ENTERTAINMENT", "active", {"category": "sangeet"}),
    ("Gardening", "interest", "ASPIRATIONS", "active", {"category": "shauk"}),
    ("Common cold", "concern", "HEALTH_WELLNESS", "archived", {"archived_why": "passing"}),
    ("Morning puja", "interest", "FAITH", "active", {"category": "bhakti"}),
    ("Evening walk", "interest", "HEALTH_WELLNESS", "active", {}),
    ("Bengaluru", "place", "GENERAL", "active", {}),
    ("Blood pressure", "concern", "HEALTH_WELLNESS", "active", {}),
    ("Priya", "person", "FAMILY", "active", {"relation": "bahu"}),
    ("Arjun", "person", "FAMILY", "active", {"relation": "beta"}),
    ("Zoo Outing", "event", "GENERAL", "active", {}),
    ("Cucumber", "interest", "GENERAL", "active", {"category": "khana"}),
    ("Mediterranean food", "interest", "GENERAL", "active", {"category": "khana"}),
]

# (what she says, kind, relation, the label it should be, or None)
SAME = [
    ("ghutne ka dard", "concern", "", "Knee pain"),
    ("ghutna", "concern", "", "Knee pain"),
    ("bagwani", "interest", "", "Gardening"),
    ("Kishore da", "interest", "", "Kishore Kumar"),
    ("zukaam", "concern", "", "Common cold"),
    ("sardi", "concern", "", "Common cold"),
    ("Bangalore", "place", "", "Bengaluru"),
    ("subah ki pooja", "interest", "", "Morning puja"),
    ("BP", "concern", "", "Blood pressure"),
    ("Lata Mangeshkar", "interest", "", None),
    ("Kumar Sanu", "interest", "", None),
    ("kamar dard", "concern", "", None),
    ("Amlodipine", "concern", "", None),
    ("Priya", "person", "padosan", None),
    ("Priya", "person", "bahu", "Priya"),
    ("Arjun beta", "person", "beta", "Arjun"),
    ("Zoo", "", "", None),
    ("ककड़ी", "interest", "", "Cucumber"),
    ("kakdi", "interest", "", "Cucumber"),
    ("முழங்கால் வலி", "concern", "", "Knee pain"),
    ("घुटने का दर्द", "concern", "", "Knee pain"),
    ("South Indian food", "interest", "", None),
]
ABOUT = [
    ("Kishore Kumar ke gaane", "Kishore Kumar"),
    ("sham ki walk", "Evening walk"),
    ("ghutne ki maalish", "Knee pain"),
    ("chai", None),
    ("Shubham", None),
]


def main():
    db = get_client()
    print(f"concept check as {UID}\n")
    fails = []
    try:
        for label, kind, pillar, status, attrs in SEED:
            db.table("interest_clusters").insert({
                "user_id": UID, "label": label, "kind": kind, "pillar": pillar,
                "status": status, "strength": 1.0, "event_count": 1,
                "attributes": attrs}).execute()
        from memory.concepts import same_as, about

        print("== SAME THING?")
        for name, kind, rel, want in SAME:
            got = same_as(UID, name, kind=kind, relation=rel)
            g = got["label"] if got else None
            ok = g == want
            fails += [] if ok else [f"same_as {name!r}{' (' + rel + ')' if rel else ''}: {g} != {want}"]
            st = f" [{got['status']}]" if got and got["status"] != "active" else ""
            print(f"  {'ok  ' if ok else 'MISS'} {name!r:24}{(' as ' + rel) if rel else '':12} -> {g!r}{st}"
                  + ("" if ok else f"   (expected {want!r})"))

        print("\n== ENGLISH KEYS FOR THE SEEDED CONCEPTS (matching only, never shown to her)")
        from memory.concepts import english
        for label, kind, _p, _st, attrs in SEED:
            if kind != "event":
                print(f"  {label:20} -> {english(label, kind, attrs.get('category', ''))!r}")

        print("\n== ABOUT WHICH? (links only, never merges)")
        for name, want in ABOUT:
            got = about(UID, name)
            g = got["label"] if got else None
            ok = g == want
            fails += [] if ok else [f"about {name!r}: {g} != {want}"]
            print(f"  {'ok  ' if ok else 'MISS'} {name!r:24} -> {g!r}" + ("" if ok else f"   (expected {want!r})"))
    finally:
        db.table("interest_clusters").delete().eq("user_id", UID).execute()
        left = db.table("interest_clusters").select("id", count="exact").eq("user_id", UID).execute().count
        print(f"\nDeleted {UID}." + (f" {left} rows left!" if left else " Nothing left behind."))

    print(f"\n{len(fails)} miss(es)")
    for f in fails:
        print("  ", f)


if __name__ == "__main__":
    main()

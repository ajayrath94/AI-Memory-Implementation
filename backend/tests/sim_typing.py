"""
What kind of thing is this? Fifty sentences.

    railway run python3 -u backend/tests/sim_typing.py
    railway run python3 -u backend/tests/sim_typing.py --runs 3

The kind column decides whether something can be offered. A concern typed as
an interest gets suggested on a quiet afternoon — "aaj ghutne ka dard try
kijiye" — and a genuine interest typed as a concern never surfaces at all.

Six sentences proved the column and the attribute agree. That is not the same
as proving the TYPE is right, and the six were all the shapes we had just
fixed.

WHAT IS BEING CHECKED
  kind      person | place | occupation | concern | interest | other
  category  only interests have one, and it decides the hour it may be
            offered — khana before a meal, sangeet in the walking hour

WHERE IT IS EXPECTED TO BE HARD
  a hobby and an ailment described the same way — "bagwani karti hoon" and
  "bhookh nahi lagti" are both things she does or experiences daily
  a place that is also an interest — Jaipur is where she lives; Kashmir is
  somewhere she wants to go
  a person who is also a profession — "doctor" alone
  food as a concern — "meetha kam khati hoon" is diet, not a love of sweets
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "typingtest"

# (sentence, {label: (kind, category)})
#
# category None means it must not be offerable.
CASES = [
    # ── people ────────────────────────────────────────────────────────────
    ("Mera beta Rajesh Mumbai mein rehta hai",
     {"Rajesh": ("person", None), "Mumbai": ("place", None)}),
    ("Meri bahu Priya teacher hai",
     {"Priya": ("person", None), "teacher": ("occupation", None)}),
    ("Pota Aarav do saal ka ho gaya",
     {"Aarav": ("person", None)}),
    ("Padosan Sharma ji roz milne aati hain",
     {"Sharma ji": ("person", None)}),

    # ── health, which must never be offered ───────────────────────────────
    ("Sugar ki problem hai mujhe",
     {"diabetes": ("concern", None)}),
    ("BP ki dawai roz leti hoon",
     {"blood pressure": ("concern", None)}),
    ("Kamar mein dard rehta hai",
     {"back pain": ("concern", None)}),
    ("Raat ko neend nahi aati",
     {"insomnia": ("concern", None)}),
    ("Bhookh nahi lagti aajkal",
     {"loss of appetite": ("concern", None)}),
    ("Chalne mein saans phoolti hai",
     {"breathlessness": ("concern", None)}),

    # ── interests, which must be ──────────────────────────────────────────
    ("Lata Mangeshkar ke gaane sunti hoon",
     {"Lata Mangeshkar": ("interest", "sangeet")}),
    ("Mughal-e-Azam meri favourite film hai",
     {"Mughal-e-Azam": ("interest", "dekhna")}),
    ("Rajma chawal bahut pasand hai",
     {"rajma chawal": ("interest", "khana")}),
    ("Bagwani karti hoon subah",
     {"gardening": ("interest", "shauk")}),
    ("Cricket dekhna acha lagta hai",
     {"cricket": ("interest", None)}),
    ("Bhagavad Gita padhti hoon roz",
     {"Bhagavad Gita": ("interest", "bhakti")}),
    ("Sudoku solve karti hoon time pass ke liye",
     {"sudoku": ("interest", "shauk")}),

    # ── the ones that sit between ─────────────────────────────────────────
    ("Meetha kam khati hoon, sugar ki wajah se",
     {"diabetes": ("concern", None)}),
    ("Doctor ne kaha roz chalna chahiye",
     {"walking": (None, None)}),
    ("Jaipur mein rehti hoon bachpan se",
     {"Jaipur": ("place", None)}),
    ("Kashmir jaana chahti hoon ek baar",
     {"Kashmir": (None, None)}),
    ("Yoga karti hoon ghutne ke liye",
     {"yoga": (None, None)}),
]


def teardown():
    db = get_client()
    for t in ("entity_relations", "user_behavioral_events",
              "interest_clusters", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def run_once(label: str):
    from memory.profile_enricher import _extract_propositions, record_propositions
    from classifier.pillar_classifier import classify_input

    teardown()
    db = get_client()
    db.table("user_profile").insert(
        {"user_id": UID, "name": "T", "language_pref": "hinglish"}).execute()

    for sentence, _ in CASES:
        try:
            props = _extract_propositions(sentence, UID) or []
            if props:
                record_propositions(props, classify_input(sentence), UID, "")
        except Exception as e:
            print(f"  [{sentence[:30]}] {e}")

    rows = (db.table("interest_clusters").select("label,kind,attributes")
            .eq("user_id", UID).execute()).data or []

    print(f"\n  {len(rows)} clusters from {len(CASES)} sentences\n")

    offerable = []
    for r in sorted(rows, key=lambda x: str(x.get("kind"))):
        a = r.get("attributes") or {}
        cat = a.get("category")
        k = str(r.get("kind"))
        if cat:
            offerable.append(r["label"])
        print(f"    {str(r['label'])[:26]:28} {k:11} {str(cat or '-')}")

    # The failure that matters: something she cannot be offered showing up as
    # offerable. A missed category means an interest stays quiet; a wrongly
    # assigned one means her diabetes is suggested as an afternoon activity.
    print(f"\n  offerable: {', '.join(offerable) or 'none'}")
    bad = [r for r in rows
           if (r.get("attributes") or {}).get("category")
           and str(r.get("kind")) in ("concern", "person", "place", "occupation")]
    if bad:
        print("\n  WRONG — these carry a category and must not:")
        for r in bad:
            print(f"    {r['label']} ({r.get('kind')})")
    else:
        print("  nothing that should be silent is offerable")

    teardown()
    return len(bad)


def main():
    runs = 1
    if "--runs" in sys.argv:
        runs = int(sys.argv[sys.argv.index("--runs") + 1])

    bad_total = []
    for i in range(runs):
        print(f"\n— run {i+1} of {runs} —")
        bad_total.append(run_once(f"run {i+1}"))

    print("\n" + "=" * 68)
    print(f"wrongly offerable, per run: {bad_total}")
    print("A concern or a person carrying a category is the failure that")
    print("reaches her. A missed one only means something stays quiet.")
    print("=" * 68)


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        main()

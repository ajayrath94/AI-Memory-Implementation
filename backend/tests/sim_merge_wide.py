"""
Does this belong to that? Across domains, not just films.

    railway run python3 -u backend/tests/sim_merge_wide.py
    railway run python3 -u backend/tests/sim_merge_wide.py --runs 3

Seventy cases. The existing harness leant on Hindi cinema, and three rules
tuned against Sholay and Bhaag Milkha Bhaag may only be rules about Sholay and
Bhaag Milkha Bhaag.

So: health, food, people, places, faith, sport, television, household, money,
and the cases that sit between two rules.

THE ASYMMETRY, RESTATED
A wrong merge keeps the LISTED label and loses the mentioned one for good. A
missed merge fragments and a later mention can still join. So the score to
drive down is WRONG, even at the cost of MISSED — and they are counted
separately for that reason.

WHERE THE HARD CASES ARE
Not in the obvious pairs. They are where the same surface shape has different
answers:

  "Delhi" + ["Arjun"]         merges. Where her son lives is part of knowing him.
  "Delhi" + ["Surat"]         does not. Two cities.

  "dawai" + ["knee pain"]     merges. Her medicine for it.
  "dawai" + ["blood pressure"] also merges, and if BOTH are listed the
                               adjudicator has to pick — and either is
                               defensible, which is why it is excluded here.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# (mention, [listed], expected or None, note)
CASES = [
    # ── health: a part joins its concern ──────────────────────────────────
    ("metformin", ["diabetes"], "diabetes", "the drug"),
    ("insulin injection", ["diabetes"], "diabetes", "the treatment"),
    ("sugar test", ["diabetes"], "diabetes", "monitoring it"),
    ("Dr Kulkarni", ["diabetes"], "diabetes", "the doctor for it"),
    ("diet chart", ["diabetes"], "diabetes", "managing it"),
    ("ghutne mein sujan", ["knee pain"], "knee pain", "swelling in the same knee"),
    ("physio exercises", ["knee pain"], "knee pain", "the treatment"),
    ("walking stick", ["knee pain"], "knee pain", "an aid for it"),
    ("inhaler", ["asthma"], "asthma", "the drug"),
    ("dust allergy", ["asthma"], "asthma", "a trigger"),

    # ── health: different conditions stay apart ───────────────────────────
    ("knee pain", ["diabetes"], None, "unrelated conditions"),
    ("asthma", ["blood pressure"], None, "unrelated conditions"),
    ("chest pain", ["knee pain"], None, "different body, and this one matters"),
    ("insomnia", ["knee pain"], None, "different complaint"),
    ("metformin", ["blood pressure"], None, "the wrong condition's drug"),
    ("cataract", ["diabetes"], None,
     "a real complication of diabetes, but she has not said so — NEW is safe"),

    # ── health: never into a vaguer word ──────────────────────────────────
    ("knee pain", ["pain"], None, "loses the knee"),
    ("chest pain", ["pain"], None, "loses the chest"),
    ("diabetes", ["health"], None, "a condition into a category"),
    ("metformin", ["dawai"], None, "a named drug into the word for medicine"),

    # ── food: dishes into cuisines, cuisines apart ────────────────────────
    ("idli", ["South Indian food"], "South Indian food", "a dish of it"),
    ("sambar", ["South Indian food"], "South Indian food", "a dish of it"),
    ("undhiyu", ["Gujarati food"], "Gujarati food", "a dish of it"),
    ("Gujarati food", ["South Indian food"], None, "two cuisines"),
    ("khichdi", ["dosa"], None, "two dishes, no containment"),
    ("dosa", ["khana"], None, "a dish into the word for food"),
    ("chai", ["coffee"], None, "two drinks"),
    ("jeera", ["khichdi"], None,
     "an ingredient of it, but a spice is not the dish — NEW is safer"),

    # ── people: a fact about someone joins them ───────────────────────────
    ("Delhi", ["Arjun"], "Arjun", "where her son lives"),
    ("doctor", ["Arjun"], "Arjun", "what he does"),
    ("Ananya", ["Arjun"], None, "his daughter is her own person"),
    ("Arjun ka phone", ["Arjun"], "Arjun", "him calling"),
    ("Meena", ["Arjun"], None, "two different people"),
    ("Delhi", ["Surat"], None, "two cities"),
    ("beta", ["Arjun"], "Arjun", "the relation word for him"),
    ("bahu", ["Arjun"], None,
     "his wife is a different person, however related"),

    # ── faith ─────────────────────────────────────────────────────────────
    ("Janmashtami vrat", ["Janmashtami"], "Janmashtami", "the fast of the festival"),
    ("Krishna", ["Janmashtami"], "Janmashtami", "whose festival it is"),
    ("Diwali", ["Janmashtami"], None, "two festivals"),
    ("morning puja", ["bhakti"], None, "a practice into a category"),
    ("Hanuman Chalisa", ["morning puja"], "morning puja",
     "what she recites at it"),

    # ── sport and television ──────────────────────────────────────────────
    ("India vs Pakistan", ["cricket"], "cricket", "a match"),
    ("Kohli", ["cricket"], "cricket", "a player"),
    ("IPL", ["cricket"], "cricket", "a tournament"),
    ("hockey", ["cricket"], None, "two sports"),
    ("Anupamaa", ["television"], None, "a named serial into a category"),
    ("Anupamaa ka episode", ["Anupamaa"], "Anupamaa", "an episode of it"),
    ("Taarak Mehta", ["Anupamaa"], None, "two serials"),

    # ── music, beyond the obvious ─────────────────────────────────────────
    ("Lata Mangeshkar", ["Mohammed Rafi"], None, "two singers"),
    ("Kishore Kumar ke gaane", ["Kishore Kumar"], "Kishore Kumar",
     "his songs are him"),
    ("R D Burman", ["Kishore Kumar"], None,
     "a composer and a singer are two people"),
    ("Sholay ka music", ["Sholay"], "Sholay", "the film's music"),
    ("purane gaane", ["Kishore Kumar"], None, "broader than one singer"),
    ("ghazal", ["Kishore Kumar"], None, "a genre, not him"),

    # ── household and money ───────────────────────────────────────────────
    ("bijli ka bill", ["household expenses"], "household expenses", "one of them"),
    ("maid", ["household expenses"], None,
     "a person, not an expense — though her wages are"),
    ("pension", ["household expenses"], None, "income, not expense"),
    ("gas cylinder", ["household expenses"], "household expenses", "one of them"),

    # ── not subjects at all ───────────────────────────────────────────────
    ("khushi", ["Arjun"], None, "a feeling is not part of a person"),
    ("thakan", ["knee pain"], None, "tiredness is not the knee"),
    ("ghar khali lagta hai", ["Arjun"], None, "how she felt when he left"),
    ("accha lagta hai", ["Kishore Kumar"], None, "not a subject"),
    ("theek hai", ["knee pain"], None, "not a subject"),

    # ── several candidates: it has to choose ──────────────────────────────
    ("metformin", ["knee pain", "diabetes", "asthma"], "diabetes",
     "the right one among three"),
    ("idli", ["Gujarati food", "South Indian food", "Chinese food"],
     "South Indian food", "the right cuisine"),
    ("Kohli", ["cricket", "Kishore Kumar", "Sholay"], "cricket",
     "the right domain"),
    ("Delhi", ["Arjun", "Surat", "knee pain"], "Arjun",
     "his city, not a city she lives in"),
    ("inhaler", ["knee pain", "blood pressure"], None,
     "none of these is asthma"),
]


def run_once(label: str):
    import os as _os
    from memory.cluster_resolver import _adjudicate, _adjudicate_v2
    _adjudicate = _adjudicate_v2 if _os.getenv('MERGE_V2') else _adjudicate
    right = wrong = missed = 0
    bad = []

    for mention, listed, want, note in CASES:
        cands = [{"label": l, "id": f"id{i}"} for i, l in enumerate(listed)]
        got = (_adjudicate(mention, cands) or {}).get("label")

        if got == want:
            right += 1
        elif want is None:
            wrong += 1
            bad.append(("WRONG ", mention, listed, got, note))
        else:
            missed += 1
            bad.append(("missed", mention, listed, got, note))

    for mark, mention, listed, got, note in bad:
        shown = f"{mention!r} + [{', '.join(listed)}]"
        print(f"  {mark} {shown[:46]:48} -> {str(got or 'NEW')[:20]:22} {note}")

    print(f"\n  {label}: {right}/{len(CASES)}   "
          f"wrong={wrong}  missed={missed}")
    return right, wrong, missed


def main():
    runs = 1
    if "--runs" in sys.argv:
        runs = int(sys.argv[sys.argv.index("--runs") + 1])

    totals = []
    for i in range(runs):
        print(f"\n— run {i+1} of {runs} —")
        totals.append(run_once(f"run {i+1}"))

    print("\n" + "=" * 72)
    r = sum(t[0] for t in totals) / len(totals)
    w = sum(t[1] for t in totals) / len(totals)
    m = sum(t[2] for t in totals) / len(totals)
    print(f"mean {r:.1f}/{len(CASES)}   wrong {w:.1f}   missed {m:.1f}")
    print("A wrong merge loses a label for good. A missed one fragments and")
    print("can still be joined later — so wrong is the number that matters.")
    print("=" * 72)


if __name__ == "__main__":
    main()

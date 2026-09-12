"""
The merge decision, tested in bulk.

    railway run python3 -u backend/tests/sim_merge.py
    railway run python3 -u backend/tests/sim_merge.py --runs 3

Every merge is irreversible: the absorbed cluster is deleted and its events
repointed. So a wrong yes silently corrupts the timeline, and a wrong no leaves
two rows that should be one — recoverable, but untidy.

Which makes this the decision most worth testing in volume rather than one case
at a time. A single run tells you little: the model is not deterministic, and
we have already tuned against lucky runs twice.

WHAT WENT WRONG BEFORE
  "Bhaag Milkha Bhaag" merged into "Sholay" — two films read as one concern,
  because the prompt taught that a specific match belongs to cricket and
  nothing distinguished an instance from a sibling.

  "knee pain" merged into "pain" — the target was vaguer than the subject, and
  since the merge keeps the listed label, a specific complaint became a
  general one.

THE RULE BEING TESTED
  merge     when the new thing is PART OF the listed one
  new       when they are two things of the same kind, or the listed one is
            vaguer, or they are unrelated
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# (mentioned, [already tracked], expected)  —  None means NEW
CASES = [
    # ── two of a kind. Never merge. ──────────────────────────────────────────
    ("Bhaag Milkha Bhaag", ["Sholay"],                      None),
    ("Kumar Sanu",         ["Kishore Kumar"],                None),
    ("Lata Mangeshkar",    ["Mohammed Rafi"],                None),
    ("dosa",               ["idli"],                         None),
    ("Ananya",             ["Arjun"],                        None),
    ("Surat",              ["Bengaluru"],                    None),

    # ── part of. Merge. ──────────────────────────────────────────────────────
    ("amlodipine",         ["blood pressure"],              "blood pressure"),
    ("O Rangrez",          ["Bhaag Milkha Bhaag"],          "Bhaag Milkha Bhaag"),
    ("Thyronorm",          ["thyroid"],                     "thyroid"),
    ("ankle swelling",     ["blood pressure"],              "blood pressure"),
    ("India vs Australia", ["cricket"],                     "cricket"),
    ("Gabbar",             ["Sholay"],                      "Sholay"),

    # ── the listed one is vaguer. Never merge INTO it. ───────────────────────
    ("knee pain",          ["pain"],                         None),
    ("Kishore Kumar",      ["music"],                        None),
    ("dosa",               ["food"],                         None),

    # ── restatements. Merge. ─────────────────────────────────────────────────
    ("ghutne ka dard",     ["knee pain"],                   "knee pain"),
    ("BP ki dawai",        ["blood pressure medication"],   "blood pressure medication"),
    ("Kishore da ke gaane",["Kishore Kumar"],               "Kishore Kumar"),

    # ── unrelated. Never merge. ──────────────────────────────────────────────
    ("cricket",            ["Kishore Kumar"],                None),
    ("knee pain",          ["blood pressure"],               None),
    ("Sholay",             ["knee pain"],                    None),

    # ── several candidates, one right answer. ────────────────────────────────
    ("amlodipine",         ["knee pain", "blood pressure", "Sholay"],
                                                            "blood pressure"),
    ("O Rangrez",          ["Sholay", "Bhaag Milkha Bhaag", "cricket"],
                                                            "Bhaag Milkha Bhaag"),
    ("Mohammed Rafi",      ["Kishore Kumar", "Kumar Sanu", "Lata Mangeshkar"],
                                                            None),
]


def run_once(verbose: bool = True):
    from memory.cluster_resolver import _adjudicate

    right, wrong = 0, 0
    misses = []

    for mentioned, tracked, expected in CASES:
        cands = [{"label": t, "id": f"id{i}", "score": 0.8}
                 for i, t in enumerate(tracked)]
        try:
            v = _adjudicate(mentioned, cands)
        except Exception as e:
            v = None
            if verbose:
                print(f"  ERR  {mentioned}: {e}")
        got = (v or {}).get("label")

        ok = (got == expected)
        right += ok
        wrong += (not ok)
        if not ok:
            misses.append((mentioned, tracked, expected, got))

        if verbose:
            mark = "ok  " if ok else "MISS"
            want = expected or "NEW"
            print(f"  {mark} {mentioned[:22]:24} in {str(tracked)[:34]:36} "
                  f"-> {str(got or 'NEW')[:20]:22} want {want}")

    return right, wrong, misses


def main():
    runs = 1
    if "--runs" in sys.argv:
        runs = int(sys.argv[sys.argv.index("--runs") + 1])

    all_misses = Counter()
    totals = []

    for r in range(runs):
        print(f"\n— run {r + 1} of {runs} —")
        right, wrong, misses = run_once()
        totals.append((right, wrong))
        for m in misses:
            all_misses[(m[0], str(m[1]))] += 1

    print("\n" + "=" * 72)
    for i, (right, wrong) in enumerate(totals, 1):
        print(f"run {i}: {right}/{right + wrong}")

    if runs > 1 and all_misses:
        print("\nwrong more than once — these are real, not variance:")
        for (mentioned, tracked), n in all_misses.most_common():
            if n > 1:
                print(f"  {n}/{runs}  {mentioned} in {tracked}")
        print("\nwrong once — could be either:")
        for (mentioned, tracked), n in all_misses.most_common():
            if n == 1:
                print(f"  {mentioned} in {tracked}")

    total_right = sum(r for r, _ in totals)
    total = sum(r + w for r, w in totals)
    print(f"\n{total_right}/{total} across {runs} run(s)")
    print("=" * 72)


if __name__ == "__main__":
    main()

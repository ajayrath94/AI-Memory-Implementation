"""
Every recommendation and what came back, for a person to read.

    railway run python3 backend/scripts/offer_log_report.py default
    railway run python3 backend/scripts/offer_log_report.py default --days 60
    railway run python3 backend/scripts/offer_log_report.py default --csv ~/Desktop/offers.csv

One line per offer: date, weekday, time, part of day, kind, what, why, her
answer and her words. Then what has worked, by kind and part of the day —
the same summary the recommendation step reads.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    args = [a for a in sys.argv[1:]]
    uid = next((a for a in args if not a.startswith("--") and not a.endswith(".csv")
                and a not in _values(args)), "default")
    days = int(_opt(args, "--days") or 30)
    out_csv = _opt(args, "--csv")

    from memory.offer_log import rows
    rs = rows(uid, days=days, limit=1000)
    if not rs:
        print(f"{uid}: no offers in the last {days} days")
        return

    print(f"{uid}: {len(rs)} offers in the last {days} days\n")
    print(f"{'date':10} {'day':3} {'time':5} {'part':13} {'kind':7} {'answer':19} what / why / her words")
    print("-" * 110)
    for r in rs:
        print(f"{r['date']:10} {r['weekday'][:3]:3} {r['time']:5} {r['slot']:13} "
              f"{r['kind'][:7]:7} {r['answer'][:19]:19} {r['what'][:45]}")
        extra = []
        if r["because"]:
            extra.append(f"because {r['because']}")
        if r["why"]:
            extra.append(f"why: {r['why'][:80]}")
        if r["festival"]:
            extra.append(r["festival"])
        if extra:
            print(f"{'':61}{' | '.join(extra)}")
        if r["her_words"]:
            print(f"{'':61}she said: \"{r['her_words'][:80]}\"")
        if r["link"]:
            print(f"{'':61}{r['link'][:80]}")

    # By kind and part of day.
    from collections import defaultdict
    t = defaultdict(lambda: defaultdict(int))
    for r in rs:
        t[(r["kind"] or "?", r["slot"] or "?")][r["answer"]] += 1
    print("\nby kind and part of day:")
    for (k, sl), c in sorted(t.items()):
        print(f"  {k:8} {sl:13} " + ", ".join(f"{a} {n}" for a, n in sorted(c.items())))

    if out_csv:
        path = os.path.expanduser(out_csv)
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rs[0].keys()))
            w.writeheader()
            w.writerows(rs)
        print(f"\nsaved {len(rs)} rows to {path}")


def _opt(args, name):
    if name in args:
        i = args.index(name)
        return args[i + 1] if i + 1 < len(args) else None
    return None


def _values(args):
    return {args[i + 1] for i, a in enumerate(args)
            if a in ("--days", "--csv") and i + 1 < len(args)}


if __name__ == "__main__":
    main()

"""
Fold what is already recorded under one name per thing.

    railway run python3 backend/tests/tools/canon_backfill.py          # dry run
    railway run python3 backend/tests/tools/canon_backfill.py --write

Recording canonicalises from now on, but six weeks of rows are already split:
"chicken" on one Sunday and "chicken curry and rice" on the next, "ghutna" and
"ghutne mein dard", "walk" and "sair". Every count groups by that column, so
the history finds patterns that are not there and misses ones that are.

HOW IT DECIDES
Oldest first, so the name she used first wins. Each subsequent subject is
asked against the ones already kept — the same question record() asks now, so
a backfilled row and a new one agree.

A merged row keeps its own date. Two Sundays of chicken stay two Sundays; they
simply end up under one name.

WHAT IT WILL NOT DO
Merge two things of the same kind. Chicken biryani stays chicken biryani; two
singers stay two singers. When unsure it leaves a subject alone, because
splitting one thing in two costs a pattern and merging two costs the truth.

Dry by default. Nothing is written without --write.
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from supabase_store import get_client

USER = "default"
WRITE = "--write" in sys.argv


def main():
    from memory.mentions import canonical

    db = get_client()
    rows = (db.table("subject_mentions")
            .select("id,subject,happened_on,cluster_id")
            .eq("user_id", USER)
            .order("happened_on").execute()).data or []

    print(f"{len(rows)} rows")
    distinct = sorted({str(r["subject"]).strip() for r in rows
                       if str(r.get("subject") or "").strip()})
    print(f"{len(distinct)} distinct subjects\n")

    # Oldest first, so the name she used first becomes the name.
    kept, mapping = [], {}
    for r in rows:
        s = str(r.get("subject") or "").strip()
        if not s or s in mapping:
            continue
        canon = canonical(USER, s, kept)
        mapping[s] = canon
        if canon not in kept:
            kept.append(canon)

    folded = {s: c for s, c in mapping.items() if s != c}
    print(f"— {len(folded)} would fold —")
    groups = defaultdict(list)
    for s, c in folded.items():
        groups[c].append(s)
    for c, members in sorted(groups.items()):
        print(f"  {c}")
        for m in members:
            print(f"      <- {m}")

    if not folded:
        print("  nothing to fold")
        return

    # What it does to the counts, which is the point.
    print("\n— what that changes —")
    before, after = defaultdict(set), defaultdict(set)
    for r in rows:
        s = str(r.get("subject") or "").strip()
        if not s:
            continue
        before[s].add(str(r["happened_on"])[:10])
        after[mapping.get(s, s)].add(str(r["happened_on"])[:10])
    grew = [(k, len(v)) for k, v in after.items()
            if len(v) > len(before.get(k, set()))]
    for k, n in sorted(grew, key=lambda x: -x[1]):
        print(f"  {k[:26]:28} {len(before.get(k, set()))} day(s) -> {n}")
    if not grew:
        print("  no subject gains a day")

    if not WRITE:
        print("\n(dry run — nothing written. --write to apply)")
        return

    n = 0
    for r in rows:
        s = str(r.get("subject") or "").strip()
        c = mapping.get(s, s)
        if not s or c == s:
            continue
        try:
            # The unique key is (user, subject, day), so a row folding onto a
            # day that already has that subject is a duplicate — drop it
            # rather than failing the whole pass.
            db.table("subject_mentions").update({"subject": c}) \
              .eq("id", r["id"]).execute()
            n += 1
        except Exception:
            try:
                db.table("subject_mentions").delete().eq("id", r["id"]).execute()
            except Exception as e:
                print(f"  could not fold {s!r}: {str(e)[:60]}")
    print(f"\n{n} rows folded")


if __name__ == "__main__":
    main()

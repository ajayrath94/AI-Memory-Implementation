#!/usr/bin/env python3
"""
BACKFILL — collapse accumulated profile lists through the existing dedup.

_merge_list has canonicalisation, containment and semantic dedup, but it only
runs when save_user_profile is handed an update touching that key. Lists that
grew before it existed, or that rarely get new entries, have never been passed
through it. Shobha's interests.religion held eight variants of "Hindu (Namaste
greeting)" for exactly this reason.

This re-merges each list against itself, in place. No new logic — it just runs
the dedup that is already there over data that never saw it.

USAGE
    # dry run, one user
    railway run python3 backfill_profile_lists.py --user default

    # dry run, every profile
    railway run python3 backfill_profile_lists.py --all

    # actually write
    railway run python3 backfill_profile_lists.py --user default --write

NOTES
  - Costs embedding calls (cached/batched by the classifier). --all over 80
    profiles is not free; run --user first.
  - Writes a JSON backup of every changed section to ./profile_backup_<ts>.json
    before touching anything.
  - Idempotent. Running it twice changes nothing the second time.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "backend")


# Sections whose list values are safe to re-merge. `medications` is excluded
# deliberately for the same reason _RESOLVE_KEYS excludes it: "BP tablet (old)"
# and "BP tablet (new)" record a switch, and collapsing them erases it.
SECTIONS = ("interests", "health", "personality", "life_context",
            "cultural_context")

SKIP_KEYS = {"medications"}


def collapse(profile: dict, user_id: str) -> tuple:
    """Return (changes, new_sections).

    changes: list of (section, key, before_count, after_count, before, after)
    new_sections: {section: {key: merged_list}} for keys that actually changed
    """
    from memory.profile_store import _merge_list

    owner = profile.get("name") or ""
    changes = []
    new_sections = {}

    for section in SECTIONS:
        block = profile.get(section)
        if not isinstance(block, dict):
            continue
        for key, val in block.items():
            if key in SKIP_KEYS or not isinstance(val, list) or len(val) < 2:
                continue
            try:
                merged = _merge_list([], val, owner=owner, user_id=user_id)
            except Exception as e:
                print(f"    !! {section}.{key}: merge failed, skipped ({e})")
                continue
            if merged != val:
                changes.append((section, key, len(val), len(merged),
                                list(val), merged))
                new_sections.setdefault(section, {})[key] = merged

    return changes, new_sections


def run_user(user_id: str, write: bool, backup: dict) -> int:
    from memory.profile_store import get_user_profile, save_user_profile

    profile = get_user_profile(user_id)
    if not profile:
        print(f"  (no profile)")
        return 0

    changes, new_sections = collapse(profile, user_id)
    if not changes:
        print(f"  nothing to collapse")
        return 0

    total_removed = 0
    for section, key, before, after, old, new in changes:
        total_removed += before - after
        print(f"  {section}.{key}: {before} -> {after}")
        dropped = [x for x in old if x not in new]
        for d in dropped[:12]:
            print(f"      - {d}")
        if len(dropped) > 12:
            print(f"      - ... and {len(dropped) - 12} more")

    # snapshot the ORIGINAL sections we are about to change
    backup[user_id] = {
        s: {k: profile.get(s, {}).get(k) for k in keys}
        for s, keys in new_sections.items()
    }

    if write:
        for section, keys in new_sections.items():
            try:
                # declared=False: this is not a user statement, it is a
                # re-merge of what was already stored. _deep_merge unions the
                # lists again, which is a no-op now they are collapsed.
                save_user_profile(user_id, {section: keys})
            except Exception as e:
                print(f"  !! write failed for {section}: {e}")
        print(f"  WROTE {len(new_sections)} section(s)")
    else:
        print(f"  (dry run — nothing written)")

    return total_removed


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--user", help="single user_id")
    g.add_argument("--all", action="store_true", help="every profile")
    ap.add_argument("--write", action="store_true",
                    help="actually write (default is dry run)")
    ap.add_argument("--limit", type=int, default=0,
                    help="with --all, stop after N profiles")
    args = ap.parse_args()

    from supabase_store import get_client

    if args.user:
        user_ids = [args.user]
    else:
        rows = (get_client().table("user_profile")
                .select("user_id").execute()).data or []
        user_ids = [r["user_id"] for r in rows]
        if args.limit:
            user_ids = user_ids[:args.limit]

    mode = "WRITE" if args.write else "DRY RUN"
    print(f"=== profile list backfill — {mode} — {len(user_ids)} profile(s)\n")

    backup = {}
    grand_total = 0
    started = time.time()

    for uid in user_ids:
        print(f"[{uid}]")
        try:
            grand_total += run_user(uid, args.write, backup)
        except Exception as e:
            print(f"  !! {uid} failed: {e}")
        print()

    if backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = f"profile_backup_{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(backup, f, indent=1, ensure_ascii=False)
        print(f"original values for every changed section: {path}")

    print(f"\n{grand_total} entries collapsed across {len(backup)} profile(s) "
          f"in {time.time() - started:.1f}s"
          + ("" if args.write else "  (DRY RUN — rerun with --write)"))


if __name__ == "__main__":
    main()

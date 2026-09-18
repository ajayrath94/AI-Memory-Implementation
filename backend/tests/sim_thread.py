"""
Does the thread compress honestly?

    railway run python3 -u backend/tests/sim_thread.py
    railway run python3 -u backend/tests/sim_thread.py --keep

Three months of seeded days, with the cases one month could not cover.

WHAT IS BEING CHECKED

  recall protects     a day she came back to stays, however old. Neglect is
                      what moves things down — that was the whole point of
                      "if user is not recalling it then we need to age it",
                      and nothing had exercised it.

  tags carry up       a month holds the union of its days'. Without this, ltm
                      is short but not searchable, and "when did her knee
                      start" has no answer.

  a fold merges       a month folds, then another stale day from that same
                      month arrives late. It has to join the existing line,
                      not overwrite it — this is where compression could
                      quietly lose things.

  a month finishes    September was folded from one stale day while two of
                      its days were still live, and produced "the month was
                      quiet and unremarkable" about a month that had not
                      ended.

WHAT WOULD BE A FAILURE
Losing something. A summary that is thin is recoverable — the next fold can
be better. A day that was deleted without being folded into anything is gone,
and that is the failure this harness exists to catch.
"""
import os
import sys
from datetime import date, datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "threadsim"
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def teardown():
    db = get_client()
    for t in ("memory_cache", "memory_stm", "memory_ltm",
              "interest_clusters", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def setup():
    teardown()
    db = get_client()
    db.table("user_profile").insert(
        {"user_id": UID, "name": "T", "language_pref": "hinglish"}).execute()

    # Two clusters, so tags have something real to point at.
    ids = {}
    for label in ("Arjun", "knee pain"):
        r = db.table("interest_clusters").insert({
            "user_id": UID, "label": label, "kind": "person" if label == "Arjun"
            else "concern", "pillar": "GENERAL", "status": "active",
            "strength": 2.0,
        }).execute()
        ids[label] = r.data[0]["id"]
    return ids


def seed(ids, today: date):
    """Three months. Some days tagged, one recalled recently, one late arrival."""
    db = get_client()
    arjun, knee = ids["Arjun"], ids["knee pain"]

    # (days ago, text, tags, untagged, recalled_days_ago or None)
    DAYS = [
        # July — long past, should fold
        (75, "Arjun called about the festival.", [arjun], [], None),
        (72, "Knee stiff in the mornings.", [knee], [], None),
        (70, "Made lemon rice.", [], ["lemon rice"], None),

        # August — should fold, and carries both tags
        (55, "Arjun visited for two days.", [arjun], [], None),
        (53, "House felt empty after he left.", [arjun], [], None),
        (48, "Knee worse. Saw the doctor.", [knee], [], None),
        (45, "Made lemon rice again.", [], ["lemon rice"], None),

        # An old day she keeps coming back to. Must NOT fold.
        (60, "The day her granddaughter was born.", [], ["Ishita"], 1),

        # Recent — stays in stm
        (5, "Made khichdi.", [], ["khichdi"], None),
        (2, "Arjun called. Knee better.", [arjun, knee], [], None),
    ]

    for ago, text, tags, loose, recalled in DAYS:
        row = {
            "user_id": UID,
            "happened_on": (today - timedelta(days=ago)).isoformat(),
            "text": text, "tags": tags, "untagged": loose,
        }
        if recalled is not None:
            row["last_recalled"] = (
                datetime.now(timezone.utc) - timedelta(days=recalled)).isoformat()
        db.table("memory_stm").insert(row).execute()

    # And some cache, to check the sweep
    for ago in (10, 3, 1):
        db.table("memory_cache").insert({
            "user_id": UID,
            "happened_on": (today - timedelta(days=ago)).isoformat(),
            "role": "user", "text": f"something said {ago} days ago",
        }).execute()

    return len(DAYS)


def main():
    from memory.thread import sweep

    ids = setup()
    today = date.today()
    n = seed(ids, today)
    db = get_client()

    print(f"{n} days seeded across three months\n")
    result = sweep(UID)
    print(f"\nsweep: {result}\n")

    stm = (db.table("memory_stm").select("*")
           .eq("user_id", UID).order("happened_on").execute()).data or []
    ltm = (db.table("memory_ltm").select("*")
           .eq("user_id", UID).order("period").execute()).data or []

    print("still in stm")
    for r in stm:
        print(f"  {r['happened_on']}  {r['text'][:52]}")
    print("\nfolded into ltm")
    for r in ltm:
        print(f"  {r['period']}  {r['text'][:74]}")
    print()

    # ── recall protects ──────────────────────────────────────────────────
    kept = [r["text"] for r in stm]
    check(any("granddaughter" in t for t in kept),
          "a day she came back to stays, however old",
          "60 days old, recalled yesterday")

    # ── nothing vanished ─────────────────────────────────────────────────
    # Every folded day has to be represented somewhere. The summaries are
    # short by design, so this checks the MONTHS exist rather than the words.
    months_folded = {str(r["period"])[:7] for r in ltm}
    july = (today - timedelta(days=72)).strftime("%Y-%m")
    august = (today - timedelta(days=50)).strftime("%Y-%m")
    check(july in months_folded, f"{july} folded")
    check(august in months_folded, f"{august} folded")

    # ── tags carry up ────────────────────────────────────────────────────
    aug_row = next((r for r in ltm if str(r["period"])[:7] == august), None)
    if aug_row:
        tags = aug_row.get("tags") or []
        check(ids["Arjun"] in tags and ids["knee pain"] in tags,
              "a month carries its days' tags",
              f"{len(tags)} tags")
        check("lemon rice" in (aug_row.get("untagged") or []),
              "and what had no cluster yet")
    else:
        check(False, "a month carries its days' tags", "no august row")

    # ── this month is not folded ─────────────────────────────────────────
    check(today.strftime("%Y-%m") not in months_folded,
          "the current month is left alone",
          "it has not finished")

    # ── cache swept by age ───────────────────────────────────────────────
    cache = (db.table("memory_cache").select("happened_on")
             .eq("user_id", UID).execute()).data or []
    old = [c for c in cache
           if date.fromisoformat(str(c["happened_on"])[:10]) < today - timedelta(days=7)]
    check(not old, "her verbatim words go after a week",
          f"{len(cache)} left, {len(old)} too old")

    # ── a late day joins its month rather than replacing it ──────────────
    print("\n— a day from August arrives late —")
    before = aug_row.get("text") if aug_row else ""
    db.table("memory_stm").insert({
        "user_id": UID,
        "happened_on": (today - timedelta(days=50)).isoformat(),
        "text": "Went to a wedding in the family.",
        "tags": [], "untagged": ["wedding"],
    }).execute()
    sweep(UID)

    after_row = (db.table("memory_ltm").select("text,untagged")
                 .eq("user_id", UID).eq("period", f"{august}-01")
                 .limit(1).execute()).data or []
    after = after_row[0].get("text") if after_row else ""
    print(f"  before: {before[:70]}")
    print(f"  after : {after[:70]}")
    check(after and after != before, "the month was rewritten, not left alone")
    check("wedding" in after.lower()
          or "wedding" in (after_row[0].get("untagged") or []),
          "and the late day is in it")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        try:
            main()
        finally:
            print("\n" + "=" * 68)
            if _fails:
                print(f"{len(_fails)} FAILURE(S)")
                for f in _fails:
                    print("   -", f)
            else:
                print("ALL GREEN")
            print("=" * 68)
            if "--keep" not in sys.argv:
                teardown()
                print("torn down")

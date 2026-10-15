"""
RECOUNT — set each group's event_count from what actually happened.

event_count drifted three ways: every fact was filed twice (as the message
came in and again when the chat closed), recall and reaction events were
added without counting, and trips and outings were created with no count
at all — Delhi Trip, Zoo Outing and Sightseeing all read 0.

The count is now one meaning: the number of DAYS she mentioned it.
    groups      distinct days with a mention event (what she said, or her
                naming it again); reactions to an offer are not mentions
    events      the days it was said (said_on, said_on_all); at least 1

Active groups only. Preview by default.

    cd backend
    PYTHONPATH=. railway run python3 scripts/recount_events.py default
    PYTHONPATH=. railway run python3 scripts/recount_events.py default --go
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _event_days(row) -> int:
    a = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
    days = set(a.get("said_on_all") or [])
    if a.get("said_on"):
        days.add(a["said_on"])
    return max(1, len(days))


def _mention_days(db, cluster_id: str) -> int:
    rows, start = [], 0
    while True:
        got = (db.table("user_behavioral_events")
               .select("created_at,sub_pillar")
               .eq("cluster_id", cluster_id)
               .range(start, start + 999).execute()).data or []
        rows += got
        if len(got) < 1000:
            break
        start += 1000
    days = {str(r.get("created_at") or "")[:10] for r in rows
            if (r.get("sub_pillar") or "") != "reaction" and r.get("created_at")}
    return len(days)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    uid = args[0] if args else "default"
    go = "--go" in sys.argv
    from supabase_store import get_client
    db = get_client()
    cl = (db.table("interest_clusters")
          .select("id,label,kind,event_count,attributes")
          .eq("user_id", uid).eq("status", "active").limit(500).execute()).data or []

    changes = []
    for c in cl:
        new = _event_days(c) if c.get("kind") == "event" else _mention_days(db, c["id"])
        old = c.get("event_count") or 0
        if c.get("kind") != "event" and new == 0:
            # Made from the setup form or a clean-up with no mention events
            # yet: one, so it is not mistaken for nothing.
            new = 1
        if new != old:
            changes.append((c, old, new))

    print(f"\n{uid}: {len(cl)} active groups, {len(changes)} counts change"
          f"{'' if go else ' (preview)'}\n")
    for c, old, new in sorted(changes, key=lambda x: x[0]["label"].lower()):
        print(f"  {c['label'][:30]:30} {c.get('kind') or '':9} {old:>4} -> {new}")
    if not go:
        print("\nNothing changed. Add --go to write.")
        return
    for c, old, new in changes:
        db.table("interest_clusters").update({"event_count": new}).eq("id", c["id"]).execute()
    print(f"\nWrote {len(changes)}.")


if __name__ == "__main__":
    main()

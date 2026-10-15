"""
Give every concept its label in plain English, once.

The same-thing check (memory/concepts.py) searches by her word AND its
English. New concepts store theirs when made; this does the ones that exist,
so the first chat after deploy does not pay for it.

    cd backend
    PYTHONPATH=. railway run python3 scripts/concept_english.py default          # preview
    PYTHONPATH=. railway run python3 scripts/concept_english.py default --go
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    uid = args[0] if args else "default"
    go = "--go" in sys.argv
    from supabase_store import get_client
    from memory.concepts import english, _attrs
    db = get_client()
    rows = (db.table("interest_clusters").select("id,label,kind,status,attributes")
            .eq("user_id", uid).neq("kind", "event").limit(1000).execute()).data or []
    todo = [r for r in rows if not _attrs(r).get("english")]
    print(f"{uid}: {len(rows)} concepts, {len(todo)} without English{'' if go else ' (preview)'}\n")
    for r in todo:
        e = english(r["label"], r.get("kind") or "", _attrs(r).get("category") or "")
        print(f"  {r['label'][:30]:30} {r.get('kind') or '':9} {r.get('status'):8} -> {e!r}")
        if go and e:   # a name written back is stored too: it marks the concept done
            a = _attrs(r)
            a["english"] = e
            db.table("interest_clusters").update({"attributes": a}).eq("id", r["id"]).execute()
    print("\nWritten." if go else "\nNothing written. Add --go.")


if __name__ == "__main__":
    main()

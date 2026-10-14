"""
Duplicate clusters: find them, and fold them together.

    railway run python3 -u backend/scripts/cluster_dupes.py USER_ID            # report only
    railway run python3 -u backend/scripts/cluster_dupes.py USER_ID --merge    # fold them

Rows written before labels were cleaned carry the relation, the place and the
model's doubts in the name: "Shubham", "Shubham (son)", "Shubham (son, lives
in Bangalore)". New writes go through clean_label() and land on one row; the
old ones are still there, and the family screen still shows all of them.

Grouped by the cleaned label. Within a group the strongest row is kept; the
others give it their strength, mentions and attributes, and are marked
status='merged' with merged_into pointing at it. Nothing is deleted, so a bad
merge can be undone by setting status back to 'active'.

Rows whose cleaned label is empty ("in Bangalore", "Nancy (appears to be...)"
with nothing left) are listed and, with --merge, marked status='dropped'.

Relations that disagree across a group are kept as candidates on the kept row
and flagged needs_review, the same way new writes are handled. Two rows whose
relations cannot be one person (a bahu and a padosan) are left apart.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: cluster_dupes.py USER_ID [--merge]")
    uid = sys.argv[1]
    do = "--merge" in sys.argv

    from supabase_store import get_client
    from memory.profile_enricher import (clean_label, _relation_candidates,
                                         _same_person_confusable)
    db = get_client()

    rows = (db.table("interest_clusters")
            .select("id,label,kind,pillar,strength,event_count,attributes,status")
            .eq("user_id", uid).eq("status", "active")
            .limit(2000).execute()).data or []
    print(f"{uid}: {len(rows)} active clusters\n")

    def attrs_of(r):
        a = r.get("attributes")
        if isinstance(a, str):
            try:
                a = json.loads(a)
            except Exception:
                a = {}
        return a if isinstance(a, dict) else {}

    groups, junk = {}, []
    for r in rows:
        a = attrs_of(r)
        a.setdefault("kind", r.get("kind") or "")
        name, a2 = clean_label(r["label"], a)
        r["_attrs"] = a2
        if not name:
            junk.append(r)
            continue
        groups.setdefault((name.lower(), r.get("kind") or ""), []).append(r)

    dupes = {k: v for k, v in groups.items() if len(v) > 1}

    print(f"== {len(dupes)} name(s) held by more than one row ==")
    for (name, kind), rs in sorted(dupes.items()):
        rs.sort(key=lambda r: -(r.get("strength") or 0))
        print(f"\n{name!r} ({kind or '?'}), {len(rs)} rows:")
        for r in rs:
            rel = r["_attrs"].get("relation") or "-"
            print(f"   {r['id'][:8]}  strength {r.get('strength') or 0:<6} "
                  f"relation {rel:<14} label {r['label']!r}")

    print(f"\n== {len(junk)} row(s) that are not a name ==")
    for r in junk:
        print(f"   {r['id'][:8]}  {r['label']!r}")

    if not do:
        print("\nReport only. Re-run with --merge to fold these together.")
        return

    merged = dropped = kept_apart = 0
    for (name, kind), rs in dupes.items():
        rs.sort(key=lambda r: -(r.get("strength") or 0))
        keep = rs[0]
        ka = dict(keep["_attrs"])
        strength = keep.get("strength") or 0
        count = keep.get("event_count") or 0
        folded = []
        for r in rs[1:]:
            ra = r["_attrs"]
            o = str(ka.get("relation") or "").lower()
            n = str(ra.get("relation") or "").lower()
            if o and n and o != n and not _same_person_confusable(o, n):
                print(f"   kept apart: {r['label']!r} ({n}) is not {keep['label']!r} ({o})")
                kept_apart += 1
                continue
            for k, v in ra.items():
                if v and k not in ("relation", "relation_candidates") and not ka.get(k):
                    ka[k] = v
            if n and n != o:
                ka = _relation_candidates(ka, n)
            strength += r.get("strength") or 0
            count += r.get("event_count") or 0
            folded.append(r)

        if not folded:
            continue
        clean, _ = clean_label(keep["label"], {})
        db.table("interest_clusters").update({
            "label": clean, "attributes": ka,
            "strength": round(strength, 4), "event_count": count,
        }).eq("id", keep["id"]).execute()
        for r in folded:
            ra = dict(r["_attrs"])
            ra["merged_into"] = keep["id"]
            ra["label_before_merge"] = r["label"]
            db.table("interest_clusters").update(
                {"status": "merged", "attributes": ra}).eq("id", r["id"]).execute()
            # Point what referred to it at the one that remains. Best effort:
            # a table without the column is simply skipped.
            for table in ("suggestions", "user_behavioral_events"):
                try:
                    db.table(table).update({"cluster_id": keep["id"]}) \
                        .eq("cluster_id", r["id"]).execute()
                except Exception:
                    pass
            merged += 1
        print(f"   {clean!r}: kept {keep['id'][:8]}, folded {len(folded)}")

    for r in junk:
        ra = dict(r["_attrs"])
        ra["label_before_drop"] = r["label"]
        db.table("interest_clusters").update(
            {"status": "dropped", "attributes": ra}).eq("id", r["id"]).execute()
        dropped += 1

    print(f"\nmerged {merged}, dropped {dropped}, kept apart {kept_apart}")


if __name__ == "__main__":
    main()

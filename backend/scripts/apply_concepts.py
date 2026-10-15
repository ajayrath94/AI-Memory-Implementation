"""
APPLY CONCEPTS — the reviewed plan for Shobha's memory, and nothing else.

The model's report changed between runs (puja and Pooja Preparation merged
once and not the next time), so nothing here asks a model. This is the plan
as reviewed on 15 October, written out:

    merge     Pooja Preparation + puja  -> "Morning puja"  (her routine, worship)
              Evening Walk + Walk       -> "Evening walk"  (her routine, health & exercise)
              Carrom Game -> Carrom ;  Delhi trip -> Delhi Trip (an episode)
    archive   Dhyanesh (autocorrect), mausam, movie, Home, Medicine,
              rest + Aram (a state, not a thing)
    fix       Fruit, paneer -> food interests under GENERAL
    split     Health -> Knee pain (active concern), Common cold (archived,
              the resolved episode); what is left (fine, took medicine,
              sleepy) stays in Health, which is archived
    mentions  attach caroom, tinde, fal, pooja ki taiyar, sham ki walk,
              Bazar, Sardi to their concepts; pool -> phool; mark junk

Preview by default. --go applies, after writing a backup of every row it
will touch. --undo FILE puts them all back.

    cd backend
    PYTHONPATH=. railway run python3 scripts/apply_concepts.py default
    PYTHONPATH=. railway run python3 scripts/apply_concepts.py default --go
    PYTHONPATH=. railway run python3 scripts/apply_concepts.py default --undo backups/concepts_....json

Archived and merged rows are never deleted: status becomes "archived" or
"merged", with merged_into, so nothing is lost and undo is exact.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MERGES = [
    # (labels to fold together, final label, kind, pillar, attributes to set)
    (["Pooja Preparation", "puja"], "Morning puja", "interest", "FAITH",
     {"category": "bhakti", "routine": "Morning puja"}),
    (["Evening Walk", "Walk"], "Evening walk", "interest", "HEALTH_WELLNESS",
     {"routine": "Evening walk"}),
    (["Carrom", "Carrom Game"], "Carrom", "interest", "ASPIRATIONS",
     {"category": "shauk"}),
    (["Delhi Trip", "Delhi trip"], "Delhi Trip", "event", "GENERAL",
     {"episode": True}),
]
ARCHIVE = {
    "Dhyanesh": "autocorrect of 'dhyan hai', not a person",
    "mausam": "weather small-talk", "movie": "generic word", "Home": "generic word",
    "Medicine": "her medicines live in her profile",
    "rest": "a state, not a thing", "Aram": "a state, not a thing",
}
FIXES = {
    "Fruit":  {"kind": "interest", "pillar": "GENERAL", "category": "khana"},
    "paneer": {"kind": "interest", "pillar": "GENERAL", "category": "khana"},
}
SPLIT_FROM = "Health"
SPLITS = [
    # (new label, kind, status, pillar, event values that move, attributes)
    ("Knee pain", "concern", "active", "HEALTH_WELLNESS",
     ["knee pain"], {"kind": "concern", "long_term": True}),
    ("Common cold", "concern", "archived", "HEALTH_WELLNESS",
     ["sardi", "sardi theek hai"], {"kind": "concern", "episode": "sardi, 5-14 Oct 2026, resolved"}),
]
ATTACH = {  # subject as she said it -> final concept label
    "caroom": "Carrom", "tinde": "Tinda", "fal": "Fruit",
    "pooja ki taiyar": "Morning puja", "sham ki walk": "Evening walk",
    "Bazar": "Market Shopping", "Sardi": "Common cold",
}
RENAME_SUBJECT = {"pool": "phool"}
JUNK = ["Aj", "sab", "everything", "Sunday", "Lunch", "List", "aj ka din",
        "aj aram se ghumne Gaye hai", "aj sham ko kya banaya jaye",
        "Garmi", "khana", "phone"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def main():
    args = sys.argv[1:]
    uid = next((a for a in args if not a.startswith("--") and not a.endswith(".json")), "default")
    if "--undo" in args:
        return undo(args[args.index("--undo") + 1])
    go = "--go" in args

    from supabase_store import get_client
    db = get_client()

    try:
        db.table("subject_mentions").select("junk").limit(1).execute()
    except Exception:
        raise SystemExit("subject_mentions.junk column missing — run "
                         "concepts_tables.sql in Supabase first.")

    cl = (db.table("interest_clusters").select("*").eq("user_id", uid)
          .limit(3000).execute()).data or []
    by_label = {}
    for c in cl:
        if c.get("status") == "active":
            by_label.setdefault(c["label"], c)
    def find(label):
        return by_label.get(label) or next(
            (c for c in cl if c["label"] == label), None)

    touched_clusters, touched_events, touched_mentions, created = {}, {}, {}, []
    def keep_cluster(c):
        touched_clusters.setdefault(c["id"], dict(c))

    def events_of(cid):
        return (db.table("user_behavioral_events").select("id,cluster_id,value")
                .eq("cluster_id", cid).limit(2000).execute()).data or []

    plan_lines = []

    # ── merges ────────────────────────────────────────────────────────────────
    final_ids = {}
    for labels, final, kind, pillar, attrs in MERGES:
        rows = [r for r in (find(l) for l in labels) if r]
        if not rows:
            plan_lines.append(f"merge {labels}: none found, skipped")
            continue
        rows.sort(key=lambda r: -(r.get("event_count") or 0))
        keep, rest = rows[0], rows[1:]
        final_ids[final] = keep["id"]
        plan_lines.append(f"merge {[r['label'] for r in rows]} -> {final!r} "
                          f"({kind}/{pillar}), keeping {keep['label']!r}")
        if go:
            keep_cluster(keep)
            for r in rest:
                keep_cluster(r)
                for e in events_of(r["id"]):
                    touched_events.setdefault(e["id"], e["cluster_id"])
                db.table("user_behavioral_events").update({"cluster_id": keep["id"]}) \
                    .eq("cluster_id", r["id"]).execute()
                ms = (db.table("subject_mentions").select("id,subject,cluster_id,junk")
                      .eq("cluster_id", r["id"]).execute()).data or []
                for m in ms:
                    touched_mentions.setdefault(m["id"], m)
                db.table("subject_mentions").update({"cluster_id": keep["id"]}) \
                    .eq("cluster_id", r["id"]).execute()
                a = dict(r.get("attributes") or {})
                a["merged_into"] = keep["id"]
                db.table("interest_clusters").update(
                    {"status": "merged", "attributes": a}).eq("id", r["id"]).execute()
            n = (db.table("user_behavioral_events").select("id", count="exact")
                 .eq("cluster_id", keep["id"]).execute()).count
            a = dict(keep.get("attributes") or {})
            a.update(attrs)
            a["kind"] = kind
            upd = {"kind": kind, "pillar": pillar, "attributes": a,
                   "event_count": n or keep.get("event_count")}
            if final != keep["label"] and not any(
                    c["label"] == final and c["id"] != keep["id"] for c in cl):
                upd["label"] = final
            db.table("interest_clusters").update(upd).eq("id", keep["id"]).execute()

    # ── archive ───────────────────────────────────────────────────────────────
    for label, why in ARCHIVE.items():
        r = find(label)
        if not r or r.get("status") != "active":
            plan_lines.append(f"archive {label!r}: not active, skipped")
            continue
        plan_lines.append(f"archive {label!r} — {why}")
        if go:
            keep_cluster(r)
            a = dict(r.get("attributes") or {})
            a["archived_why"] = why
            db.table("interest_clusters").update(
                {"status": "archived", "attributes": a}).eq("id", r["id"]).execute()

    # ── fixes ─────────────────────────────────────────────────────────────────
    for label, fx in FIXES.items():
        r = find(label)
        if not r:
            continue
        plan_lines.append(f"fix {label!r}: {r.get('kind')}/{r.get('pillar')} -> "
                          f"{fx['kind']}/{fx['pillar']} [{fx['category']}]")
        if go:
            keep_cluster(r)
            a = dict(r.get("attributes") or {})
            a.update({"kind": fx["kind"], "category": fx["category"]})
            db.table("interest_clusters").update(
                {"kind": fx["kind"], "pillar": fx["pillar"], "attributes": a}) \
                .eq("id", r["id"]).execute()

    # ── split Health ──────────────────────────────────────────────────────────
    src = find(SPLIT_FROM)
    if src:
        evs = events_of(src["id"])
        for label, kind, status, pillar, values, attrs in SPLITS:
            moving = [e for e in evs if str(e.get("value") or "").strip().lower()
                      in [v.lower() for v in values]]
            plan_lines.append(f"split {len(moving)} event(s) from {SPLIT_FROM!r} -> "
                              f"{label!r} ({kind}, {status})")
            if go and moving:
                existing = next((c for c in cl if c["label"] == label), None)
                if existing:
                    nid = existing["id"]
                    keep_cluster(existing)
                else:
                    row = {"user_id": uid, "label": label, "pillar": pillar,
                           "kind": kind, "status": status, "strength": 1.0,
                           "attributes": attrs}
                    try:
                        from classifier.pillar_classifier import embed_text
                        v = embed_text(label)
                        if v:
                            row["centroid"] = v
                    except Exception:
                        pass
                    nid = db.table("interest_clusters").insert(row).execute().data[0]["id"]
                    created.append(nid)
                final_ids[label] = nid
                for e in moving:
                    touched_events.setdefault(e["id"], e["cluster_id"])
                    db.table("user_behavioral_events").update({"cluster_id": nid}) \
                        .eq("id", e["id"]).execute()
                db.table("interest_clusters").update({"event_count": len(moving)}) \
                    .eq("id", nid).execute()
        plan_lines.append(f"archive {SPLIT_FROM!r} — what is left is states "
                          f"(fine, took medicine, sleepy)")
        if go:
            keep_cluster(src)
            a = dict(src.get("attributes") or {})
            a["archived_why"] = "split into Knee pain and Common cold; the rest are states"
            db.table("interest_clusters").update({"status": "archived", "attributes": a}) \
                .eq("id", src["id"]).execute()

    # ── mentions ──────────────────────────────────────────────────────────────
    ms = (db.table("subject_mentions").select("id,subject,cluster_id,junk")
          .eq("user_id", uid).limit(5000).execute()).data or []
    labels_now = {**{c["label"]: c["id"] for c in cl if c.get("status") == "active"},
                  **final_ids}
    for subj, target in ATTACH.items():
        rows = [m for m in ms if str(m["subject"]).strip().lower() == subj.lower()]
        tid = labels_now.get(target)
        plan_lines.append(f"attach {len(rows)} mention(s) of {subj!r} -> {target!r}"
                          + ("" if tid or not go else " (concept missing, skipped)"))
        if go and tid:
            for m in rows:
                touched_mentions.setdefault(m["id"], m)
                db.table("subject_mentions").update({"cluster_id": tid}) \
                    .eq("id", m["id"]).execute()
    for old, new in RENAME_SUBJECT.items():
        rows = [m for m in ms if str(m["subject"]).strip().lower() == old.lower()]
        plan_lines.append(f"rename {len(rows)} mention(s) {old!r} -> {new!r}")
        if go:
            for m in rows:
                touched_mentions.setdefault(m["id"], m)
                db.table("subject_mentions").update({"subject": new}).eq("id", m["id"]).execute()
    jl = [j.lower() for j in JUNK]
    rows = [m for m in ms if str(m["subject"]).strip().lower() in jl and not m.get("junk")]
    plan_lines.append(f"mark {len(rows)} mention(s) as junk: "
                      f"{sorted({m['subject'] for m in rows})}")
    if go:
        for m in rows:
            touched_mentions.setdefault(m["id"], m)
            db.table("subject_mentions").update({"junk": True}).eq("id", m["id"]).execute()

    print(f"\n{'APPLYING' if go else 'PREVIEW — nothing changed'} for {uid}:\n")
    for l in plan_lines:
        print("  " + l)

    if go:
        os.makedirs("backups", exist_ok=True)
        path = f"backups/concepts_{uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"user_id": uid, "at": _now(),
                       "clusters": list(touched_clusters.values()),
                       "events": touched_events, "mentions": list(touched_mentions.values()),
                       "created": created}, f, ensure_ascii=False, indent=1, default=str)
        print(f"\nDone. Backup of every changed row: {os.path.abspath(path)}")
        print(f"Undo: PYTHONPATH=. railway run python3 scripts/apply_concepts.py --undo {path}")
    else:
        print("\nRun again with --go to apply.")


def undo(path: str):
    from supabase_store import get_client
    db = get_client()
    b = json.load(open(path, encoding="utf-8"))
    for eid, cid in (b.get("events") or {}).items():
        db.table("user_behavioral_events").update({"cluster_id": cid}).eq("id", eid).execute()
    for c in b.get("clusters") or []:
        db.table("interest_clusters").update(
            {k: c.get(k) for k in ("label", "kind", "pillar", "status", "attributes",
                                   "event_count") if k in c}).eq("id", c["id"]).execute()
    for m in b.get("mentions") or []:
        db.table("subject_mentions").update(
            {"subject": m.get("subject"), "cluster_id": m.get("cluster_id"),
             "junk": bool(m.get("junk"))}).eq("id", m["id"]).execute()
    for cid in b.get("created") or []:
        db.table("interest_clusters").delete().eq("id", cid).execute()
    print(f"Restored {len(b.get('clusters') or [])} cluster(s), {len(b.get('events') or {})} "
          f"event(s), {len(b.get('mentions') or [])} mention(s); removed "
          f"{len(b.get('created') or [])} created cluster(s).")


if __name__ == "__main__":
    main()

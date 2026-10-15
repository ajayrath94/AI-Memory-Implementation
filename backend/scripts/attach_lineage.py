"""
ATTACH LINEAGE — hang her existing episodes and events under their concepts.

New ones attach themselves (episodes._concept_for, events._parent_for).
This does the ones from before:

    episodes   each under its illness ("Common cold"), found with the same
               check (concepts.same_as); a new illness concept is made
               archived — known, never offered
    events     the model reads all her events together, with what she said
               and the dates, and names what each was about — so the
               sightseeing and the outing on the days of the Delhi trip are
               about Delhi. Each goes under that concept (found or made).
               An ordinary meal filed as an event is set aside (archived).

    cd backend
    PYTHONPATH=. railway run python3 scripts/attach_lineage.py default           # preview
    PYTHONPATH=. railway run python3 scripts/attach_lineage.py default --go      # write, with a backup
    PYTHONPATH=. railway run python3 scripts/attach_lineage.py --undo backups/lineage_default_....json

Needs the lineage SQL first (health_episodes.cluster_id).
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _plan_events(events):
    from llm import ask
    listing = "\n".join(
        f'{i + 1}. "{e["label"]}" on {e.get("happened_on")} — she said: '
        f'"{str((e.get("attributes") or {}).get("said") or "")[:160]}"'
        for i, e in enumerate(events))
    raw = ask(f"""These are things an elderly woman in India told her companion had happened.

{listing}

For EACH, return:
  "about": the ONE thing it happened to or at, by its short plain name — the
           person who visited ("Arjun"), the place ("Zoo", "Delhi"), the
           activity ("Carrom"). Events on the same days as a trip, like its
           sightseeing or an outing, are about the trip's place.
  "about_kind": person | place | activity | health
  "meal": true if the event's name is a dish, a meal or food she cooked or
          ate — whatever else the same message mentions ("poha khaya, kal zoo
          jaenge" is a meal; the zoo is a plan). Not a meal only when the meal
          itself was the occasion (a birthday dinner, a feast for guests).

Return a JSON list: [{{"n": 1, "about": "...", "about_kind": "...", "meal": false}}]""",
               max_tokens=1500) or ""
    i, j = raw.find("["), raw.rfind("]")
    return json.loads(raw[i:j + 1]) if i >= 0 else []


def main():
    from supabase_store import get_client
    from memory.concepts import same_as
    db = get_client()

    if "--undo" in sys.argv:
        path = sys.argv[sys.argv.index("--undo") + 1]
        b = json.load(open(path))
        for e in b.get("episodes", []):
            db.table("health_episodes").update({"cluster_id": None}).eq("id", e["id"]).execute()
        for e in b.get("events", []):
            upd = {"parent_id": e.get("parent_id"), "status": e.get("status") or "active"}
            if e.get("merged"):
                row = (db.table("interest_clusters").select("attributes").eq("id", e["id"])
                       .limit(1).execute()).data
                a = dict((row[0].get("attributes") or {}) if row else {})
                a.pop("merged_into", None)
                upd["attributes"] = a
            db.table("interest_clusters").update(upd).eq("id", e["id"]).execute()
        for cid in b.get("created", []):
            db.table("interest_clusters").delete().eq("id", cid).execute()
        print(f"Undone: {len(b.get('episodes', []))} episodes, {len(b.get('events', []))} events, "
              f"{len(b.get('created', []))} concepts removed.")
        return

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    uid = args[0] if args else "default"
    go = "--go" in sys.argv
    print(f"\n{uid}: {'ATTACHING' if go else 'PREVIEW'}\n")
    backup = {"user_id": uid, "episodes": [], "events": [], "created": []}

    # ── episodes ──────────────────────────────────────────────────────────
    try:
        eps = (db.table("health_episodes").select("*").eq("user_id", uid)
               .execute()).data or []
    except Exception as e:
        print(f"health_episodes read failed (run the lineage SQL first?): {e}")
        return
    print("== EPISODES")
    for ep in eps:
        if ep.get("cluster_id"):
            continue
        name = ep.get("english") or ep["what"]
        hit = same_as(uid, name, kind="concern") or same_as(uid, ep["what"], kind="concern")
        target = (f"{hit['label']!r} [{hit['status']}]" if hit
                  else f"a new archived concept {name[:1].upper() + name[1:]!r}")
        print(f"  {ep['what']} ({ep.get('english')}) {str(ep.get('first_reported'))[:10]} "
              f"{ep.get('status')}  ->  {target}")
        if go:
            if hit:
                cid = hit["id"]
            else:
                from memory.episodes import _concept_for
                cid = _concept_for(uid, ep["what"], ep.get("english") or "", False)
                if cid:
                    backup["created"].append(cid)
            if cid:
                backup["episodes"].append({"id": ep["id"]})
                db.table("health_episodes").update({"cluster_id": cid}).eq("id", ep["id"]).execute()

    # ── events ────────────────────────────────────────────────────────────
    evs = [e for e in (db.table("interest_clusters").select("*").eq("user_id", uid)
                       .eq("kind", "event").execute()).data or []
           if (e.get("status") or "active") == "active" and not e.get("parent_id")]
    evs.sort(key=lambda e: str(e.get("happened_on")))
    print("\n== EVENTS")
    if not evs:
        print("  none to attach")
    plan = _plan_events(evs) if evs else []
    for p in plan:
        try:
            e = evs[int(p.get("n")) - 1]
        except Exception:
            continue
        if p.get("meal"):
            print(f"  {e['happened_on']} {e['label']:22} -> an ordinary meal: set aside")
            if go:
                backup["events"].append({"id": e["id"], "parent_id": None, "status": "active"})
                from memory.concepts import set_aside
                set_aside(e["id"], "a meal, not an event")
            continue
        about = str(p.get("about") or "").strip()
        kind = str(p.get("about_kind") or "")
        if not about or kind == "health":
            print(f"  {e['happened_on']} {e['label']:22} -> left alone ({kind or 'no subject'})")
            continue
        from memory.events import _ABOUT_KIND
        hit = same_as(uid, about, kind=_ABOUT_KIND.get(kind, ""))
        target = (f"{hit['label']!r}" if hit else f"a new {kind} concept {about!r}")
        print(f"  {e['happened_on']} {e['label']:22} -> about {about!r}: {target}")
        if go:
            from memory.events import _parent_for
            before = {r["id"] for r in (db.table("interest_clusters").select("id")
                                        .eq("user_id", uid).execute()).data or []}
            pid = _parent_for(uid, about, kind)
            if pid and pid not in before:
                backup["created"].append(pid)
            if pid:
                backup["events"].append({"id": e["id"], "parent_id": None, "status": "active"})
                db.table("interest_clusters").update({"parent_id": pid}).eq("id", e["id"]).execute()

    # One trip told as three events ("Delhi Trip", "Sightseeing", "Outing" on
    # 26-27 Sep) is one occurrence: the same rule new events follow — same
    # concept, within three days — applied to what was attached above. Soft:
    # the later ones forward to the first.
    print("\n== SAME OCCURRENCE")
    groups = {}
    for p in plan:
        try:
            e = evs[int(p.get("n")) - 1]
        except Exception:
            continue
        if p.get("meal") or not p.get("about") or p.get("about_kind") == "health":
            continue
        groups.setdefault(str(p["about"]).strip().lower(), []).append(e)
    from datetime import date as _date
    for about, es in groups.items():
        es = sorted(es, key=lambda e: str(e.get("happened_on")))
        keep = None
        for e in es:
            d = _date.fromisoformat(str(e["happened_on"])[:10])
            if keep and (d - _date.fromisoformat(str(keep["happened_on"])[:10])).days <= 3:
                print(f"  {e['happened_on']} {e['label']:22} -> same occurrence as "
                      f"{keep['label']!r} ({keep['happened_on']})")
                if go:
                    from memory.concepts import merge
                    merge(uid, keep["id"], e["id"], "same occurrence")
                    backup["events"].append({"id": e["id"], "parent_id": None, "status": "active",
                                             "merged": True})
            else:
                keep = e
    if not go:
        print("\nNothing changed. Add --go to attach.")
        return
    os.makedirs("backups", exist_ok=True)
    path = f"backups/lineage_{uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    json.dump(backup, open(path, "w"), indent=1)
    print(f"\nDone. Backup: {os.path.abspath(path)}")
    print(f"Undo: PYTHONPATH=. railway run python3 scripts/attach_lineage.py --undo {path}")


if __name__ == "__main__":
    main()

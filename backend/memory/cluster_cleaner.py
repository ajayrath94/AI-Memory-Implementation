"""
CLUSTER CLEANER — the Track 2 distillation pass.

Runs periodically (on the heartbeat), off the hot path. Two-stage design:
  STAGE 1 (vectors, free): centroid cosine finds cluster pairs that are
    plausibly the same real thing — recall, cheap.
  STAGE 2 (LLM, only on candidates): Haiku confirms same-entity, supplies the
    canonical name, and flags phrase/fragment labels to normalize or drop —
    precision + meaning.
Vectors propose (what's similar); the LLM disposes (what it means, what to call
it, whether to merge). Conservative: merges only when the LLM confirms same
entity; fails toward leaving clusters separate.
"""
import os, json
from itertools import combinations

MERGE_COSINE = 0.82          # centroid similarity to become a merge CANDIDATE
_MODEL = "claude-haiku-4-5-20251001"


def _parse_centroid(c):
    if not c:
        return None
    if isinstance(c, list):
        return c
    try:
        return json.loads(c)
    except Exception:
        return None


def _cos(a, b):
    try:
        from classifier.pillar_classifier import cosine_similarity
        return cosine_similarity(a, b)
    except Exception:
        return 0.0


def _candidate_groups(clusters):
    """Union-find over cluster pairs whose centroids are cosine >= MERGE_COSINE."""
    parent = {c["id"]: c["id"] for c in clusters}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    vecs = {c["id"]: _parse_centroid(c.get("centroid")) for c in clusters}
    for a, b in combinations(clusters, 2):
        va, vb = vecs[a["id"]], vecs[b["id"]]
        if va and vb and _cos(va, vb) >= MERGE_COSINE:
            union(a["id"], b["id"])

    groups = {}
    for c in clusters:
        groups.setdefault(find(c["id"]), []).append(c)
    # only groups with 2+ members are merge candidates
    return [g for g in groups.values() if len(g) >= 2]


def _llm_plan(clusters, candidate_groups):
    """Ask Haiku to (a) confirm/reject each candidate merge + name it, and
    (b) flag any label that is a phrase/fragment, not an entity noun."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    lines = []
    for c in clusters:
        lines.append(f'  id={c["id"][:8]} label="{c["label"]}" pillar={c["pillar"]} attrs={c.get("attributes") or {}}')
    all_block = "\n".join(lines)

    cand_block = ""
    for i, g in enumerate(candidate_groups):
        ids = ", ".join(f'{c["id"][:8]}("{c["label"]}")' for c in g)
        cand_block += f'  group {i}: {ids}\n'
    if not cand_block:
        cand_block = "  (none)\n"

    prompt = f"""You clean a memory system's entity clusters. Two jobs.

ALL CLUSTERS:
{all_block}

MERGE CANDIDATES (vector-similar — may or may not be the same real thing):
{cand_block}
JOB 1 — MERGES: For each candidate group, decide if they are the SAME real
entity (e.g. "daughter" and "Meena" = the same person; a role word and her
name). Only merge if you are confident they are literally the same thing. NEVER
merge two different people, or two different conditions, even if similar. For a
confirmed merge, pick the best canonical label (a proper NAME beats a role word:
prefer "Meena" over "daughter").

JOB 2 — LABELS: Any label that is a phrase, action, or sentence fragment rather
than a clean entity noun should be normalized to its canonical noun, or dropped
if there is no real entity in it.
- "received medicine from doctor" -> rename to "medicine"
- "while climbing stairs" -> this is a fragment of knee pain; if a "knee pain"
  cluster exists, DROP this (it's not its own thing); else rename to "knee pain"
- a clean noun like "high blood pressure", "Arjun", "cricket" -> leave alone

Return ONLY JSON:
{{
  "merges": [{{"keep_id": "8charid", "absorb_ids": ["8charid"], "canonical_label": "Meena", "reason": "same person"}}],
  "renames": [{{"id": "8charid", "canonical_label": "medicine"}}],
  "drops": [{{"id": "8charid", "reason": "fragment of knee pain"}}]
}}
Use the 8-char id prefixes shown above. Empty lists if nothing to do. No prose."""

    resp = client.messages.create(
        model=_MODEL, max_tokens=1500,
        messages=[{"role": "user", "content": prompt}])
    txt = resp.content[0].text.strip()
    if txt.startswith("```"):
        txt = txt.split("```")[1].replace("json", "", 1).strip()
    try:
        return json.loads(txt)
    except Exception as e:
        print(f"[Cleaner] LLM plan parse failed: {e} | raw={txt[:200]}")
        return {"merges": [], "renames": [], "drops": []}


def _full_id(prefix, clusters):
    for c in clusters:
        if c["id"].startswith(prefix):
            return c["id"]
    return None


def clean_clusters(user_id: str, dry_run: bool = False) -> dict:
    from supabase_store import get_client
    db = get_client()
    clusters = (db.table("interest_clusters").select(
        "id,label,pillar,strength,event_count,attributes,centroid")
        .eq("user_id", user_id).execute()).data or []
    if len(clusters) < 2:
        return {"skipped": "fewer than 2 clusters", "clusters": len(clusters)}

    groups = _candidate_groups(clusters)
    plan = _llm_plan(clusters, groups)
    report = {"merges": [], "renames": [], "drops": [], "dry_run": dry_run}

    # DROPS
    for d in plan.get("drops", []):
        cid = _full_id(d.get("id", ""), clusters)
        if not cid:
            continue
        report["drops"].append(d)
        if not dry_run:
            try:
                db.table("user_behavioral_events").delete().eq("cluster_id", cid).execute()
                db.table("interest_clusters").delete().eq("id", cid).execute()
            except Exception as e:
                print(f"[Cleaner] drop failed: {e}")

    # RENAMES
    for r in plan.get("renames", []):
        cid = _full_id(r.get("id", ""), clusters)
        lbl = r.get("canonical_label")
        if not cid or not lbl:
            continue
        report["renames"].append(r)
        if not dry_run:
            try:
                db.table("interest_clusters").update({"label": lbl}).eq("id", cid).execute()
            except Exception as e:
                print(f"[Cleaner] rename failed: {e}")

    # MERGES
    for m in plan.get("merges", []):
        keep = _full_id(m.get("keep_id", ""), clusters)
        absorb = [_full_id(a, clusters) for a in m.get("absorb_ids", [])]
        absorb = [a for a in absorb if a and a != keep]
        lbl = m.get("canonical_label")
        if not keep or not absorb:
            continue
        report["merges"].append(m)
        if dry_run:
            continue
        try:
            keep_row = next(c for c in clusters if c["id"] == keep)
            absorb_rows = [c for c in clusters if c["id"] in absorb]
            new_strength = round((keep_row.get("strength") or 0)
                                 + sum((c.get("strength") or 0) for c in absorb_rows), 4)
            new_events = (keep_row.get("event_count") or 0) \
                         + sum((c.get("event_count") or 0) for c in absorb_rows)
            merged_attrs = dict(keep_row.get("attributes") or {})
            for c in absorb_rows:
                for k, v in (c.get("attributes") or {}).items():
                    if v and not merged_attrs.get(k):
                        merged_attrs[k] = v
            upd = {"strength": new_strength, "event_count": new_events,
                   "attributes": merged_attrs}
            if lbl:
                upd["label"] = lbl
            db.table("interest_clusters").update(upd).eq("id", keep).execute()
            for a in absorb:
                db.table("user_behavioral_events").update(
                    {"cluster_id": keep}).eq("cluster_id", a).execute()
                db.table("interest_clusters").delete().eq("id", a).execute()
        except Exception as e:
            print(f"[Cleaner] merge failed: {e}")

    report["summary"] = (f"{len(report['merges'])} merges, "
                         f"{len(report['renames'])} renames, "
                         f"{len(report['drops'])} drops")
    print(f"[Cleaner] {user_id}: {report['summary']}"
          + (" (dry run)" if dry_run else ""))
    return report

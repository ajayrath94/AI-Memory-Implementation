"""
CLUSTER RESOLVER — decide which ongoing concern a new event belongs to.

One level up from entity resolution. Entity resolution answers "is this the
same *thing* said differently" (knee / ghutne ka dard -> knee pain). Cluster
resolution answers "does this belong to the same ongoing *concern*"
(amlodipine, blood pressure, BP medication -> one blood-pressure cluster).

Because a concern legitimately spans related-but-distinct entities, the LLM
judge here asks a broader question than the entity judge: not "same thing" but
"same ongoing situation".
"""

import os
import json
from typing import Optional, List

# A concern is broader than a synonym, so the floor sits a touch lower than the
# entity resolver's 0.87 — but still well above the ~0.81 noise floor measured
# on gemini-embedding-001.
CLUSTER_FLOOR = 0.84
MAX_CANDIDATES = 4


def _cosine(a, b) -> float:
    from classifier.pillar_classifier import cosine_similarity
    return cosine_similarity(a, b)


def find_cluster(user_id: str, label: str, pillar: str,
                 embedding: List[float]) -> Optional[str]:
    """
    Return the id of the cluster this event belongs to, or None for a new one.

    Reuses the embedding the entity resolver already computed — no extra call.
    """
    if not embedding:
        return None

    try:
        from supabase_store import get_client
        db = get_client()
        rows = (db.table("interest_clusters")
                .select("id,label,pillar,centroid")
                .eq("user_id", user_id)
                .eq("pillar", pillar)            # concerns don't cross pillars
                .not_.is_("centroid", "null")
                .limit(100)
                .execute()).data or []
    except Exception as e:
        print(f"[ClusterResolver] fetch failed: {e}")
        return None

    scored = []
    for r in rows:
        cen = r.get("centroid")
        if isinstance(cen, str):
            try:
                cen = json.loads(cen)
            except Exception:
                continue
        if not cen:
            continue
        s = _cosine(embedding, cen)
        if s >= CLUSTER_FLOOR:
            scored.append({"id": r["id"], "label": r["label"], "score": round(s, 4)})

    if not scored:
        return None

    scored.sort(key=lambda x: x["score"], reverse=True)
    candidates = scored[:MAX_CANDIDATES]

    verdict = _adjudicate(label, candidates)
    if verdict:
        print(f"[ClusterResolver] {label!r} -> cluster {verdict['label']!r} "
              f"({[c['label'] for c in candidates]})")
        return verdict["id"]
    return None


def _adjudicate(label: str, candidates: List[dict]) -> Optional[dict]:
    """
    Does this new thing belong to one of these ongoing concerns?

    Broader than the entity judge: amlodipine BELONGS to a blood-pressure
    concern even though it is not a synonym for it. But knee pain does NOT
    belong to a blood-pressure concern, and cricket does not belong to a
    music concern — those are different situations.
    """
    listing = "\n".join(f"- {c['label']}" for c in candidates)
    prompt = f"""A person mentioned: "{label}"

They have these ongoing concerns / interests already tracked:
{listing}

Does "{label}" BELONG TO one of these ongoing concerns — i.e. is it part of
the same situation the person is dealing with over time?

Belongs (answer the concern name):
- a treatment, symptom, doctor, or medicine for a health concern already listed
  (amlodipine belongs to "blood pressure"; ankle swelling from BP meds belongs to "blood pressure")
- a specific instance of a listed interest (a particular match belongs to "cricket")

Does NOT belong (answer NEW):
- a different body part or condition (knee pain is not blood pressure)
- a different topic entirely
- a broader category than what is listed

When unsure, answer NEW — a wrong merge corrupts the timeline.

Reply with exactly one line: the concern name verbatim, or NEW."""

    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        resp = client.models.generate_content(
            model="gemini-flash-lite-latest", contents=prompt)
        answer = (resp.text or "").strip().strip('"').strip()

        if answer.upper() == "NEW" or not answer:
            return None
        for c in candidates:
            if answer.lower() == c["label"].lower():
                return c
        return None
    except Exception as e:
        print(f"[ClusterResolver] adjudication failed: {e}")
        return None

def _general_label(a: str, b: str) -> str:
    """Of two labels for one concern, return the more general (condition over instance)."""
    if a.strip().lower() == b.strip().lower():
        return a
    prompt = f"""Two labels describe the same ongoing concern:
- "{a}"
- "{b}"

Which is the more general name for the concern itself — the condition or theme,
rather than a specific instance, treatment, or detail?
Examples: between "amlodipine" and "blood pressure", choose "blood pressure".
Between "India match" and "cricket", choose "cricket".
Reply with exactly one of the two labels, verbatim. No other text."""
    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        resp = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
        ans = (resp.text or "").strip().strip('"').strip()
        for lab in (a, b):
            if ans.lower() == lab.lower():
                return lab
        return a
    except Exception as e:
        print(f"[ClusterResolver] general-label pick failed: {e}")
        return a


def merge_clusters(user_id: str, keep_id: str, absorb_id: str, label: str = None):
    """
    Fold one cluster into another: repoint its events, sum the totals,
    recompute the centroid as the count-weighted mean, delete the absorbed row.
    """
    from supabase_store import get_client
    db = get_client()
    try:
        rows = (db.table("interest_clusters")
                .select("id,event_count,strength,centroid")
                .in_("id", [keep_id, absorb_id]).execute()).data or []
        by_id = {r["id"]: r for r in rows}
        keep, absorb = by_id.get(keep_id), by_id.get(absorb_id)
        if not keep or not absorb:
            return

        kn, an = keep.get("event_count") or 0, absorb.get("event_count") or 0
        kc, ac = keep.get("centroid"), absorb.get("centroid")
        merged_centroid = keep.get("centroid")
        if kc and ac and len(kc) == len(ac) and (kn + an) > 0:
            merged_centroid = [
                round((k * kn + a * an) / (kn + an), 6)
                for k, a in zip(kc, ac)
            ]

        db.table("user_behavioral_events").update(
            {"cluster_id": keep_id}).eq("cluster_id", absorb_id).execute()

        db.table("interest_clusters").delete().eq("id", absorb_id).execute()

        # Recompute the count from actual rows rather than summing — the summed
        # value can drift if any event was pointing at a stale cluster id.
        real = (db.table("user_behavioral_events")
                .select("id", count="exact")
                .eq("cluster_id", keep_id).execute())
        real_count = real.count if real.count is not None else (kn + an)

        update = {
            "event_count": real_count,
            "strength":    round((keep.get("strength") or 0) + (absorb.get("strength") or 0), 4),
            "centroid":    merged_centroid,
        }
        if label:
            update["label"] = label
        db.table("interest_clusters").update(update).eq("id", keep_id).execute()
        print(f"[ClusterResolver] merged {absorb_id} -> {keep_id}")
        return keep_id
    except Exception as e:
        print(f"[ClusterResolver] merge failed: {e}")
        return keep_id


def reconcile(user_id: str, cluster_id: str, pillar: str):
    """
    Deferred merge: after a cluster is created/updated, check whether any OTHER
    cluster in the same pillar is now close enough to be the same concern.

    Fixes the order-of-arrival problem — "amlodipine" arriving before the
    "blood pressure" cluster exists creates an orphan that this later folds in.
    """
    from supabase_store import get_client
    db = get_client()
    try:
        rows = (db.table("interest_clusters")
                .select("id,label,event_count,centroid")
                .eq("user_id", user_id).eq("pillar", pillar)
                .not_.is_("centroid", "null").limit(100).execute()).data or []
    except Exception as e:
        print(f"[ClusterResolver] reconcile fetch failed: {e}")
        return

    this = next((r for r in rows if r["id"] == cluster_id), None)
    if not this or not this.get("centroid"):
        return
    this_cen = this["centroid"]
    if isinstance(this_cen, str):
        try: this_cen = json.loads(this_cen)
        except Exception: return

    for r in rows:
        if r["id"] == cluster_id:
            continue
        cen = r.get("centroid")
        if isinstance(cen, str):
            try: cen = json.loads(cen)
            except Exception: continue
        if not cen:
            continue
        if _cosine(this_cen, cen) >= CLUSTER_FLOOR:
            # Same "belongs to same concern" judge, applied cluster-to-cluster.
            verdict = _adjudicate(r["label"], [{"id": this["id"], "label": this["label"]}])
            if verdict:
                # Keep the one with more events as the survivor.
                keep, absorb = (this, r) if (this.get("event_count") or 0) >= (r.get("event_count") or 0) else (r, this)
                # Survivor id is the bigger cluster (fewer rows to repoint), but
                # the LABEL should be the more general concern name, not whichever
                # instance happened to arrive first.
                label = _general_label(keep["label"], absorb["label"])
                merge_clusters(user_id, keep["id"], absorb["id"], label)
                return keep["id"]

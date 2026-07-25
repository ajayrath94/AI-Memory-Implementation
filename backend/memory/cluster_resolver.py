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

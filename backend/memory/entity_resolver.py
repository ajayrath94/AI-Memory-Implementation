"""
ENTITY RESOLVER — decide whether a newly extracted entity is something we
already track for this user, or genuinely new.

Why this exists: counting is exact-match, so "knee" on Monday and "knee pain"
on Thursday fragment into two interests and the signal degrades.

Why it is not just a cosine threshold: measured on real data with
gemini-embedding-001, unrelated concepts floor around 0.81 and true matches
top out around 0.96 — but "joint pain"/"back pain" (different body parts)
scores 0.92, ABOVE pairs that should merge. Cosine is symmetric and cannot
express "one is broader than the other", so it cannot separate synonymy from
hierarchy. Embeddings therefore do candidate RETRIEVAL; an LLM makes the call.
"""

import os
import json
from typing import Optional, List

# Below this, not even worth asking about. Set from measured data: unrelated
# pairs sat at 0.79-0.82, so this only filters the obvious floor.
CANDIDATE_FLOOR = 0.87
MAX_CANDIDATES  = 5


def embed_entity(name: str, entity_type: str = "") -> Optional[List[float]]:
    """
    Embed an entity name with a type tag for context.

    Bare 1-2 word strings embed poorly (anisotropy — everything crowds into a
    narrow cone). Adding the type separates "puja (activity)" from
    "puja (person)" and gives the vector something to hang on.
    """
    try:
        from google import genai
        from google.genai import types

        text = f"{name} ({entity_type})" if entity_type else name
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        resp = client.models.embed_content(
            model="models/gemini-embedding-001",
            contents=text,
            config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY"),
        )
        return list(resp.embeddings[0].values)
    except Exception as e:
        print(f"[Resolver] embed failed for {name!r}: {e}")
        return None


def _candidates(user_id: str, vector: List[float], pillar: str = "") -> List[dict]:
    """
    Nearest existing entities for this user, above the floor.

    Exact comparison rather than an ANN index: pgvector caps HNSW at 2000
    dimensions and these vectors are 3072, and per-user entity counts are small
    enough that scanning them is trivially fast.
    """
    from classifier.pillar_classifier import cosine_similarity
    from supabase_store import get_client

    try:
        q = (get_client()
             .table("user_behavioral_events")
             .select("value,sub_pillar,pillar,embedding")
             .eq("user_id", user_id)
             .not_.is_("embedding", "null")
             .order("created_at", desc=True)
             .limit(400))
        rows = (q.execute()).data or []
    except Exception as e:
        print(f"[Resolver] candidate fetch failed: {e}")
        return []

    best = {}
    for r in rows:
        name = (r.get("value") or "").strip()
        emb  = r.get("embedding")
        if not name or not emb:
            continue
        if isinstance(emb, str):
            try:
                emb = json.loads(emb)
            except Exception:
                continue
        score = cosine_similarity(vector, emb)
        if score >= CANDIDATE_FLOOR and score > best.get(name, {}).get("score", 0):
            best[name] = {"name": name, "score": round(score, 4),
                          "type": r.get("sub_pillar"), "pillar": r.get("pillar")}

    out = sorted(best.values(), key=lambda x: x["score"], reverse=True)
    return out[:MAX_CANDIDATES]


def resolve(name: str, entity_type: str, pillar: str, user_id: str) -> dict:
    """
    Returns {"name": <canonical name to use>, "embedding": [...], "matched": bool}

    Falls back to the extracted name on any failure — a missed merge costs some
    signal, a wrong merge silently corrupts it, so we bias toward not merging.
    """
    vector = embed_entity(name, entity_type)
    if not vector:
        return {"name": name, "embedding": None, "matched": False}

    cands = _candidates(user_id, vector, pillar)
    if not cands:
        return {"name": name, "embedding": vector, "matched": False}

    verdict = _adjudicate(name, entity_type, cands)
    if verdict:
        print(f"[Resolver] {name!r} -> {verdict!r} (was {[c['name'] for c in cands]})")
        return {"name": verdict, "embedding": vector, "matched": True}

    return {"name": name, "embedding": vector, "matched": False}


def _adjudicate(name: str, entity_type: str, candidates: List[dict]) -> Optional[str]:
    """
    Ask the model whether the new entity IS one of the candidates.

    The distinction that matters and that cosine cannot make: same thing
    (merge) versus broader/narrower thing (do not merge). "knee pain" and
    "arthritis" score 0.90 but are a symptom and a diagnosis; collapsing them
    would corrupt exactly the signal we are trying to measure.
    """
    listing = "\n".join(f"- {c['name']}" for c in candidates)
    prompt = f"""A person mentioned: "{name}" (type: {entity_type or 'unknown'})

We already track these for them:
{listing}

Does "{name}" refer to the SAME real-world thing as one of the tracked items?

Answer with the tracked name ONLY if they are the same thing said differently
(synonyms, translations, more or less specific wording for the identical thing).

Answer "NEW" if it is:
- a broader or narrower category (arthritis vs knee pain; old Hindi songs vs Kishore Kumar)
- a different instance of the same kind (back pain vs knee pain; Lata vs Kishore)
- merely related or topically similar

When unsure, answer NEW. A wrong merge is worse than a missed one.

Reply with exactly one line: either the tracked name verbatim, or NEW."""

    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        resp = client.models.generate_content(
            model="gemini-flash-lite-latest", contents=prompt)
        answer = (resp.text or "").strip().strip('"').strip()

        if answer.upper() == "NEW" or not answer:
            return None
        for c in candidates:
            if answer.lower() == c["name"].lower():
                return c["name"]
        print(f"[Resolver] judge returned unrecognised {answer!r}, treating as NEW")
        return None
    except Exception as e:
        print(f"[Resolver] adjudication failed: {e}")
        return None

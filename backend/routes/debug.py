"""
DEBUG — inspection endpoints for tuning extraction.

Read-only: classifies and extracts, writes nothing. Runs on Railway so it
uses the real environment rather than an approximation of it.
"""

import os, json
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()


class ExtractRequest(BaseModel):
    messages: List[str]
    user_id:  str = "debug_user"   # so known-entity reuse can be exercised


@router.post("/extract")
def debug_extract(req: ExtractRequest):
    """Show what the classifier and entity extractor make of each message."""
    from classifier.pillar_classifier import classify_input
    from memory.profile_enricher import _should_run_haiku, _haiku_extract

    out = []

    for msg in req.messages[:25]:
        cl = classify_input(msg)
        run, hint = _should_run_haiku(cl)

        row = {
            "message":  msg,
            "core":     f"{cl.core}/{cl.core_priority}",
            "core_score": round(getattr(cl, "core_score", 0.0), 4),
            "emotion":  f"{cl.emotion}/{cl.emotion_priority}",
            "emotion_score": round(getattr(cl, "emotion_score", 0.0), 4),
            "gated_in": run,
            "entities": [],
        }

        if run:
            # Call the REAL extractor rather than a copy of its prompt — a debug
            # tool that tests different code than production is worse than none.
            try:
                res = _haiku_extract(msg, hint, req.user_id)
                ents = res.get("entities", [])
                row["entities"] = ents
                from memory.profile_enricher import _safe_salience
                sal = [_safe_salience(e.get("salience")) for e in ents] or [0.0]
                top = max(sal)
                row["salience_priority"] = (
                    "HIGH" if top >= 0.8 else ("MEDIUM" if top >= 0.5 else "LOW"))
                row["max_salience"] = round(top, 3)
                row["profile_fields"] = {
                    k: v for k, v in res.items()
                    if k != "entities" and v
                }
            except Exception as e:
                row["error"] = str(e)

        out.append(row)

    return {"results": out}

class SimilarityRequest(BaseModel):
    names: List[str]
    task_type: str = "SEMANTIC_SIMILARITY"
    context_tag: bool = False    # embed "knee pain (health)" instead of "knee pain"


@router.post("/similarity")
def debug_similarity(req: SimilarityRequest):
    """
    Pairwise cosine similarity between entity names.

    Exists to CALIBRATE the merge threshold rather than guess it: run it on
    real entities plus deliberate near-miss pairs and look at where true
    matches separate from true non-matches.
    """
    from google import genai
    from google.genai import types
    from classifier.pillar_classifier import cosine_similarity

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    vectors, failed = [], []

    for n in req.names[:40]:
        text = n
        try:
            resp = client.models.embed_content(
                model="models/gemini-embedding-001",
                contents=text,
                config=types.EmbedContentConfig(task_type=req.task_type),
            )
            vectors.append(list(resp.embeddings[0].values))
        except Exception as e:
            failed.append({"name": n, "error": str(e)[:200]})
            vectors.append(None)

    pairs = []
    for i in range(len(req.names[:40])):
        for j in range(i + 1, len(req.names[:40])):
            if vectors[i] and vectors[j]:
                pairs.append({
                    "a": req.names[i],
                    "b": req.names[j],
                    "cosine": cosine_similarity(vectors[i], vectors[j]),
                })

    pairs.sort(key=lambda x: x["cosine"], reverse=True)
    return {"task_type": req.task_type, "failed": failed, "pairs": pairs}

@router.get("/interests/{user_id}")
def debug_interests(user_id: str, pillar: str = ""):
    """Decay-weighted interest ranking — the recommendation engine's input."""
    from memory.interest_scores import get_interest_scores
    return {"interests": get_interest_scores(user_id, pillar)}


@router.get("/time/{user_id}")
def debug_time_context(user_id: str):
    """Show the full temporal picture for a user — local time, slot, mode, silence."""
    from memory.time_context import time_context
    return time_context(user_id)


@router.get("/proactive/{user_id}")
def debug_proactive(user_id: str, hour: int = None):
    """What would the proactive engine decide? Optional ?hour= to simulate time."""
    from memory.proactive_engine import proactive_check
    return proactive_check(user_id, override_hour=hour)

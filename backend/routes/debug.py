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
            "emotion":  f"{cl.emotion}/{cl.emotion_priority}",
            "gated_in": run,
            "entities": [],
        }

        if run:
            # Call the REAL extractor rather than a copy of its prompt — a debug
            # tool that tests different code than production is worse than none.
            try:
                res = _haiku_extract(msg, hint, req.user_id)
                row["entities"] = res.get("entities", [])
                row["profile_fields"] = {
                    k: v for k, v in res.items()
                    if k != "entities" and v
                }
            except Exception as e:
                row["error"] = str(e)

        out.append(row)

    return {"results": out}

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


@router.post("/extract")
def debug_extract(req: ExtractRequest):
    """Show what the classifier and entity extractor make of each message."""
    from classifier.pillar_classifier import classify_input
    from memory.profile_enricher import _should_run_haiku, _pillar_guide

    guide, names = _pillar_guide()
    options = "|".join(names)
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
            prompt = f"""Extract what this person is telling you about.

Pillar definitions:
{guide}

Message: "{msg}"

For each specific thing mentioned, return:
- name: the thing itself, stripped of connectors. Noun form.
- action: what happened to it, as a single verb or short verb phrase
- sentiment: positive | negative | neutral — how THEY feel about it
- salience: 0.0-1.0 — how much this matters to them right now
- type: person|artist|hobby|health|place|food|media|activity|other
- pillar: {options}

Return ONLY JSON: {{"entities": [...]}}
Empty list if nothing specific is mentioned. Do not invent things.

Example:
"I was listening to Mohammed Rafi but my back has been aching badly"
{{"entities": [
  {{"name": "Mohammed Rafi", "action": "listened", "sentiment": "positive", "salience": 0.6, "type": "artist", "pillar": "ENTERTAINMENT"}},
  {{"name": "back pain", "action": "worsening", "sentiment": "negative", "salience": 0.9, "type": "health", "pillar": "HEALTH_WELLNESS"}}
]}}"""
            try:
                from google import genai
                client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
                resp = client.models.generate_content(
                    model="gemini-flash-lite-latest", contents=prompt)
                raw = (resp.text or "").strip().replace("```json", "").replace("```", "").strip()
                row["entities"] = (json.loads(raw) if raw else {}).get("entities", [])
            except Exception as e:
                row["error"] = str(e)

        out.append(row)

    return {"results": out}

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


@router.get("/scheduler-pass")
def debug_scheduler_pass(dry_run: bool = True):
    """Run one scheduler pass. dry_run=true (default) decides but does NOT log."""
    from memory.scheduler import run_scheduler_pass
    return run_scheduler_pass(dry_run=dry_run)


@router.get("/memory-trace/{user_id}")
def memory_trace(user_id: str):
    """
    THE MEMORY LENS. One view of everything memory knows about a user, across
    both tracks, with text + vector status at each tier, plus what recall
    actually returns. Reads persistent DB state (not ephemeral logs), so you can
    inspect any user any time. This is the debugging tool for all memory work.
    """
    from supabase_store import get_client
    db = get_client()
    out = {"user_id": user_id, "track1_conversation": {}, "track2_person": {}, "recall": {}}

    def _vec_status(v):
        if v is None:
            return "none"
        if isinstance(v, str):
            return f"str[{len(v)} chars]"
        if isinstance(v, list):
            return f"list[{len(v)} dims]"
        return type(v).__name__

    # ── TRACK 1: conversation (cache in-memory can't be read per-user here; STM + LTM from DB) ──
    try:
        stm = (db.table("stm_clusters").select("pillar,text,strength,embedding")
               .order("id", desc=True).limit(200).execute()).data or []
        # stm is session-keyed today; we can't filter by user yet, so show recent themes
        out["track1_conversation"]["stm_recent"] = [
            {"pillar": s.get("pillar"), "text": s.get("text"),
             "strength": s.get("strength"), "vector": _vec_status(s.get("embedding"))}
            for s in stm[:15]
        ]
        out["track1_conversation"]["stm_note"] = "STM is session-keyed (not user-scoped yet — #2 will fix)"
    except Exception as e:
        out["track1_conversation"]["stm_error"] = str(e)

    try:
        um = (db.table("user_memory").select("summary,key_facts,session_count")
              .eq("user_id", user_id).execute()).data
        if um:
            out["track1_conversation"]["ltm_summary"] = {
                "summary": um[0].get("summary"),
                "key_facts": um[0].get("key_facts"),
                "session_count": um[0].get("session_count"),
            }
        else:
            out["track1_conversation"]["ltm_summary"] = None
    except Exception as e:
        out["track1_conversation"]["ltm_error"] = str(e)

    # ── TRACK 2: person (clusters + events) ──
    try:
        clusters = (db.table("interest_clusters")
                    .select("label,pillar,status,strength,event_count,first_seen,last_event,centroid")
                    .eq("user_id", user_id).order("strength", desc=True).limit(60).execute()).data or []
        out["track2_person"]["clusters"] = [
            {"label": c.get("label"), "pillar": c.get("pillar"), "status": c.get("status"),
             "strength": c.get("strength"), "event_count": c.get("event_count"),
             "text": c.get("label"), "vector": _vec_status(c.get("centroid"))}
            for c in clusters
        ]
        out["track2_person"]["cluster_count"] = len(clusters)
    except Exception as e:
        out["track2_person"]["clusters_error"] = str(e)

    try:
        events = (db.table("user_behavioral_events")
                  .select("value,pillar,sentiment,salience,event_type,created_at")
                  .eq("user_id", user_id).order("created_at", desc=True).limit(20).execute()).data or []
        out["track2_person"]["recent_events"] = events
        out["track2_person"]["event_count"] = len(events)
    except Exception as e:
        out["track2_person"]["events_error"] = str(e)

    # ── RECALL: what Nancy actually gets ──
    try:
        from memory.user_memory_store import build_memory_prompt
        recalled = build_memory_prompt(user_id)   # no embedding = strength-only view
        out["recall"]["build_memory_prompt"] = recalled
        out["recall"]["note"] = "strength-only here; live recall also adds similarity via current message embedding"
    except Exception as e:
        out["recall"]["error"] = str(e)

    return out


@router.post("/prop-extract")
def prop_extract(payload: dict):
    """TEMP: test proposition extraction on the deployed backend (has google-genai).
    POST {"text": "..."} -> returns the LLM's proposition array. Remove after tuning."""
    import os, json
    text = payload.get("text", "")
    PROMPT = '''You extract PROPOSITIONS (subject-relation-object facts) from an elderly person's message, including Hindi/Hinglish.

For EACH fact return an object:
- subject: canonical name (translate common nouns to English: "ghutne ka dard"->"knee pain"; keep proper nouns: "Vikram")
- subject_ref: proper_name | son | daughter | husband | wife | grandchild | pronoun | self
- relation: likes | stopped_liking | lives_in | works_as | is | has_condition | feels | did
- object: canonical target ("Amreeka"->"America") or null
- entity_type: person | food | health | hobby | artist | media | place | belief | other
- pillar: FAMILY | HEALTH_WELLNESS | ENTERTAINMENT | ASPIRATIONS | FINANCE | GENERAL. Pillar follows entity_type, NOT sentence context.
- sentiment: positive | negative | neutral
- is_correction: true if message CHANGES/RETRACTS a prior fact (switched, gave up, "no wait", actually, "I meant", "prefer X now", "not X anymore")
- replaces: prior thing overridden ("coffee") or null
- attributes: for people only {relationship, location, occupation}

RULES:
- Different relationships (son AND daughter) are DIFFERENT subjects — NEVER merge.
- A role/pronoun ("beta","my boy","he") for an already-named person uses that PERSON'S proper name as subject.
- "switched to tea, gave up coffee" -> [{"subject":"tea","relation":"likes","is_correction":true,"replaces":"coffee"},{"subject":"coffee","relation":"stopped_liking","is_correction":true,"replaces":null}]

Return ONLY a JSON array. Message:
"''' + text + '"'
    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        resp = client.models.generate_content(model="gemini-flash-lite-latest", contents=PROMPT)
        raw = (resp.text or "").strip().replace("```json", "").replace("```", "").strip()
        return {"text": text, "propositions": json.loads(raw) if raw else []}
    except Exception as e:
        return {"text": text, "error": str(e)}

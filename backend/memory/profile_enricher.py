"""
PROFILE ENRICHER v2 — Zero pattern matching

Two sources of truth:
  1. Classification output (ClassifiedInput) — health, emotion, priority, language
  2. Claude Haiku micro-extraction — named entities only (name, family, places)

Haiku extraction only fires when classification signals something worth extracting,
keeping cost minimal (~50 tokens per triggered message).
"""

import os
import json
from typing import Optional


# ── Haiku micro-extractor ──────────────────────────────────────────────────────

def _pillar_guide() -> str:
    """
    Build the pillar definitions for the extraction prompt from pillars.xml —
    the same source the embedding classifier uses. Hardcoding the list here
    would silently drift the moment a pillar is added or renamed.
    """
    try:
        from classifier.pillar_classifier import CORE_PILLARS, _get_matrix
        lines = []
        for name in CORE_PILLARS:
            m = _get_matrix(name) or {}
            subject = (m.get("SUBJECT", {}) or {}).get("primary", "")
            action  = (m.get("ACTION",  {}) or {}).get("primary", "")
            lines.append(f"- {name}: about {subject or 'general topics'}; "
                         f"typically {action or 'anything else'}")
        return "\n".join(lines), CORE_PILLARS
    except Exception as e:
        print(f"[ProfileEnricher] pillar guide unavailable: {e}")
        fallback = ["HEALTH_WELLNESS", "FINANCE", "CAREER_GOAL",
                    "ASPIRATIONS", "ENTERTAINMENT", "GENERAL"]
        return "\n".join(f"- {p}" for p in fallback), fallback


def _known_entities(user_id: str, limit: int = 60) -> list:
    """
    Entity names already tracked for this user, most recent first.

    Passed into the extraction prompt so the model MATCHES an existing name
    rather than inventing a new one each time. Without this the same knee
    becomes "knee pain" on Monday and "knee" on Thursday, and the two never
    accumulate into one interest.
    """
    if not user_id:
        return []
    try:
        from supabase_store import get_client
        rows = (get_client()
                .table("user_behavioral_events")
                .select("value")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(300)
                .execute()).data or []
        seen = []
        for r in rows:
            v = (r.get("value") or "").strip()
            if v and v not in seen:
                seen.append(v)
            if len(seen) >= limit:
                break
        return seen
    except Exception as e:
        print(f"[ProfileEnricher] known entities unavailable: {e}")
        return []


def _haiku_extract(text: str, context: str, user_id: str = "") -> dict:
    """
    Single focused Haiku call to extract named entities.
    Returns only what's confidently found — no guessing.
    """
    known = _known_entities(user_id)
    known_block = ("\nAlready tracked for this person — REUSE these exact names "
                   "if the message refers to the same thing:\n"
                   + "\n".join(f"- {k}" for k in known)) if known else ""

    guide, pillar_names = _pillar_guide()
    pillar_options = "|".join(pillar_names)

    prompt = f"""Extract factual information from this message. Context: {context}

Pillar definitions (assign each entity to exactly one):
{guide}

Message: "{text}"

Return ONLY a JSON object with what you are 100% confident about.
Use empty string/list if not found. Do NOT infer or guess.

{{
  "name": "user's own name if they said it (not Nancy's name)",
  "family_members": [
    {{"relation": "son/daughter/husband/wife/grandson/granddaughter", "name": "", "location": ""}}
  ],
  "location": "city/place user mentioned as their own location",
  "occupation": "past or current job if explicitly mentioned",
  "interests": ["specific interest/hobby mentioned"],
  "wants_to": ["specific goal/aspiration mentioned"],
  "entities": [
    {{"name": "canonical ENGLISH name for the thing", "surface_form": "exactly as the user wrote it, in their own language", "type": "person|artist|hobby|health|place|food|media|other", "pillar": "{pillar_options}", "sentiment": "positive|negative|neutral", "action": "what they did with it or what happened to it, one verb"}}
  ]
}}

For "entities": extract the THING itself, never the whole sentence.
{known_block}

"name" MUST be a canonical English key, so the same real thing always produces
the same string and repeat mentions accumulate:
- lowercase common nouns, singular, no articles ("knee pain", "bollywood song")
- translate common nouns to English ("ghutne ka dard" -> "knee pain")
- do NOT translate proper nouns or cultural terms — transliterate consistently
  ("Kishore Kumar", "Kedarnath", "puja", "roza", "tiffin")
"surface_form" keeps their original words verbatim.
"sentiment" is how THEY feel about it, not the mood of the message. "I don't
enjoy these songs" is negative about the songs. A complaint about pain is
negative. Merely mentioning something factually is neutral.

"I watched an old Kishore Kumar concert" -> [{{"name": "Kishore Kumar", "surface_form": "Kishore Kumar", "type": "artist", "pillar": "ENTERTAINMENT"}}]
"Ghutne mein bahut dard hai" -> [{{"name": "knee pain", "surface_form": "ghutne mein dard", "type": "health", "pillar": "HEALTH_WELLNESS"}}]
Each entity gets its OWN pillar. One message can contain entities from different pillars.
Return an empty list if the message mentions nothing specific.

Return ONLY the JSON."""

    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        resp   = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=prompt,
        )
        raw  = (resp.text or "").strip()
        raw  = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw) if raw else {}
    except Exception as e:
        # Loud on purpose. This returning {} silently made a total extraction
        # outage look like "nothing found" — the model had been retired for
        # over a week before anyone noticed.
        print(f"!!! [ProfileEnricher] EXTRACTION FAILED — no entities, no profile "
              f"enrichment will happen. Error: {e}")
        return {}


def _should_run_haiku(classified) -> tuple:
    """
    Decide if Haiku extraction is worth running.
    Returns (should_run, context_hint)
    Only runs for HIGH/MEDIUM priority signals with specific pillars.
    """
    core    = classified.core
    emotion = classified.emotion
    cp      = classified.core_priority
    ep      = classified.emotion_priority

    # High value extractions
    if core in ("CAREER_GOAL", "ASPIRATIONS") and cp in ("HIGH", "MEDIUM"):
        return True, "user talking about their work history or life goals"

    if emotion in ("LOVE", "JOY") and ep in ("HIGH", "MEDIUM"):
        return True, "user expressing love or happiness about family/people"

    if emotion == "SADNESS" and ep == "HIGH":
        return True, "user feeling lonely or missing someone"

    if core == "ENTERTAINMENT" and cp in ("HIGH", "MEDIUM"):
        return True, "user talking about hobbies or entertainment interests"

    if core == "HEALTH_WELLNESS" and cp in ("HIGH", "MEDIUM"):
        return True, "user talking about their health, symptoms or treatment"

    if core == "FINANCE" and cp in ("HIGH", "MEDIUM"):
        return True, "user talking about money, expenses or financial worries"

    # Anything the classifier rated HIGH is worth extracting from, whatever the
    # pillar. Extraction runs on the free tier now, so a narrow gate costs more
    # in missed signal than it saves in calls.
    if cp == "HIGH" or ep == "HIGH":
        return True, "high-signal message"

    return False, ""


# ── Classification-driven extractors ──────────────────────────────────────────

def _health_from_classification(classified) -> dict:
    """
    Extract health profile purely from classification.
    The matrix already has structured health info.
    """
    if classified.core not in ("HEALTH_WELLNESS", "FEAR"):
        return {}
    if classified.core_priority not in ("HIGH", "MEDIUM"):
        return {}

    health  = {"conditions": [], "concerns": []}
    matrix  = classified.core_matrix or {}
    score   = classified.core_score

    action   = matrix.get("ACTION",  {}).get("primary", "")
    context  = matrix.get("CONTEXT", {}).get("primary", "")
    modifier = matrix.get("ACTION",  {}).get("modifier", "")

    if "pain" in action or "hurt" in action or "ache" in action:
        if score >= 0.82:
            health["conditions"].append("pain/physical discomfort (HIGH confidence)")
        else:
            health["conditions"].append("pain/physical discomfort (MEDIUM confidence)")

    if "problem" in action or "bimari" in action:
        health["conditions"].append("health issue reported")

    if "suffering" in context or "urgent" in context:
        health["concerns"].append("urgent health concern")
    elif "concern" in context:
        health["concerns"].append("health concern")

    if "chronic" in modifier or "since long" in modifier:
        health["concerns"].append("possibly chronic")

    return {k: list(set(v)) for k, v in health.items() if v}


def _emotion_from_classification(classified) -> dict:
    """Extract emotional state purely from classification."""
    if classified.emotion_priority not in ("HIGH", "MEDIUM"):
        return {}

    emotion_map = {
        "SADNESS":  "feeling lonely/sad",
        "FEAR":     "anxious/worried",
        "STRESS":   "stressed/overwhelmed",
        "JOY":      "happy/cheerful",
        "OPTIMISM": "positive/hopeful",
        "ANGER":    "frustrated/upset",
        "LOVE":     "warm/affectionate",
    }
    state = emotion_map.get(classified.emotion, "")
    if not state:
        return {}

    style = "Hinglish" if classified.language == "hi" else "English"
    return {
        "emotional_state":      state,
        "communication_style":  style,
    }


def _living_situation_from_classification(classified) -> dict:
    """
    Infer living situation from emotion matrix context.
    SADNESS + isolation context → likely lives alone.
    """
    if classified.emotion not in ("SADNESS", "FEAR"):
        return {}

    context = classified.emotion_matrix.get("CONTEXT", {}).get("primary", "") \
              if classified.emotion_matrix else ""

    if "isolation" in context or "no visitors" in context or "empty house" in context:
        return {"living_situation": "possibly lives alone (inferred from emotional context)"}

    return {}


# ── Merge Haiku output into profile structure ──────────────────────────────────

def _merge_haiku_output(extracted: dict, user_id: str) -> dict:
    """Convert Haiku extraction into profile field structure."""
    updates = {}

    if extracted.get("name"):
        updates["name"] = extracted["name"]

    if extracted.get("location"):
        updates["location"] = extracted["location"]

    if extracted.get("occupation"):
        updates["life_context"] = {"occupation": extracted["occupation"]}

    family_members = extracted.get("family_members", [])
    if family_members:
        family = {"children": [], "grandchildren": [], "spouse": "", "other": []}
        for m in family_members:
            relation = m.get("relation", "").lower()
            name     = m.get("name", "")
            location = m.get("location", "")
            desc     = f"{name}{' in ' + location if location else ''}".strip() or relation

            if relation in ("son", "daughter"):
                family["children"].append(desc)
            elif relation in ("grandson", "granddaughter", "grandchild"):
                family["grandchildren"].append(desc)
            elif relation in ("husband", "wife", "spouse"):
                family["spouse"] = desc
            else:
                family["other"].append(desc)

        updates["family"] = {k: v for k, v in family.items() if v}

    interests_list = extracted.get("interests", [])
    if interests_list:
        # Only add to interests after 3+ mentions (threshold check)
        try:
            from supabase_store import get_client
            db = get_client()
            for interest in interests_list:
                # Check how many times this interest has been mentioned
                count = db.table("user_behavioral_events")                    .select("id", count="exact")                    .eq("user_id", user_id)                    .ilike("value", f"%{interest[:20]}%")                    .execute()
                mention_count = count.count or 0
                if mention_count >= 3:
                    # Strong interest — add to profile
                    existing = updates.get("interests", {})
                    hobbies = existing.get("hobbies", [])
                    if interest not in hobbies:
                        hobbies.append(interest)
                    updates["interests"] = {"hobbies": hobbies}
                    print(f"[Enricher] Interest promoted: {interest} ({mention_count} mentions)")
                else:
                    print(f"[Enricher] Interest weak ({mention_count}/3): {interest} — not added yet")
        except Exception as e:
            print(f"[Enricher] Interest threshold check failed: {e}")
            # Fallback: still add if extraction is very confident
            if len(interests_list) > 0:
                updates["interests"] = {"hobbies": interests_list}

    goals = extracted.get("wants_to", [])
    if goals:
        updates["life_context"] = updates.get("life_context", {})
        updates["life_context"]["notable_events"] = goals

    return updates


# ── Main enricher ──────────────────────────────────────────────────────────────

def enrich_profile_from_message(text: str, classified, user_id: str):
    """
    Called after every user message. Zero pattern matching.

    Path 1: Classification-driven (always runs, free)
      → health conditions from HEALTH_WELLNESS classification
      → emotional state from emotion pillar
      → living situation inferred from emotion matrix context
      → language preference from classified.language

    Path 2: Haiku micro-extraction (runs only when worthwhile)
      → named entities: name, family members, location, occupation, interests
      → only for HIGH/MEDIUM priority on specific pillars
    """
    if not user_id:
        return

    priorities = {
        classified.core_priority,
        classified.emotion_priority,
        classified.functional_priority,
    }
    if priorities == {"LOW"}:
        return

    updates = {}

    # ── Path 1: Classification-driven ─────────────────────────────────────────
    health = _health_from_classification(classified)
    if health:
        updates["health"] = health

    personality = _emotion_from_classification(classified)
    if personality:
        updates["personality"] = personality

    living = _living_situation_from_classification(classified)
    if living:
        updates["life_context"] = living

    if classified.language == "hi":
        updates["language_pref"] = "hinglish"

    # ── Path 2: Haiku micro-extraction ────────────────────────────────────────
    should_run, context_hint = _should_run_haiku(classified)
    if should_run:
        extracted = _haiku_extract(text, context_hint, user_id)
        if extracted:
            # Raw interest signal for the recommendation engine
            record_entity_events(extracted.get("entities", []), classified, user_id)
            haiku_updates = _merge_haiku_output(extracted, user_id)
            # Deep merge haiku updates into updates
            for key, val in haiku_updates.items():
                if key in updates and isinstance(updates[key], dict) and isinstance(val, dict):
                    updates[key].update(val)
                else:
                    updates[key] = val

    # ── Path 3: Demographics extraction ──────────────────────────────────────
    if _should_extract_demographics(classified, text):
        demographics = _extract_demographics_from_haiku(text, classified)
        if demographics:
            updates["demographics"] = demographics

    # ── Path 4: Cultural context extraction ───────────────────────────────────
    if _should_extract_cultural(classified, text):
        cultural = _extract_cultural_context_from_haiku(text)
        if cultural:
            updates["cultural_context"] = cultural

    # ── Path 5: Location detection ───────────────────────────────────────────
    try:
        from memory.location_engine import process_location_from_message
        process_location_from_message(text, classified, user_id)
    except Exception as e:
        print(f"[LocationEngine] {e}")

    # ── Save ──────────────────────────────────────────────────────────────────
    if updates:
        try:
            from memory.profile_store import save_user_profile
            save_user_profile(user_id, updates)
            haiku_ran = "+ Haiku" if should_run else ""
            print(f"[ProfileEnricher] Updated {list(updates.keys())} {haiku_ran} for {user_id}")
        except Exception as e:
            print(f"[ProfileEnricher] Save failed: {e}")


# ── Demographics extractor ─────────────────────────────────────────────────────

def _extract_demographics_from_haiku(text: str, classified) -> dict:
    """
    Extract demographics via Haiku — gender, age, marital status, diet.
    Only fires on HIGH/MEDIUM signals.
    """
    import os, json, anthropic

    prompt = f"""Extract demographic information from this message ONLY if explicitly stated.
Return ONLY a JSON object. Use empty string if not found. Do NOT guess.

Message: "{text}"

{{
  "age": null,
  "gender": "",
  "marital_status": "",
  "diet": ""
}}

Rules:
- age: number only if explicitly stated (e.g. "main 67 saal ki hoon" → 67)
- gender: "male"/"female" only if clear from pronouns or name context
- marital_status: "married"/"widowed"/"single"/"divorced" only if mentioned
- diet: "vegetarian"/"non-vegetarian"/"vegan" only if mentioned

Return ONLY the JSON."""

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp   = client.messages.create(
            model      = "claude-haiku-4-5",
            max_tokens = 150,
            messages   = [{"role": "user", "content": prompt}]
        )
        raw  = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        return {k: v for k, v in data.items() if v}
    except Exception as e:
        print(f"[ProfileEnricher] Demographics extraction failed: {e}")
        return {}


def _extract_cultural_context_from_haiku(text: str) -> dict:
    """
    Extract religion, practices, festivals, region from text.
    """
    import os, json, anthropic

    prompt = f"""Extract cultural/religious information from this message ONLY if explicitly mentioned.
Return ONLY a JSON object. Use empty lists/strings if not found.

Message: "{text}"

{{
  "religion": "",
  "practices": [],
  "festivals": [],
  "region": ""
}}

Rules:
- religion: "Hindu"/"Muslim"/"Sikh"/"Christian"/"Jain"/"Buddhist" only if clear
- practices: list of religious practices mentioned (e.g. "morning puja", "namaz", "fasting")
- festivals: list of festivals mentioned (e.g. "Diwali", "Eid", "Navratri")
- region: state/region if mentioned (e.g. "Gujarat", "Punjab", "Tamil Nadu")

Return ONLY the JSON."""

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp   = client.messages.create(
            model      = "claude-haiku-4-5",
            max_tokens = 150,
            messages   = [{"role": "user", "content": prompt}]
        )
        raw  = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        return {k: v for k, v in data.items() if v}
    except Exception as e:
        print(f"[ProfileEnricher] Cultural extraction failed: {e}")
        return {}


def _should_extract_demographics(classified, text: str) -> bool:
    """Check if message likely contains demographic info."""
    t = text.lower()
    age_signals      = ["saal", "year", "old", "age", "born", "umar"]
    gender_signals   = ["main hoon", "mai hoon", "i am", "myself"]
    diet_signals     = ["vegetarian", "veg", "non-veg", "fasting", "upvas"]
    marital_signals  = ["husband", "wife", "pati", "patni", "widow", "widower", "divorced"]
    return any(s in t for s in age_signals + gender_signals + diet_signals + marital_signals)


def _should_extract_cultural(classified, text: str) -> bool:
    """Check if message likely contains cultural/religious info."""
    t = text.lower()
    religion_signals = ["mandir", "masjid", "gurudwara", "church", "temple", "mosque",
                        "puja", "namaz", "prayer", "pooja", "aarti", "bhajan",
                        "diwali", "eid", "navratri", "holi", "christmas", "vaisakhi",
                        "fasting", "upvas", "roza", "ekadashi", "ramadan",
                        "hindu", "muslim", "sikh", "christian", "jain",
                        "pandit", "maulvi", "granthi"]
    return any(s in t for s in religion_signals)


# ── Behavioural events (interest signal for recommendations) ───────────────────

def _upsert_cluster(user_id: str, label: str, pillar: str, strength: float) -> str:
    """
    Ensure a persistent cluster exists for this concern and return its id.

    The cluster is the ONGOING thing ("blood pressure"); the events are its
    dated timeline. Create on first mention, otherwise bump the running totals.
    Strength is summed raw here — recency decay is applied at read time so the
    curve stays retunable without a backfill.
    """
    try:
        from supabase_store import get_client
        db = get_client()

        existing = (db.table("interest_clusters")
                    .select("id,event_count,strength")
                    .eq("user_id", user_id)
                    .eq("label", label)
                    .limit(1)
                    .execute()).data

        if existing:
            row = existing[0]
            db.table("interest_clusters").update({
                "event_count": (row.get("event_count") or 0) + 1,
                "strength":    round((row.get("strength") or 0) + strength, 4),
                "last_event":  "now()",
                "status":      "active",   # any fresh mention reactivates it
            }).eq("id", row["id"]).execute()
            return row["id"]

        created = (db.table("interest_clusters").insert({
            "user_id":     user_id,
            "label":       label,
            "pillar":      pillar,
            "strength":    round(strength, 4),
            "event_count": 1,
        }).execute()).data
        return created[0]["id"] if created else None

    except Exception as e:
        print(f"[Cluster] upsert failed for {label!r}: {e}")
        return None


def record_entity_events(entities: list, classified, user_id: str, session_id: str = ""):
    """
    Write one row per extracted entity to user_behavioral_events.

    This is the raw signal the recommendation engine ranks on. We store the
    entity itself ("Kishore Kumar"), never the whole sentence, so rows are
    countable. Scoring — frequency, recency decay — happens at read time, so
    the decay curve can be retuned later without losing history.
    """
    if not entities or not user_id:
        return

    try:
        from supabase_store import get_client
        db = get_client()

        rows = []
        from memory.entity_resolver import resolve

        for ent in entities:
            name = (ent.get("name") or "").strip()
            if not name or len(name) > 100:
                continue

            ent_type = (ent.get("type") or "other")[:40]
            pillar   = (ent.get("pillar") or classified.core)

            # Reuse an existing name if this is the same thing said differently,
            # so repeat mentions accumulate instead of fragmenting.
            res = resolve(name, ent_type, pillar, user_id)

            ev_strength = round(float(classified.core_score or 0.5), 4)
            cluster_id  = _upsert_cluster(user_id, res["name"], pillar, ev_strength)

            rows.append({
                "user_id":      user_id,
                "cluster_id":   cluster_id,
                "session_id":   session_id or None,
                "pillar":       pillar,
                "sub_pillar":   ent_type,
                "value":        res["name"],                    # canonical key
                "surface_form": (ent.get("surface_form") or name)[:200],
                "strength":     round(float(classified.core_score or 0.5), 4),
                # Column is numeric — store the signed weight, not the label.
                # Negative mentions must SUBTRACT from interest or the engine
                # confidently recommends things people said they dislike.
                "sentiment":    {"positive": 1.0, "negative": -0.6}.get(
                                    (ent.get("sentiment") or "").lower(), 0.5),
                "event_type":   (ent.get("action") or "mentioned")[:40],
                "embedding":    res.get("embedding"),
            })

        if rows:
            db.table("user_behavioral_events").insert(rows).execute()
            print(f"[Events] {len(rows)} entity events for {user_id}: "
                  f"{[r['value'] for r in rows]}")

    except Exception as e:
        print(f"[Events] Failed to record entities: {e}")

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
                    "ASPIRATIONS", "ENTERTAINMENT", "FAMILY", "GENERAL"]
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
    {{"name": "canonical ENGLISH name for the thing", "surface_form": "exactly as the user wrote it, in their own language", "type": "person|artist|hobby|health|place|food|media|other", "pillar": "{pillar_options}", "sentiment": "positive|negative|neutral", "salience": "0.0-1.0, how much this matters to them right now — pain and money worries are high, casual mentions low", "action": "what they did with it or what happened to it, one verb", "relationship_type": "concern|preference|person|routine|possession|aspiration — what KIND of thing this is to them", "attributes": {{"relationship": "son/daughter/husband/wife/etc IF a family member", "location": "city/place they live IF mentioned", "occupation": "their job IF mentioned"}} }}
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
"My son Rohan lives in Delhi and works as a teacher" -> [{{"name": "Rohan", "surface_form": "Rohan", "type": "person", "pillar": "FAMILY", "relationship_type": "person", "action": "mentioned", "attributes": {{"relationship": "son", "location": "Delhi", "occupation": "teacher"}} }}]
IMPORTANT: when a PERSON is described with where they live, their job, or their relationship, attach those as "attributes" of that person — do NOT emit the city or job as separate entities. The person is the anchor; their facts hang off them. So "Delhi" here is Rohan's attribute, not its own entity.
FAMILY is for the person's relatives and loved ones — son, daughter, husband, wife, mother, father, beta, beti, brother, sister, grandchildren, and named family members. Use FAMILY (not GENERAL or ASPIRATIONS) whenever a family relationship is mentioned.
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

    # SELF-DISCLOSURE — user telling us durable facts about themselves. These
    # accumulate the person's profile (the core value of a companion), so extract
    # at ANY priority, including calm/LOW. "My son lives in Delhi" or "I do puja
    # every morning" are quiet but essential to remember.
    if core in ("FAMILY", "HEALTH_WELLNESS", "ENTERTAINMENT", "CAREER_GOAL",
                "ASPIRATIONS", "FINANCE"):
        return True, "user sharing durable personal information about themselves"

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

    # Interest storage is now owned by the proposition pipeline
    # (record_propositions): every interest becomes a cluster with strength
    # scaled by the LLM's salience classification — a stated passion surfaces
    # immediately, a passing mention accumulates over time. The old "3 mentions
    # before adding" gate is removed; it dropped single-mention interests.
    goals = extracted.get("wants_to", [])
    if goals:
        updates["life_context"] = updates.get("life_context", {})
        updates["life_context"]["notable_events"] = goals

    return updates


# ── Main enricher ──────────────────────────────────────────────────────────────

def enrich_profile_from_message(text: str, classified, user_id: str, session_id: str = ""):
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

    try:
        from memory.profile_store import ensure_profile_exists
        ensure_profile_exists(user_id)
    except Exception as e:
        print(f"[ProfileEnricher] ensure_profile: {e}")

    priorities = {
        classified.core_priority,
        classified.emotion_priority,
        classified.functional_priority,
    }
    # Don't bail on all-LOW if the message is self-disclosure — the user calmly
    # telling us about their family, health, habits or interests is durable info
    # worth accumulating even when it carries no emotional urgency.
    _SELF_DISCLOSURE = {"FAMILY", "HEALTH_WELLNESS", "ENTERTAINMENT",
                        "CAREER_GOAL", "ASPIRATIONS", "FINANCE"}
    if priorities == {"LOW"} and classified.core not in _SELF_DISCLOSURE:
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
        # NEW: proposition-based extraction for clusters/events (subject-relation-
        # object with correction-detection, coreference, pillar-by-type). Replaces
        # the old entity path for cluster storage. Old _haiku_extract still runs
        # below for profile-field merge (name/health/language) until that migrates.
        try:
            props = _extract_propositions(text, user_id)
            if props:
                record_propositions(props, classified, user_id, session_id)
        except Exception as e:
            print(f"[Propositions] live path failed, falling back: {e}")

        extracted = _haiku_extract(text, context_hint, user_id)
        if extracted:
            # (cluster storage now handled by record_propositions above)
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

def derive_trajectory(events: list) -> dict:
    """Given a cluster's time-ordered events (oldest first), derive its rollup:
    current_state (recency-weighted sentiment), trend (direction), and the last
    state/sentiment. This turns a series of revisits into a living trajectory —
    e.g. BP mentioned as 'swell, swell, improved' -> trend='improving'."""
    if not events:
        return {}
    sents = [float(e.get("sentiment") or 0) for e in events]
    n = len(sents)
    weights = [i + 1 for i in range(n)]              # newest weighted highest
    current = round(sum(s * w for s, w in zip(sents, weights)) / sum(weights), 3)
    if n >= 2:
        mid = n // 2
        earlier = sum(sents[:mid]) / max(mid, 1)
        recent  = sum(sents[mid:]) / max(n - mid, 1)
        delta = recent - earlier
        trend = "improving" if delta > 0.3 else ("worsening" if delta < -0.3 else "stable")
    else:
        trend = "new"
    # dominant relationship_type across events, if present
    rels = [e.get("relationship_type") for e in events if e.get("relationship_type")]
    relationship = max(set(rels), key=rels.count) if rels else None
    return {
        "current_state":  current,
        "trend":          trend,
        "relationship":   relationship,
        "last_state":     events[-1].get("event_type"),
        "last_sentiment": sents[-1],
    }


def recompute_cluster_trajectory(user_id: str, cluster_id: str):
    """Recompute and store a cluster's trajectory rollup from its events.
    Called after each new event lands, so recall/engine read a current trend
    cheaply without recomputing."""
    if not cluster_id:
        return
    try:
        from supabase_store import get_client
        db = get_client()
        # Trend only makes sense for things with a health/finance trajectory —
        # a person (FAMILY) or an interest doesn't "improve" or "worsen". Check
        # the cluster's pillar and skip trend for non-trajectory pillars.
        crow = (db.table("interest_clusters").select("pillar")
                .eq("id", cluster_id).limit(1).execute()).data
        pillar = crow[0].get("pillar") if crow else None
        if pillar not in ("HEALTH_WELLNESS", "FINANCE"):
            return

        evs = (db.table("user_behavioral_events")
               .select("sentiment,event_type,relationship_type,created_at")
               .eq("cluster_id", cluster_id).order("created_at", desc=False)
               .execute()).data or []
        roll = derive_trajectory(evs)
        if roll:
            db.table("interest_clusters").update(roll).eq("id", cluster_id).execute()
    except Exception as e:
        print(f"[Trajectory] recompute failed for {cluster_id}: {e}")


def _upsert_cluster(user_id: str, label: str, pillar: str,
                    strength: float, embedding: list = None,
                    attributes: dict = None) -> str:
    """
    Attach this event to the ongoing concern it belongs to, or start a new one.

    Matching is by CENTROID, not label string: "amlodipine", "blood pressure"
    and "BP medication" are different labels for one concern, so exact-label
    matching would fragment them. find_cluster embeds-and-adjudicates to pick
    the right cluster; here we just maintain its running totals and centroid.

    Strength sums raw (decay applied at read time). The centroid is the running
    mean of its members, so it settles between related labels rather than
    anchoring on whichever was said first.
    """
    try:
        from supabase_store import get_client
        from memory.cluster_resolver import find_cluster
        db = get_client()

        cluster_id = find_cluster(user_id, label, pillar, embedding)

        if cluster_id:
            row = (db.table("interest_clusters")
                   .select("event_count,strength,centroid,attributes")
                   .eq("id", cluster_id).limit(1).execute()).data
            row = row[0] if row else {}
            n   = row.get("event_count") or 0

            update = {
                "event_count": n + 1,
                "strength":    round((row.get("strength") or 0) + strength, 4),
                "last_event":  "now()",
                "status":      "active",
            }

            # Running-mean centroid: (old*n + new) / (n+1)
            old_cen = row.get("centroid")
            if isinstance(old_cen, str):
                import json as _j
                try: old_cen = _j.loads(old_cen)
                except Exception: old_cen = None
            if embedding and old_cen and len(old_cen) == len(embedding):
                update["centroid"] = [
                    round((o * n + e) / (n + 1), 6)
                    for o, e in zip(old_cen, embedding)
                ]

            if attributes:
                existing_attrs = row.get("attributes") or {}
                if isinstance(existing_attrs, str):
                    import json as _j2
                    try: existing_attrs = _j2.loads(existing_attrs)
                    except Exception: existing_attrs = {}
                merged = {**existing_attrs, **{k: v for k, v in attributes.items() if v}}
                if merged:
                    update["attributes"] = merged
            db.table("interest_clusters").update(update).eq("id", cluster_id).execute()
            try:
                from memory.cluster_resolver import reconcile
                cluster_id = reconcile(user_id, cluster_id, pillar) or cluster_id
            except Exception as e:
                print(f"[Cluster] reconcile failed: {e}")
            return cluster_id

        # Exact-label safety net: find_cluster scopes by pillar + centroid, but the
        # unique constraint is (user_id, label) across ALL pillars. If a cluster
        # with this exact label already exists (e.g. stored under a different
        # pillar earlier), UPDATE it instead of inserting — avoids the dup-key
        # collision AND heals stale pillars (Vikram GENERAL -> FAMILY on re-mention).
        try:
            dupe = (db.table("interest_clusters").select("id,strength,event_count,attributes")
                    .eq("user_id", user_id).eq("label", label).limit(1).execute()).data
        except Exception:
            dupe = None
        if dupe:
            d = dupe[0]
            merged_attrs = d.get("attributes") or {}
            if isinstance(merged_attrs, str):
                try: merged_attrs = json.loads(merged_attrs)
                except Exception: merged_attrs = {}
            merged_attrs.update({k: v for k, v in (attributes or {}).items() if v})
            db.table("interest_clusters").update({
                "strength":    round((d.get("strength") or 0) + strength, 4),
                "event_count": (d.get("event_count") or 0) + 1,
                "pillar":      pillar,
                "last_event":  "now()",
                "status":      "active",
                "attributes":  merged_attrs,
            }).eq("id", d["id"]).execute()
            return d["id"]

        created = (db.table("interest_clusters").insert({
            "user_id":     user_id,
            "label":       label,
            "pillar":      pillar,
            "strength":    round(strength, 4),
            "event_count": 1,
            "centroid":    embedding,
            "attributes":  {k: v for k, v in (attributes or {}).items() if v} or {},
        }).execute()).data
        new_id = created[0]["id"] if created else None
        if new_id:
            try:
                from memory.cluster_resolver import reconcile
                new_id = reconcile(user_id, new_id, pillar) or new_id
            except Exception as e:
                print(f"[Cluster] reconcile failed: {e}")
        return new_id

    except Exception as e:
        print(f"[Cluster] upsert failed for {label!r}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════
# PROPOSITION EXTRACTION (new) — LLM returns subject-relation-object facts with
# correction-detection and coreference. Processor below turns them into cluster
# operations: pillar-by-type, weighted corrections, subject-grouped attributes.
# ══════════════════════════════════════════════════════════════════════════

# entity_type -> pillar, deterministic (don't trust the LLM's pillar field; it
# leaks context, e.g. tea near health talk -> HEALTH. type is reliable, so map it.)
_TYPE_TO_PILLAR = {
    "person": "FAMILY", "food": "GENERAL", "health": "HEALTH_WELLNESS",
    "hobby": "ASPIRATIONS", "artist": "ENTERTAINMENT", "media": "ENTERTAINMENT",
    "place": "GENERAL", "belief": "GENERAL", "other": "GENERAL",
}

def _extract_propositions(text: str, user_id: str = "") -> list:
    """Extract subject-relation-object propositions. Feeds known entities back in
    so pronouns/roles ('beta','he') resolve to the named person (coreference)."""
    known = _known_entities(user_id)
    known_block = ("\nPeople/things already known about this person:\n"
                   + "\n".join(f"- {k}" for k in known)
                   + "\nUse these names ONLY to resolve a pronoun or role that clearly "
                     "refers to one of them ('he'/'beta' -> the known son). NEVER make "
                     "a known name the subject of a statement that is not about them. "
                     "'I love Lata' is about the USER (subject=self), NOT about any "
                     "known person. When unsure, keep the natural subject.") if known else ""

    prompt = f'''You extract PROPOSITIONS (subject-relation-object facts) from an elderly person's message, including Hindi/Hinglish.{known_block}

For EACH fact return an object:
- subject: canonical name (translate common nouns to English: "ghutne ka dard"->"knee pain"; keep proper nouns transliterated: "Vikram")
- subject_ref: proper_name | son | daughter | husband | wife | grandchild | mother | father | pronoun | self
- relation: likes | stopped_liking | lives_in | works_as | is | has_condition | feels | did
- object: canonical target ("Amreeka"->"America") or null
- entity_type: person | food | health | hobby | artist | media | place | belief | other
- sentiment: positive | negative | neutral
- salience: 0.0-1.0 (pain, money, family worries high; casual mentions low)
- is_correction: true if the message CHANGES/RETRACTS a prior fact. Triggers: switched, gave up, "no wait", actually, "I meant", "prefer X now", "not X anymore"
- replaces: the prior thing overridden ("coffee") or null
- attributes: for people only {{"relationship":"son/daughter/etc","location":"city","occupation":"job"}}

RULES:
- Different relationships (son AND daughter) are DIFFERENT subjects — NEVER merge them.
- A role/pronoun ("beta","my boy","he") referring to an already-known person uses that PERSON'S proper name as subject.
- Do NOT emit a person's location/job as a separate place/thing — put it in their attributes.

Return ONLY a JSON array. Message:
"{text}"'''

    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        resp = client.models.generate_content(
            model="gemini-flash-lite-latest", contents=prompt)
        raw = (resp.text or "").strip().replace("```json", "").replace("```", "").strip()
        props = json.loads(raw) if raw else []
        return props if isinstance(props, list) else []
    except Exception as e:
        print(f"!!! [Propositions] EXTRACTION FAILED: {e}")
        return []


def record_propositions(props: list, classified, user_id: str, session_id: str = "") -> dict:
    """Turn propositions into cluster operations:
    - pillar from entity_type (deterministic)
    - group by subject so one person's facts merge into one cluster + attributes
    - corrections: fade the replaced cluster (weighted x0.3), let new dominate
    - reuse _upsert_cluster (anchoring) + recompute trajectory."""
    if not props or not user_id:
        return {}
    try:
        from supabase_store import get_client
        from memory.entity_resolver import resolve
        db = get_client()

        # Group propositions by the ENTITY TO REMEMBER.
        # For "I love coffee", subject is "self" but the thing to cluster is the
        # OBJECT (coffee). For "Vikram lives in America", the subject (Vikram) is
        # the entity. So: if subject is self/the user, cluster the object; else
        # cluster the subject. Pure feelings with no object (self feels lonely)
        # have nothing to cluster and are skipped.
        by_subject = {}
        for pr in props:
            subj = (pr.get("subject") or "").strip()
            obj = (pr.get("object") or "").strip()
            ref = (pr.get("subject_ref") or "").strip().lower()
            # Trust subject_ref over subject. The known-entities hint sometimes makes
            # the LLM wrongly stuff a known name into `subject` while still (correctly)
            # marking subject_ref="self" — e.g. "I love Lata" -> subject=Arjun,
            # ref=self, object=Lata. When ref says self, the statement is the USER's
            # and the thing to remember is the OBJECT, no matter what's in subject.
            if ref in ("self", "user", "i", "me") or subj.lower() in ("self", "user", "i", "me", ""):
                key = obj                      # cluster the thing they mentioned
            else:
                key = subj                     # cluster the named entity
            if not key or key.lower() in ("self", "user"):
                continue                       # nothing concrete to remember
            by_subject.setdefault(key, []).append(pr)

        affected_clusters = []
        for subj, subj_props in by_subject.items():
            first = subj_props[0]
            etype = (first.get("entity_type") or "other").lower()

            # merge attributes across all of this subject's props
            attrs = {}
            for pr in subj_props:
                a = pr.get("attributes") or {}
                if isinstance(a, dict):
                    attrs.update({k: v for k, v in a.items() if v})

            # A person WITH a family relationship is FAMILY regardless of type
            # ("Vikram lives_in America" arrives as type=place, but he is her son).
            if attrs.get("relationship") or any(
                    pr.get("subject_ref") in ("son","daughter","husband","wife",
                                              "grandchild","mother","father")
                    for pr in subj_props):
                pillar = "FAMILY"
            else:
                pillar = _TYPE_TO_PILLAR.get(etype, "GENERAL")

            # sentiment/salience/relation from the strongest prop
            sent_word = first.get("sentiment", "neutral")
            sentiment = {"positive": 1.0, "negative": -0.6}.get(sent_word, 0.5)
            salience = _safe_salience(first.get("salience"))
            relation = first.get("relation") or "mentioned"

            # CORRECTION: fade ONLY what the LLM explicitly identified as replaced,
            # and ONLY if it actually exists. We do NOT guess a target — a
            # correction that doesn't resolve to a real cluster is left alone
            # (recency lets the new preference dominate anyway). Failing safe here
            # means we never fade the wrong memory; the worst case is a stale old
            # preference lingering slightly, which is recoverable. Guessing is not.
            for pr in subj_props:
                if not (pr.get("is_correction") and pr.get("replaces")):
                    continue
                repl = str(pr["replaces"]).strip()
                if not repl or repl.lower() == key.lower():
                    continue
                try:
                    old_c = (db.table("interest_clusters").select("id,strength,label")
                             .eq("user_id", user_id).ilike("label", f"%{repl}%")
                             .limit(1).execute()).data
                    if old_c:                       # validated: it exists
                        new_str = round((old_c[0].get("strength") or 0) * 0.3, 4)
                        db.table("interest_clusters").update(
                            {"strength": new_str}).eq("id", old_c[0]["id"]).execute()
                        print(f"[Prop] correction faded '{old_c[0]['label']}' -> {new_str}")
                    else:
                        print(f"[Prop] correction target '{repl}' not found — left alone")
                except Exception as e:
                    print(f"[Prop] fade failed: {e}")

            # If this subject is itself being GIVEN UP (relation stopped_liking),
            # don't upsert it as a fresh interest — that would re-add strength and
            # cancel the fade. The negative signal is already applied above.
            if any(pr.get("relation") == "stopped_liking" for pr in subj_props):
                print(f"[Prop] '{subj}' retracted — fading, not re-adding")
                try:
                    gone = (db.table("interest_clusters").select("id,strength")
                            .eq("user_id", user_id).ilike("label", f"%{subj}%")
                            .limit(1).execute()).data
                    if gone:
                        faded = round((gone[0].get("strength") or 0) * 0.3, 4)
                        db.table("interest_clusters").update(
                            {"strength": faded}).eq("id", gone[0]["id"]).execute()
                except Exception as e:
                    print(f"[Prop] retract-fade failed: {e}")
                continue

            # resolve + upsert (reuse anchoring path)
            res = resolve(subj, etype, pillar, user_id)
            # Strength scales by the LLM's salience classification: a stated
            # passion ("I love X", salience~0.8) stores strong and surfaces now;
            # a passing mention ("watched some cricket", ~0.3) stores weak and
            # only surfaces if it accumulates over repeated mentions. The LLM
            # judges importance; we just multiply. No thresholds, no verb rules.
            ev_strength = round(float(classified.core_score or 0.5) * max(0.15, salience), 4)
            cluster_id = _upsert_cluster(user_id, res["name"], pillar, ev_strength,
                                         res.get("embedding"), attrs or None)
            if cluster_id:
                affected_clusters.append(cluster_id)
                # one event per subject (the relation is the state verb)
                try:
                    db.table("user_behavioral_events").insert({
                        "user_id": user_id, "cluster_id": cluster_id,
                        "session_id": session_id or None, "pillar": pillar,
                        "sub_pillar": etype, "value": res["name"],
                        "surface_form": subj[:200], "strength": ev_strength,
                        "sentiment": sentiment, "salience": salience,
                        "event_type": relation[:40],
                        "relationship_type": first.get("subject_ref"),
                        "embedding": res.get("embedding"),
                    }).execute()
                except Exception as e:
                    print(f"[Prop] event insert failed: {e}")

        for cid in set(affected_clusters):
            recompute_cluster_trajectory(user_id, cid)

        print(f"[Prop] recorded {len(by_subject)} subjects: {list(by_subject.keys())}")
        return {"subjects": list(by_subject.keys())}
    except Exception as e:
        print(f"[Prop] record failed: {e}")
        return {}


def _safe_salience(v) -> float:
    """Salience should be 0-1, but the model sometimes returns a word. Coerce."""
    words = {"high": 0.9, "medium": 0.5, "low": 0.2, "none": 0.1}
    try:
        return round(min(1.0, max(0.0, float(v))), 4)
    except (TypeError, ValueError):
        return words.get(str(v).strip().lower(), 0.5)


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
            cluster_id  = _upsert_cluster(user_id, res["name"], pillar, ev_strength,
                                          res.get("embedding"), ent.get("attributes"))

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
                "salience":     _safe_salience(ent.get("salience")),
                "event_type":   (ent.get("action") or "mentioned")[:40],
                "relationship_type": (ent.get("relationship_type") or None),
                "embedding":    res.get("embedding"),
            })

        if rows:
            db.table("user_behavioral_events").insert(rows).execute()
            print(f"[Events] {len(rows)} entity events for {user_id}: "
                  f"{[r['value'] for r in rows]}")
            # Refresh each affected cluster's trajectory rollup (trend, current_state)
            for cid in {r.get("cluster_id") for r in rows if r.get("cluster_id")}:
                recompute_cluster_trajectory(user_id, cid)

        sal = [_safe_salience(e.get("salience")) for e in entities] or [0.0]
        top = max(sal)
        salience_priority = "HIGH" if top >= 0.8 else ("MEDIUM" if top >= 0.5 else "LOW")
        return {"salience_priority": salience_priority, "max_salience": round(top, 3)}

    except Exception as e:
        print(f"[Events] Failed to record entities: {e}")

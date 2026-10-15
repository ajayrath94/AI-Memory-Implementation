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
        # Once more. This comes back 555 "JSON could not be generated" from
        # Supabase now and then — transient, not structural, 155 rows and an
        # indexed user_id. But when it fails the extractor runs blind, and the
        # same knee becomes "ghutna" on Monday and "Ghutne mein dard" on
        # Thursday. Both are in her clusters now, from exactly this.
        try:
            import time as _t
            _t.sleep(0.4)
            rows = (get_client().table("user_behavioral_events")
                    .select("value").eq("user_id", user_id)
                    .limit(300).execute()).data or []
            seen = []
            for r in rows:
                v = (r.get("value") or "").strip()
                if v and v not in seen:
                    seen.append(v)
                if len(seen) >= limit:
                    break
            return seen
        except Exception as e2:
            print(f"[ProfileEnricher] known entities unavailable twice: {e2}")
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
    {{"name": "canonical ENGLISH name for the thing", "surface_form": "exactly as the user wrote it, in their own language", "type": "person|artist|music|hobby|health|place|food|media|other", "pillar": "{pillar_options}", "sentiment": "positive|negative|neutral", "salience": "0.0-1.0, how much this matters to them right now — pain and money worries are high, casual mentions low", "action": "what they did with it or what happened to it, one verb", "relationship_type": "concern|preference|person|routine|possession|aspiration — what KIND of thing this is to them", "attributes": {{"relationship": "son/daughter/husband/wife/etc IF a family member", "location": "city/place they live IF mentioned", "occupation": "their job IF mentioned"}} }}
  ]
}}

For "entities": extract the THING itself, never the whole sentence.

"name" is ALWAYS a noun — a person, object, place, or activity-as-noun. NEVER a
verb phrase, action, or feeling. The verb goes in "action", never in "name":
- "bahut yaad aati hai beti ki" (I miss my daughter) -> name: "daughter", action: "misses"  NOT name: "missing daughter"
- "doctor ne dawai di" (doctor gave medicine) -> name: "medicine", action: "prescribed"  NOT name: "was given medicine by doctor"
- "roz gaane sunti hoon" (I listen to songs daily) -> name: "songs" (or the artist), action: "listens daily"  NOT name: "listen to songs daily"
- "main proud feel karti hoon" (I feel proud) -> emit NOTHING; a bare feeling is not a thing to remember
If the person CORRECTS themselves or talks ABOUT the conversation ("maine galti
se kuch aur bola", "let me correct that", "I said the wrong name"), that is meta
about the chat, NOT a durable fact — emit NOTHING for the correction statement
itself (but DO emit the corrected fact, e.g. the right name).
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
        client = __import__("llm").genai_client()
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

    # Language is declared, not inferred. This used to set hinglish whenever
    # the classifier saw Hindi in a message, which is unreliable on its own —
    # a Punjabi speaker writing one Hinglish sentence would be reclassified,
    # and someone may deliberately want English replies while writing in Hindi.
    # It is now set only from the language picker, through the declared path.

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

    # ── Paths 3 + 4: who she is — age, marriage, diet, faith, region ─────────
    # These ran only when the message contained one of a few dozen words
    # ("saal", "pati", "mandir", "puja"), so "tengo 78 años" or "voy a misa"
    # never reached the model at all. One call now reads both, in any
    # language, on every message that got this far.
    facts = _extract_self_facts(text)
    if facts.get("demographics"):
        updates["demographics"] = facts["demographics"]
    if facts.get("cultural_context"):
        updates["cultural_context"] = facts["cultural_context"]

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

def _extract_self_facts(text: str) -> dict:
    """Age, gender, marital status, diet, religion, practices, festivals and
    region — only what the message itself states, in any language.
    {"demographics": {...}, "cultural_context": {...}}, empty when none."""
    import json as _json
    prompt = f"""An elderly person wrote this message, in any language:

"{text}"

Extract ONLY what the message explicitly says about the person who wrote
it. Do not guess. Return JSON only:
{{
 "demographics": {{
   "age": a number if they state their age, else null,
   "gender": "male" or "female" only if clear from how they refer to
             themselves, else "",
   "marital_status": "married" / "widowed" / "single" / "divorced" if said,
   "diet": "vegetarian" / "non-vegetarian" / "vegan" if said
 }},
 "cultural_context": {{
   "religion": their religion in English if clear (e.g. Hindu, Muslim,
               Sikh, Christian, Catholic, Jain, Buddhist, Jewish), else "",
   "practices": religious practices they mention, in English
                (e.g. "morning puja", "Sunday mass", "fasting"),
   "festivals": festivals they mention, by their usual name,
   "region": the state, region or country they say they are from, else ""
 }}
}}
Leave anything not stated empty."""
    try:
        from llm import ask
        raw = ask(prompt, max_tokens=250) or ""
        i, j = raw.find("{"), raw.rfind("}")
        data = _json.loads(raw[i:j + 1]) if i >= 0 else {}
    except Exception as e:
        print(f"[ProfileEnricher] self-facts extraction failed: {e}")
        return {}
    out = {}
    for part in ("demographics", "cultural_context"):
        d = data.get(part) or {}
        if isinstance(d, dict):
            d = {k: v for k, v in d.items() if v}
            if d:
                out[part] = d
    return out


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
        # This used to return early for anything but HEALTH_WELLNESS and
        # FINANCE, on the reasoning that "trend" is meaningless for an artist.
        # True of trend — but it also skipped current_state and relationship,
        # so every interest, person and preference cluster had null sentiment
        # and no segmentation. An event could say relationship_type=preference
        # and the cluster it belonged to would still be unmarked.
        trajectory_pillar = pillar in ("HEALTH_WELLNESS", "FINANCE")

        evs = (db.table("user_behavioral_events")
               .select("sentiment,event_type,relationship_type,created_at")
               .eq("cluster_id", cluster_id).order("created_at", desc=False)
               .execute()).data or []
        roll = derive_trajectory(evs)
        if roll and not trajectory_pillar:
            # An artist does not improve or worsen; a knee does.
            roll.pop("trend", None)
        if roll:
            db.table("interest_clusters").update(roll).eq("id", cluster_id).execute()
    except Exception as e:
        print(f"[Trajectory] recompute failed for {cluster_id}: {e}")


# ── what a label may be ──────────────────────────────────────────────────────
#
# The FAMILY screen showed Shubham six times: "Shubham", "Shubham (son)",
# "Shubham (son, lives in Bangalore)", and Nancy three times as "Nancy
# (appears to be a caregiver/friend)". The extractor had nowhere else to put
# a relation or a doubt, so it put them in the name, and three different
# strings can never be matched as one person. "in Bangalore" became an entity
# with no name at all.
#
# So a label is cleaned before anything looks it up or writes it: what is in
# brackets goes to the attributes, a hedge goes to confidence, and something
# that is not a name is not written.

_HEDGES = ("appears to", "possibly", "probably", "seems", "maybe", "might be",
           "unclear", "unknown", "not sure", "likely")

def _is_relation(part: str) -> bool:
    """Is a bracketed word how someone is related to her — "son", "bahu",
    "hijo", "Nachbarin"? Asked, in any language; remembered per word."""
    try:
        from memory.judge import yes_no
        return yes_no(f'Is "{part}" a word for how a person is related to '
                      f'someone (a family relation, friend, neighbour, '
                      f'carer, doctor and so on), in any language?',
                      key="rel:" + part.lower())
    except Exception:
        return False


def clean_label(label: str, attributes: dict = None):
    """(clean label, attributes) or (None, attributes) if it is not a name."""
    import re as _re
    attrs = dict(attributes or {})
    raw = str(label or "").strip()

    # What is in brackets is about the thing, not its name.
    inside = _re.findall(r"\(([^)]*)\)", raw)
    name = _re.sub(r"\([^)]*\)", " ", raw)
    name = _re.sub(r"\s+", " ", name).strip(" ,.-:;\"'")

    for bit in inside:
        b = bit.strip().lower()
        if not b:
            continue
        if any(h in b for h in _HEDGES):
            # A guess is a guess: lower confidence, never a name.
            attrs.setdefault("confidence", "low")
            attrs.setdefault("note", bit.strip()[:120])
            continue
        parts = [x.strip() for x in _re.split(r"[,;/]", b) if x.strip()]
        for part in parts:
            if not attrs.get("relation") and len(part) <= 30 and _is_relation(part):
                attrs["relation"] = part
            elif part.startswith(("lives in ", "in ", "from ")) and not attrs.get("location"):
                attrs["location"] = part.split(" ", 2)[-1].strip().title()
            else:
                attrs.setdefault("note", bit.strip()[:120])

    low = name.lower()
    # A hedge in the name itself, or nothing that is a name.
    if any(h in low for h in _HEDGES):
        return None, attrs
    if len(name) < 2 or not _re.search(r"[^\W\d_]", name):
        return None, attrs
    # "in Bangalore", "at the temple": a fragment, not a thing.
    if _re.match(r"^(in|at|from|to|of|with|the)\s", low) and \
            (attrs.get("kind") or "") in ("person", ""):
        return None, attrs
    return name[:120], attrs


# Relations that can be the same person mistaken. Son and grandson, daughter
# and granddaughter: a model unsure of the generation guesses, and splitting
# on its guess is what made six Shubhams. A daughter-in-law and a neighbour
# are not a mistake about one person; they stay two. Asked, because the
# relation is kept in her own words — "pota", "nieto", "Enkel".
def _same_person_confusable(a: str, b: str) -> bool:
    try:
        from memory.judge import yes_no
        x, y = sorted([a.lower(), b.lower()])
        return yes_no(f'One person is called "{x}" and, later, "{y}" by the '
                      f'same elderly speaker (relation words, any language). '
                      f'Is one of these a child and the other a grandchild '
                      f'of the speaker — the kind of generation mix-up a '
                      f'listener could make about ONE person?',
                      key=f"gen:{x}|{y}")
    except Exception:
        return False


def _relation_candidates(attrs: dict, rel: str) -> dict:
    """Add one sighting of a relation to the candidates on a person."""
    cands = attrs.get("relation_candidates")
    if not isinstance(cands, dict):
        cands = {}
        if attrs.get("relation"):
            cands[str(attrs["relation"]).lower()] = 1
    r = str(rel).lower()
    cands[r] = cands.get(r, 0) + 1
    attrs["relation_candidates"] = cands
    # Shown: the one said most. Flagged when two are both said.
    attrs["relation"] = max(cands, key=cands.get)
    attrs["needs_review"] = len([c for c in cands.values() if c >= 1]) > 1
    return attrs


def _upsert_cluster(user_id: str, label: str, pillar: str,
                    strength: float, embedding: list = None,
                    attributes: dict = None, resolve_into: bool = True) -> str:
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
    label, attributes = clean_label(label, attributes)
    if not label:
        print(f"[Cluster] not a name, not written: {attributes.get('note') or ''}")
        return None
    try:
        from supabase_store import get_client
        from memory.cluster_resolver import find_cluster
        db = get_client()

        # resolve_into=False for anything a person named deliberately.
        #
        # The resolver exists because conversational mentions are ambiguous:
        # "the knee thing", "ghutne ka dard" and "knee pain" are one ongoing
        # situation phrased three ways, and merging them is the whole point.
        # A form field has no such ambiguity — the text is already canonical
        # because someone typed it on purpose.
        #
        # Asking anyway introduced a failure that could not otherwise exist:
        # "Hum Aapke Hain Koun" was merged into a cluster holding Sholay and
        # Gadar, on the reasoning that a specific film belongs to films. That
        # is true of a cricket match belonging to cricket and false of three
        # named works, which are siblings rather than instances — and it is a
        # subtle enough distinction that relying on it holding, in every
        # domain and nine languages, is worse than not asking.
        cluster_id = (find_cluster(user_id, label, pillar, embedding)
                      if resolve_into else None)

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
                    # The COLUMN too, not only the attribute. Vikram came out
                    # kind=interest in the column and kind=person in his
                    # attributes — two sources of truth for one fact, already
                    # disagreeing. The picker filters on the column, so a
                    # person with a category would be offered as an afternoon
                    # activity.
                    if merged.get("kind"):
                        update["kind"] = merged["kind"]
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
            dupe = (db.table("interest_clusters")
                    .select("id,label,strength,event_count,attributes,status")
                    .eq("user_id", user_id).eq("label", label).limit(1).execute()).data
        except Exception:
            dupe = None
        # A clean-up decided what this name is. Merged: it lives in another
        # group now, so the mention goes there. Archived: known and set
        # aside, so it is not brought back — this match used to set it
        # "active" again, undoing the clean-up the next time she said it.
        # A caregiver typing it into the form (resolve_into=False) is a
        # deliberate choice and may still bring it back.
        _forwarded = False
        if dupe:
            from memory.cluster_resolver import follow, parked
            if (dupe[0].get("status") or "active") == "merged":
                to = follow(db, dupe[0],
                            "id,label,strength,event_count,attributes,status")
                if to and to.get("id") != dupe[0]["id"] and not parked(to) \
                        and (to.get("status") or "active") != "merged":
                    print(f"[Cluster] {label!r} was merged -> {to.get('label')!r}")
                    label = to.get("label") or label
                    dupe = [to]
                    _forwarded = True
                elif resolve_into:
                    print(f"[Cluster] {label!r} was merged into a group that is "
                          f"gone; left as it is")
                    return dupe[0]["id"]
            elif parked(dupe[0]) and resolve_into:
                print(f"[Cluster] {label!r} is {dupe[0].get('status')}; "
                      f"not brought back")
                return dupe[0]["id"]
        # Same name, different person. Her daughter-in-law Priya and her
        # neighbour Priya ji became one cluster — an exact-label match with
        # nothing asked, so two people merged and neither is recoverable.
        #
        # The relation is the evidence and it is already extracted: a bahu is
        # not a padosan. When both carry one and they differ, this is somebody
        # else.
        if dupe:
            _old_rel = ((dupe[0].get("attributes") or {}) if isinstance(
                dupe[0].get("attributes"), dict) else {}).get("relation")
            _new_rel = (attributes or {}).get("relation")
            if _old_rel and _new_rel and str(_old_rel).lower() != str(_new_rel).lower():
                o, n = str(_old_rel).lower(), str(_new_rel).lower()
                if _same_person_confusable(o, n):
                    # Same name, a generation apart: far more often one
                    # person the model was unsure about than two people.
                    # Held as candidates on the one row and flagged, so the
                    # family screen shows one Shubham and a caregiver can
                    # settle it, rather than the code deciding silently.
                    print(f"[Cluster] {label!r}: {n} or {o}? one person, "
                          f"flagged for review")
                    _a = dupe[0].get("attributes") if isinstance(
                        dupe[0].get("attributes"), dict) else {}
                    attributes = _relation_candidates(dict(_a), n)
                    attributes.pop("_skip", None)
                else:
                    # A different person with the same name. The table
                    # allows one row per name per user, so the second one
                    # cannot also be "Priya": inserting it failed on the
                    # unique key and the neighbour was silently lost, every
                    # time. She is kept under a name that tells them apart,
                    # and a later mention of her finds that row.
                    alt = f"{label} ({_new_rel})"
                    print(f"[Cluster] {label!r} is {_new_rel}, not {_old_rel} — "
                          f"a different person, kept as {alt!r}")
                    try:
                        dupe = (db.table("interest_clusters")
                                .select("id,strength,event_count,attributes,status")
                                .eq("user_id", user_id).eq("label", alt)
                                .limit(1).execute()).data or None
                    except Exception:
                        dupe = None
                    label = alt

        if dupe:
            d = dupe[0]
            from memory.cluster_resolver import parked as _parked
            if _parked(d) and resolve_into:
                print(f"[Cluster] {label!r} is {d.get('status')}; not brought back")
                return d["id"]
            merged_attrs = d.get("attributes") or {}
            if isinstance(merged_attrs, str):
                try: merged_attrs = json.loads(merged_attrs)
                except Exception: merged_attrs = {}
            merged_attrs.update({k: v for k, v in (attributes or {}).items() if v})
            # Only reached for a merged row when a caregiver brings it back
            # deliberately; then it is no longer a forwarding address.
            if not _forwarded:
                merged_attrs.pop("merged_into", None)
            upd = {
                "strength":    round((d.get("strength") or 0) + strength, 4),
                "event_count": (d.get("event_count") or 0) + 1,
                "last_event":  "now()",
                "status":      "active",
                "attributes":  merged_attrs,
            }
            # A forwarded mention keeps the survivor where the clean-up put
            # it: "puja" arriving from the habit path as GENERAL must not
            # move Morning puja out of FAITH.
            if not _forwarded:
                upd["pillar"] = pillar
            db.table("interest_clusters").update(upd).eq("id", d["id"]).execute()
            return d["id"]

        created = (db.table("interest_clusters").insert({
            "user_id":     user_id,
            "label":       label,
            "pillar":      pillar,
            "strength":    round(strength, 4),
            "event_count": 1,
            "centroid":    embedding,
            "attributes":  {k: v for k, v in (attributes or {}).items() if v} or {},
            # From the attributes, not the column default. A new cluster came
            # out kind=interest whatever it was, and only a SECOND mention
            # corrected it — so a concern or a person was an interest until
            # she happened to mention it again.
            "kind":        (attributes or {}).get("kind") or "interest",
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
    "hobby": "ASPIRATIONS", "artist": "ENTERTAINMENT", "music": "ENTERTAINMENT", "media": "ENTERTAINMENT",
    "place": "GENERAL", "belief": "GENERAL", "other": "GENERAL",
}

def _is_family(ref: str) -> bool:
    """Is she talking about a relative? "beta", "hijo", "Tochter" — asked,
    once per word. "self", "pronoun", "proper_name" are the extractor's own
    markers, not relations."""
    r = (ref or "").strip()
    if not r or r.lower() in ("self", "user", "pronoun", "proper_name", "i", "me"):
        return False
    try:
        from memory.judge import yes_no
        return yes_no(f'Is "{r}" a word for a family member or relative '
                      f'(not a friend, neighbour or helper), in any language?',
                      key="fam:" + r.lower())
    except Exception:
        return False


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

    prompt = f'''You extract PROPOSITIONS (subject-relation-object facts) from an elderly person's message, in any language (often Hindi/Hinglish).{known_block}

ONE PROPOSITION PER FACT, NOT PER SENTENCE. "Mera beta Vikram Pune mein
engineer hai" holds two: he lives in Pune, and he works as an engineer. It
returned only the occupation and the city was lost — and a city is exactly the
kind of fact that changes later, which is why it needs to exist separately.

For EACH fact return an object:
- subject: canonical name. Translate common nouns to English ("ghutne ka dard"
  KEEP HER WORD whenever she would recognise it as her own — the label is
  what gets said back to her, and she did not say "gardening".

  Not a list of categories. This said "a person, a film, a song, a place, a
  festival, a dish with a name", and bagwani is none of those, so it came back
  as "gardening" while mandir and ghutna survived — the rule was applied
  exactly as written and still got it wrong. The same list-shaped rule turned
  devar into husband and had no slot for மருமகள்.

  So: bagwani, mandir, ghutna, Sholay, Zinda, Mera Yaar, devar, தோட்டம்.
  Translate only when the English is genuinely what she would say herself.

  These are not a boundary — a word not on this line still keeps her form.
  They are here because without them 'ghutne mein dard' came back as 'knee
  pain' and Tamil produced nothing at all: the principle alone was not
  specific enough to act on, and the model judged conservatively toward
  English.

  A title is never vocabulary. "Zinda" means alive AND is a song; when a word
  could be either, keep it as she said it. Translating a common noun loses a
  little; translating a name loses the thing itself, and nothing downstream
  can recover it.
- subject_ref: how they were referred to, IN HER OWN WORDS — "beta", "devar",
  "jethani", "saheli", "padosan", "mausi" — or "self", "pronoun",
  "proper_name" when no relation was named.

  Do NOT translate it and do NOT force it into a small English set. Offered
  seven words to choose from, "mere devar Suresh" came back as husband,
  because devar is the husband's younger brother and husband was the nearest
  slot. Her brother-in-law became her husband, and the milkman became one too.

  Hindi alone has devar, jeth, nanad, bhabhi, jethani, dewrani, sala, mausi,
  chachi, taai, bua, mama — and every other Indian language has its own set.
  There is no list worth keeping. Write what she said.
- relation: likes | stopped_liking | lives_in | works_as | is | has_condition | feels | did
- object: canonical target ("Amreeka"->"America") or null
- entity_type: person | food | health | hobby | artist | music | media | place | belief | other
- kind: durable_fact | action_request | scheduled_event | transient_state
    A FEELING IS NEVER durable. "Bahut khushi hui", "ghar khali lag raha
    hai", "mann nahi tha" are how a day went, not facts about her — they
    belong to the summary, and clustered they become things she supposedly
    has. relation=feels means transient_state, whatever it is about.

    A QUESTION CREATES NO MEMORY OF WHAT IT ASKS ABOUT. "Meri sugar ki report
    kaisi thi?" recorded a sugar report — so she now has one, and she never
    did. "Mere pati ka naam kya tha?" recorded "asked about husband's name".
    The thing being asked about is unknown to HER; recording it invents it.

    AN EMPTY LIST IS A GOOD ANSWER. A question that states nothing yields
    nothing — do not reach for something to return. "Sunita ke saath kab mili
    thi main?" yielded "meet Sunita", as though the meeting were established;
    "Mere pati ka naam kya tha?" yielded "asked about husband's name", which
    narrates her asking rather than recording anything. Neither is a fact.
    Never describe the act of asking.

    A question may still carry facts, but never about its subject. "Kal doctor
    ke paas gayi thi, report kaisi thi?" states that she went yesterday —
    extract that. The report remains unknown and is not a fact.

    durable_fact    = still true next month. "knee pain", "son Shubham in Bangalore", "loves Kishore Kumar"
    action_request  = asking for something to be done. "remind me in 5 minutes", "paanch minute mein yaad dilana"
    scheduled_event = a specific thing at a specific time, worth remembering
                      NEXT WEEK. "doctor kal 12 baje", "beta Sunday ko aa
                      raha hai", "bazar gayi thi Navratri ke liye".

                      Not the ordinary furniture of a day. She ate lunch;
                      that is what lunch is. Six clusters in two days were
                      "Lunch", "Light Meal", "breakfast" and "Aloo parathe"
                      twice — none of which anyone would recall on Friday.

                      The test: does it have a TOMORROW? A market trip does
                      — she bought things and the festival is coming. A meal
                      is finished when it is eaten.

                      And ANSWERING is not an event. "Lunch kaisa raha?"
                      "Acha raha" is a reply to a question. Volunteering is
                      different: "aaj pehli baar dhokla banaya" is a day she
                      would tell someone about.
    transient_state = how they feel right now, not a trait. "thak gayi hoon", "confused", "theek hoon"
  Judge the MEANING, not the words - this must work in any language.
  When unsure between durable_fact and anything else, choose the other one:
  a missed fact costs a little signal, a stored request or dated event rots.
- sentiment: positive | negative | neutral
- salience: 0.0-1.0 (pain, money, family worries high; casual mentions low)
- is_correction: true if the message CHANGES/RETRACTS a prior fact. Triggers: switched, gave up, "no wait", actually, "I meant", "prefer X now", "not X anymore"
- replaces: the prior thing overridden ("coffee") or null
- attributes: for people only {{"relationship":"son/daughter/etc","location":"city","occupation":"job"}}
- when: WHEN they do or did the thing, if the message says so, else null.
    {{"part": "early_morning|morning|afternoon|evening|night", "day": "monday|...|sunday|weekend|weekdays"}}
    Either may be null. It is when the thing HAPPENS, not when they are
    speaking: "kal raat Netflix dekha", said at ten in the morning, is
    {{"part": "night"}}. "Raat ko serial dekhti hoon" is night. "Sunday ko
    chicken banta hai" is {{"day": "sunday"}}. "Subah sair karti hoon" is
    morning. Nothing said about when: null. Never guess from the hour of
    the message.

RULES:
- Different relationships (son AND daughter) are DIFFERENT subjects — NEVER merge them.
- A role/pronoun ("beta","my boy","he") referring to an already-known person uses that PERSON'S proper name as subject.
- Do NOT emit a person's location/job as a separate place/thing — put it in their attributes.

Return ONLY a JSON array. Message:
"{text}"'''

    def _once():
        from google import genai
        client = __import__("llm").genai_client()
        resp = client.models.generate_content(
            model="gemini-flash-lite-latest", contents=prompt)
        raw = (resp.text or "").strip().replace("```json", "").replace("```", "").strip()
        props = json.loads(raw) if raw else []
        return props if isinstance(props, list) else []

    try:
        props = _once()
        # Asked the same sentence fifteen times, the lite model said nothing
        # once — "Kal raat bhi Netflix pe ek film dekhi" came back [] — and in
        # one test run twice in a row, so a habit she stated plainly was never
        # learned. An empty answer is often right ("theek hoon"), so this is
        # not a retry for everything: only when she named a time, which is
        # exactly the sentence a habit is made of.
        # Retried for any message long enough to state something — a
        # list of time words only knew Hindi and English.
        if not props and len((text or "").split()) >= 4:
            props = _once()
            if props:
                print(f"[Propositions] empty first time, retried: {text[:50]!r}")
        return props
    except Exception as e:
        print(f"!!! [Propositions] EXTRACTION FAILED: {e}")
        return []



def _is_durable_fact(name: str, ptype: str = "", rel_type: str = "",
                     kind: str = "") -> bool:
    """Gate out things that shouldn't become their own memory cluster:
    bare emotions ('proud') and vague, non-specific complaints ('tabiyat theek
    nahi'). Uses the extracted name/type — no extra LLM call. Emotions belong to
    the summary's texture, not the fact clusters; vague phrases should attach to
    a concrete condition, not spawn a cluster."""
    # The extractor now labels each proposition. Trust it when present: it reads
    # meaning rather than word shapes, so it works in any language — the older
    # heuristics below are English verb lists that missed "drink water in 3
    # minutes" and "call home in 5 minutes" entirely. They stay as a fallback
    # for propositions extracted before the field existed.
    k = (kind or "").strip().lower()
    if k and k != "durable_fact":
        # One exception: a symptom. "Ghutne mein dard hai" is genuinely a
        # transient state — it describes today — but the REPETITION is the
        # signal, and filtering each instance means the trajectory can never
        # form. Three mentions across a week with trend=worsening is what tells
        # a companion the pain is getting worse; without this each one is
        # discarded and the cluster stays at a single event forever.
        # Everything else transient ("thak gayi hoon") still drops.
        # A PERSON is durable even when what they did is not. "Beta Mohan ka
        # phone aaya" is a Tuesday, and it also tells you Mohan is her son —
        # the whole proposition was dropped and he went with it. Six of nine
        # people she named were lost this way: her son, her devar, her
        # neighbour, the milkman, her grandson.
        #
        # Most mentions of a person are like this. Almost nobody says "mera
        # beta engineer hai" twice; they say he called.
        # A hobby or a faith practice is durable even when the sentence is
        # about tonight. "Aj caroom khelenge" is a Tuesday evening and carrom
        # is still a thing she plays; "mangalvar ko vrat rakhti hoon" came
        # back as a scheduled_event and vanished.
        #
        # Same reasoning as the person exception above: almost nobody says
        # "main carrom khelti hoon" as a statement of fact. They say they are
        # playing tonight.
        if ptype in ("hobby", "belief") and k in ("transient_state",
                                                  "scheduled_event"):
            pass
        elif k != "transient_state" or ptype not in ("health", "person"):
            return False

    n = (name or "").strip().lower()
    if not n or len(n) < 2:
        return False
    # a single word that is purely an emotion label, even if mispillar'd
    if rel_type == "emotion" or ptype == "emotion":
        return False
    return True


def _node_for(user_id: str, label: str, kind: str, pillar: str = "GENERAL"):
    """The cluster for this thing, made if it is not there.

    A place or an occupation is a node so an edge can point at it, but it is
    never something to suggest — no category, so offerable_now skips it.
    """
    label, _attrs = clean_label(label, {"kind": kind})
    if not label:
        return None
    from supabase_store import get_client
    db = get_client()
    try:
        found = (db.table("interest_clusters").select("id")
                 .eq("user_id", user_id).ilike("label", label)
                 .limit(1).execute()).data or []
        if found:
            return found[0]["id"]
    except Exception:
        pass

    row = {"user_id": user_id, "label": label[:120], "pillar": pillar,
           "kind": kind, "status": "active", "strength": 0.5,
           "attributes": {"kind": kind}}
    try:
        from classifier.pillar_classifier import embed_text
        v = embed_text(label)
        if v:
            row["centroid"] = v
    except Exception:
        pass
    try:
        return (db.table("interest_clusters").insert(row).execute()).data[0]["id"]
    except Exception as e:
        print(f"[Prop] could not create node {label!r}: {e}")
        return None

# What a subject_ref has to look like to make something a person. Not a list
# of relations — devar, padosan, mausi and மருமகள் are all relations and no
# list could hold them. These are the refs that are NOT one.
_NOT_A_RELATION = ("", "self", "user", "pronoun", "i", "me", "proper_name",
                   "name", "none", "null")

# type -> (kind, category). A category is what makes something offerable, so
# only things worth offering have one.
_AS = {
    "artist": ("interest", "sangeet"),
    "music":  ("interest", "sangeet"),
    "media":  ("interest", "dekhna"),
    "food":   ("interest", "khana"),
    "hobby":  ("interest", "shauk"),
    "belief": ("interest", "bhakti"),
    "health": ("concern", None),
    "person": ("person", None),
    "place":  ("place", None),
}


def decide(subject: str, props: list) -> tuple:
    """What is this, to her? Returns (etype, kind, category, why).

    One decision rather than a chain of overrides, ordered by what a thing IS
    rather than by which type is most specific — which is what a rank table
    answers and is the wrong question.
    """
    types = [str(p.get("entity_type") or "other").lower() for p in props]
    refs = [str(p.get("subject_ref") or "").strip().lower() for p in props]
    rels = [r for r in refs if r not in _NOT_A_RELATION]

    # Her body, first and without exception. The extractor returned
    # subject_ref "ghutne" for her knee — the knee's own name — and the
    # person rule turned a condition into a person. Nothing about a knee
    # makes it anything but a concern.
    # Her body, first and without exception — but HERS.
    #
    # "Arjun se baat hui, wo theek hai" carries a health proposition about
    # her son, and health-first made him a medical concern. A person with a
    # relation is a person whatever is said about their health; the knee
    # this rule exists for has no relation, because a knee is not somebody.
    if "health" in types and not rels:
        return "health", "concern", None, "health comes first"

    # Then her people, and what makes a person is a RELATION. Shubham arrives
    # as person and media together when she watches a film with him, and a
    # rank table put media first; "beta" is what settles it.
    # An artist is never her person, whatever the ref says. "Kishore da" is
    # how she refers to a singer and "da" is elder brother in Bengali, so
    # loosening the person rule to catch Mausi made him family.
    if any(t in types for t in ("artist", "music", "media")):
        pass
    elif ("person" in types or rels) and rels:
        # A relation is enough on its own. "Mausi ki tabiyat kharab hai"
        # carries only a health proposition — she is mentioned solely through
        # her illness — so person was never in the types and her aunt came
        # out as "other". Somebody with a relation is somebody.
        return "person", "person", None, f"relation: {rels[0]}"

    # Then what she enjoys. An artist is a person and is not her person —
    # she listens to Lata, she knows Shubham — so a name alone never makes
    # one, which is why proper_name is not a relation.
    for t in ("artist", "music", "media", "food", "hobby", "belief"):
        if t in types:
            kind, cat = _AS[t]
            return t, kind, cat, f"{t}, no relation"

    # A person named with no relation at all — someone she mentioned once.
    if "person" in types:
        return "person", "person", None, "a person, unrelated"

    if "place" in types:
        return "place", "place", None, "a place"

    return "other", "other", None, "nothing more specific"


_WHEN_PARTS = ("early_morning", "morning", "afternoon", "evening", "night")
_WHEN_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday",
              "saturday", "sunday", "weekend", "weekdays")


def _note_when(db, cluster_id: str, whens: list) -> None:
    """Count when she does this, on the thing itself: {"night": 3, "weekend": 2}.

    Nothing recorded WHEN anything happens. subject_mentions keeps the date
    she talked about it and the events keep the minute it was logged, and
    neither is when she does it: "kal raat Netflix dekha" said at ten in the
    morning is about ten at night. So when she says, it is kept, and counted
    rather than overwritten, because once is an anecdote and five times is
    her evening.
    """
    seen = []
    for w in whens or []:
        if not isinstance(w, dict):
            continue
        for v in (w.get("part"), w.get("day")):
            v = str(v or "").strip().lower().replace(" ", "_")
            if v in _WHEN_PARTS or v in _WHEN_DAYS:
                seen.append(v)
    if not seen:
        return
    try:
        rows = (db.table("interest_clusters").select("attributes")
                .eq("id", cluster_id).limit(1).execute()).data or []
        a = rows[0].get("attributes") if rows else {}
        if isinstance(a, str):
            a = json.loads(a)
        a = a if isinstance(a, dict) else {}
        usually = dict(a.get("usually") or {})
        for v in set(seen):                 # once per message, however phrased
            usually[v] = int(usually.get(v, 0)) + 1
        a["usually"] = usually
        db.table("interest_clusters").update({"attributes": a}) \
            .eq("id", cluster_id).execute()
        print(f"[Prop] when: {cluster_id[:8]} {usually}")
    except Exception as e:
        print(f"[Prop] when note failed: {e}")


def _lasting(user_id: str, subject: str) -> bool:
    """Is this health matter something that lasts, or something that passes?

    A passing illness — a cold, a fever, an upset stomach — is an episode: it
    starts, is checked on, and ends, and memory/episodes.py keeps exactly
    that. Filed here as well it became a concern group that never ended:
    "Sardi", "Cold" and "Common cold" were three groups for one week of a
    cold, and the episode already had it. What lasts — her knee, BP, thyroid
    — is what a group is for.

    Asked, not listed, so it works for "zukaam" and "jalubu" alike. When the
    model cannot answer it is kept: a group too many is recoverable, a knee
    nobody tracks is not."""
    try:
        from memory.judge import yes_no
        return yes_no(
            f'An elderly person mentioned this about their own health: "{subject}".\n'
            f'Is it a LASTING condition — one that goes on for months or keeps '
            f'coming back (joint pain, blood pressure, diabetes, thyroid, '
            f'weak eyesight) — rather than a passing illness or a symptom of '
            f'one (a cold, cough, fever, upset stomach, a headache today)?',
            key="lasting:" + subject.strip().lower())
    except Exception as e:
        print(f"[Prop] lasting check failed for {subject!r}: {e}")
        return True


def _already_this_session(db, user_id: str, session_id: str, name: str) -> bool:
    """Did the live path already file this, in this conversation?"""
    if not session_id or not name:
        return False
    try:
        got = (db.table("user_behavioral_events").select("id")
               .eq("user_id", user_id).eq("session_id", session_id)
               .eq("value", name).limit(1).execute()).data
        return bool(got)
    except Exception:
        return False


def record_propositions(props: list, classified, user_id: str, session_id: str = "",
                        once_per_session: bool = False) -> dict:
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
                # The object, unless there is none — "kamar dard se pareshan
                # hoon" comes back subject="Kamar dard", ref=self, object=null
                # and her back pain was dropped entirely. The rule exists for
                # "I love Lata", where the subject is wrongly the user; when
                # the object is empty the subject IS the thing.
                key = obj or (subj if subj.lower() not in
                              ("self", "user", "i", "me", "") else "")
            else:
                key = subj                     # cluster the named entity
            if not key or key.lower() in ("self", "user"):
                continue                       # nothing concrete to remember
            by_subject.setdefault(key, []).append(pr)

        affected_clusters = []
        for subj, subj_props in by_subject.items():
            first = subj_props[0]
            # The most specific type across everything said about this
            # subject, not whichever proposition came first. "Vikram lives_in
            # Pune" and "Vikram works_as engineer" arrive together and the
            # second carried entity_type=other, so he was filed as other —
            # a person only by luck of ordering.
            # artist and media outrank person, because the question is not
            # "is this a human" but "what is this TO HER". Lata Mangeshkar is
            # typed artist by one proposition and person by another — she IS
            # a person — and with person first every singer she mentioned
            # became kind=person, which the picker filters out.
            #
            # So conversation could never produce an offerable artist. Only
            # Kishore Kumar was offerable in her real profile, and only
            # because he came from the setup form.
            #
            # She listens to Lata; she does not know her. Rajesh she knows.
# What is this, to her? One decision, with a reason — see
            # decide() above for why this is not a rank table.
            etype, _kind, _cat, _why = decide(subj, subj_props)
            print(f"[Prop] {subj!r} -> {_kind}"
                  + (f"/{_cat}" if _cat else "") + f" ({_why})")

            # A passing illness is an episode, not a group. episodes.hear
            # reads the same message and keeps it, with its start, its
            # check-ins and its end.
            if _kind == "concern" and not _lasting(user_id, subj):
                print(f"[Prop] {subj!r} passes — an episode, not a group")
                continue

            # Gate: skip bare emotions ("proud") and vague complaints
            # ("tabiyat theek nahi") — they belong to the summary's texture,
            # not durable fact clusters.
            _rt = (first.get("relationship_type") or "").lower()
            _k = (first.get("kind") or "").strip().lower()
            if not _is_durable_fact(subj, etype, _rt, _k):
                continue

            attrs = {}
            for pr in subj_props:
                a = pr.get("attributes") or {}
                if isinstance(a, dict):
                    attrs.update({k: v for k, v in a.items() if v})

            attrs["kind"] = _kind
            if _cat:
                attrs["category"] = _cat
            if _kind == "person":
                _r = next((str(pr.get("subject_ref") or "").strip()
                           for pr in subj_props
                           if str(pr.get("subject_ref") or "").strip().lower()
                           not in _NOT_A_RELATION), "")
                if _r:
                    attrs["relation"] = _r


            # A person WITH a family relationship is FAMILY regardless of type
            # ("Vikram lives_in America" arrives as type=place, but he is her son).
            if attrs.get("relationship") or any(
                    _is_family(str(pr.get("subject_ref") or ""))
                    for pr in subj_props):
                pillar = "FAMILY"
                # WHICH relation, not merely that there is one. The extractor
                # returns son, daughter-in-law, grandchild in subject_ref, and the
                # cluster stored "person" for all three — so the system knew Rajesh
                # was a person and had forgotten he was her son.
                #
                # As an edge rather than an attribute, because a relation between
                # two people is what the edge table is for, and it carries dates: a
                # husband who dies or a daughter-in-law who becomes an ex is a
                # closed edge, not a deleted fact.
                # Whatever she called them. The person check stopped using a list
                # and this did not, so "devar" matched nothing and every relation
                # came back empty — twelve people and not one of them anybody.
                _NOT_REL = ("", "self", "user", "pronoun", "i", "me", "proper_name")
                _rel = next((str(pr.get("subject_ref") or "").strip()
                             for pr in subj_props
                             if str(pr.get("subject_ref") or "").strip().lower()
                             not in _NOT_REL), "")
                if _rel:
                    attrs["relation"] = _rel
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
                             .eq("user_id", user_id).eq("status", "active")
                             .ilike("label", f"%{repl}%")
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
                            .eq("user_id", user_id).eq("status", "active")
                            .ilike("label", f"%{subj}%")
                            .limit(1).execute()).data
                    if gone:
                        faded = round((gone[0].get("strength") or 0) * 0.3, 4)
                        # Fading alone loses WHY it faded. "She stopped liking
                        # coffee" and "coffee never came up" end up looking the
                        # same, so the companion has no way to know not to
                        # offer it. Mark it a negative preference explicitly —
                        # computed_dislikes reads exactly this.
                        db.table("interest_clusters").update({
                            "strength":      faded,
                            "relationship":  "preference",
                            "current_state": -1.0,
                            "last_sentiment": -1.0,
                        }).eq("id", gone[0]["id"]).execute()
                except Exception as e:
                    print(f"[Prop] retract-fade failed: {e}")
                continue

            # resolve + upsert (reuse anchoring path)
            # The relation goes with the name. Two people share a name far
            # more often than two conditions do, and "bahu" versus "padosan"
            # is the only thing telling her daughter-in-law Priya from her
            # neighbour Priya ji.
            res = resolve(subj, etype, pillar, user_id,
                          relation=attrs.get("relation", ""))
            # Strength scales by the LLM's salience classification: a stated
            # passion ("I love X", salience~0.8) stores strong and surfaces now;
            # a passing mention ("watched some cricket", ~0.3) stores weak and
            # only surfaces if it accumulates over repeated mentions. The LLM
            # judges importance; we just multiply. No thresholds, no verb rules.
            ev_strength = round(float(classified.core_score or 0.5) * max(0.15, salience), 4)
            # The conversation is read twice: each message as it arrives, and
            # all of hers together when it closes. Both filed every fact, so
            # every mention counted double — strength, event_count, events.
            if once_per_session and (
                    _already_this_session(db, user_id, session_id, res["name"])
                    or _already_this_session(db, user_id, session_id, subj)):
                print(f"[Prop] {subj!r} already filed this conversation")
                continue
            cluster_id = _upsert_cluster(user_id, res["name"], pillar, ev_strength,
                                         res.get("embedding"), attrs or None)
            if cluster_id:
                affected_clusters.append(cluster_id)
                _note_when(db, cluster_id, [pr.get("when") for pr in subj_props])

                # Facts ABOUT this subject become their own nodes, linked.
                #
                # "Vikram Pune mein engineer hai" used to store the occupation
                # and lose the city. As an attribute a city is overwritten when
                # he moves and "pehle kahan tha" has no answer; as an edge with
                # dates, Delhi closes and Pune opens and both survive.
                #
                # Which type is exclusive matters: he lives in one city, so a
                # new lives_in closes the old. Children accumulate — a third
                # grandchild does not end the first two.
                _EDGE_REL = {
                    "lives_in": ("lives_in", "place"),
                    "works_as": ("does", "occupation"),
                    "treats":   ("treats", "condition"),
                }
                for pr in subj_props:
                    rel = (pr.get("relation") or "").lower()
                    obj = (pr.get("object") or "").strip()
                    if rel not in _EDGE_REL or not obj or len(obj) < 2:
                        continue
                    etype_edge, node_kind = _EDGE_REL[rel]
                    try:
                        from memory.relations import link_current
                        obj_id = _node_for(user_id, obj, node_kind, pillar)
                        if obj_id:
                            link_current(user_id, cluster_id, obj_id, etype_edge)
                    except Exception as _ee:
                        print(f"[Prop] edge failed for {obj!r}: {_ee}")
                # one event per subject (the relation is the state verb)
                try:
                    db.table("user_behavioral_events").insert({
                        "user_id": user_id, "cluster_id": cluster_id,
                        "session_id": session_id or None, "pillar": pillar,
                        "sub_pillar": etype, "value": res["name"],
                        "surface_form": subj[:200], "strength": ev_strength,
                        "sentiment": sentiment, "salience": salience,
                        "event_type": relation[:40],
                        # relationship_type is the KIND of thing this is to them
                        # (concern/preference/person/...). The entity path at the
                        # bottom of this file writes exactly that. This path used
                        # to write subject_ref here instead — proper_name, son,
                        # self — so one column held two unrelated vocabularies
                        # and whichever path ran last won. That is why no cluster
                        # anywhere is marked "preference", and why health rows
                        # came out as "self".
                        # The proposition extractor does not return the
                        # concern/preference vocabulary — that belongs to the
                        # entity path. But `relation` already carries the same
                        # distinction and is reliably populated: likes,
                        # stopped_liking, has_condition, lives_in, feels, did.
                        # Map it, so a cluster's dominant relation tells us
                        # whether it is an interest, a concern or a person.
                        "relationship_type": {
                            "likes":          "preference",
                            "stopped_liking": "preference",
                            "has_condition":  "concern",
                            "feels":          "feeling",
                            "lives_in":       "person",
                            "works_as":       "person",
                            "is":             "person",
                            "did":            "action",
                        }.get((relation or "").lower()) or None,
                        "context": {"subject_ref": first.get("subject_ref")},
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

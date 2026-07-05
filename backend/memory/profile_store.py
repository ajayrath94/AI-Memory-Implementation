"""
USER PROFILE STORE
Builds and maintains a living profile of who the user is.

Separate from user_memory (which tracks what happened).
This tracks who the person fundamentally is:
  - Name, age, location
  - Family structure
  - Health conditions
  - Interests and hobbies
  - Personality traits
  - Communication style
  - Life context

Profile is extracted from conversations using Claude Haiku
and merged incrementally — never overwrites, only enriches.
"""

import os
import json
from typing import Optional
from supabase_store import get_client, get_session_messages


# ── Get / Save ─────────────────────────────────────────────────────────────────

def get_user_profile(user_id: str) -> Optional[dict]:
    db     = get_client()
    result = db.table("user_profile").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None


def save_user_profile(user_id: str, updates: dict):
    """
    Merge updates into existing profile.
    Never overwrites a field with empty/None — only enriches.
    """
    db       = get_client()
    existing = get_user_profile(user_id) or {}

    merged = _deep_merge(existing, updates)
    merged["user_id"]    = user_id
    merged["updated_at"] = "now()"

    db.table("user_profile").upsert(merged, on_conflict="user_id").execute()
    print(f"[Profile] Updated profile for {user_id}")


def _deep_merge(base: dict, updates: dict) -> dict:
    """
    Deep merge updates into base.
    - Scalars: only update if base is empty/None
    - Dicts: merge recursively
    - Lists: union (no duplicates)
    """
    result = dict(base)
    for key, new_val in updates.items():
        if key in ("user_id", "updated_at", "created_at"):
            continue
        existing_val = result.get(key)

        if new_val is None or new_val == "" or new_val == {} or new_val == []:
            continue  # Never overwrite with empty

        if isinstance(new_val, dict) and isinstance(existing_val, dict):
            result[key] = _deep_merge(existing_val, new_val)
        elif isinstance(new_val, list) and isinstance(existing_val, list):
            combined = existing_val + [x for x in new_val if x not in existing_val]
            result[key] = combined
        else:
            # For scalars: update if existing is empty
            if not existing_val:
                result[key] = new_val
            else:
                result[key] = existing_val  # Keep existing, don't overwrite

    return result


# ── Extract profile from conversation ──────────────────────────────────────────

def extract_profile_from_session(session_id: str, user_id: str) -> dict:
    """
    Use Claude Haiku to extract profile information from a session.
    Returns a partial profile dict with only what was found.
    """
    messages = get_session_messages(session_id)
    if not messages:
        return {}

    # Build conversation text
    convo = []
    for msg in messages:
        if msg.get("role") in ("user", "assistant"):
            role    = "User" if msg["role"] == "user" else "Nancy"
            content = msg.get("content", "")[:500]
            convo.append(f"{role}: {content}")

    convo_text = "\n".join(convo[-20:])  # Last 20 messages

    prompt = f"""Analyze this conversation and extract factual information about the user.
Return ONLY a JSON object with what you can confidently extract. Leave fields empty if not mentioned.

Conversation:
{convo_text}

Extract into this exact JSON structure (use empty string/dict/list if not found):
{{
  "name": "user's name if mentioned",
  "age_group": "approximate age group: under-50/50-60/60-70/70-80/80+",
  "location": "city or region if mentioned",
  "language_pref": "hindi/english/hinglish based on how they speak",
  "family": {{
    "spouse": "name/status if mentioned",
    "children": ["list of children mentioned with details"],
    "grandchildren": ["list if mentioned"],
    "other": ["other family members mentioned"]
  }},
  "health": {{
    "conditions": ["list of health conditions mentioned"],
    "medications": ["list of medications mentioned"],
    "concerns": ["health concerns or symptoms mentioned"]
  }},
  "interests": {{
    "sports": ["sports they follow"],
    "music": ["music preferences"],
    "entertainment": ["TV/movies/shows"],
    "religion": ["religious practices if mentioned"],
    "hobbies": ["other hobbies"]
  }},
  "personality": {{
    "traits": ["personality traits observed"],
    "emotional_state": "current overall emotional state",
    "communication_style": "how they communicate"
  }},
  "life_context": {{
    "occupation": "past/current occupation if mentioned",
    "living_situation": "lives alone/with family/etc",
    "notable_events": ["significant life events mentioned"]
  }}
}}

Return ONLY the JSON, no explanation."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp   = client.messages.create(
            model      = "claude-haiku-4-5",
            max_tokens = 1000,
            messages   = [{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()

        # Clean JSON
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        extracted = json.loads(text)
        print(f"[Profile] Extracted profile data from session {session_id[:8]}")
        return extracted

    except json.JSONDecodeError as e:
        print(f"[Profile] JSON parse failed: {e}")
        return {}
    except Exception as e:
        print(f"[Profile] Extraction failed: {e}")
        return {}


# ── Update profile after session ───────────────────────────────────────────────

def update_profile_from_session(session_id: str, user_id: str):
    """
    Extract and merge profile updates after a session ends.
    Called in background alongside memory summarization.
    """
    try:
        extracted = extract_profile_from_session(session_id, user_id)
        if extracted:
            save_user_profile(user_id, extracted)
    except Exception as e:
        print(f"[Profile] Update failed: {e}")


# ── Build profile context for Nancy ───────────────────────────────────────────

def build_profile_prompt(user_id: str) -> Optional[str]:
    """
    Build a concise profile summary to inject into Nancy's system prompt.
    Only includes fields that are actually populated.
    """
    profile = get_user_profile(user_id)
    if not profile:
        return None

    lines = ["PERSONAL PROFILE:"]

    if profile.get("name"):
        lines.append(f"- Name: {profile['name']}")
    if profile.get("age_group"):
        lines.append(f"- Age group: {profile['age_group']}")
    if profile.get("location"):
        lines.append(f"- Location: {profile['location']}")
    if profile.get("language_pref"):
        lines.append(f"- Preferred language: {profile['language_pref']}")

    # Family
    family = profile.get("family", {})
    if family:
        family_parts = []
        if family.get("spouse"):
            family_parts.append(f"spouse: {family['spouse']}")
        if family.get("children"):
            family_parts.append(f"children: {', '.join(family['children'])}")
        if family.get("grandchildren"):
            family_parts.append(f"grandchildren: {', '.join(family['grandchildren'])}")
        if family_parts:
            lines.append(f"- Family: {'; '.join(family_parts)}")

    # Health
    health = profile.get("health", {})
    if health.get("conditions"):
        lines.append(f"- Health conditions: {', '.join(health['conditions'])}")
    if health.get("medications"):
        lines.append(f"- Medications: {', '.join(health['medications'])}")

    # Interests
    interests = profile.get("interests", {})
    interest_parts = []
    for category, items in interests.items():
        if items:
            vals = items if isinstance(items, list) else [items]
            if vals:
                interest_parts.append(f"{category}: {', '.join(str(v) for v in vals)}")
    if interest_parts:
        lines.append(f"- Interests: {'; '.join(interest_parts)}")

    # Personality
    personality = profile.get("personality", {})
    if personality.get("traits"):
        lines.append(f"- Personality: {', '.join(personality['traits'])}")
    if personality.get("communication_style"):
        lines.append(f"- Communication style: {personality['communication_style']}")

    # Life context
    life = profile.get("life_context", {})
    if life.get("occupation"):
        lines.append(f"- Occupation: {life['occupation']}")
    if life.get("living_situation"):
        lines.append(f"- Living situation: {life['living_situation']}")

    # Demographics
    demographics = profile.get("demographics", {})
    if demographics.get("age"):
        lines.append(f"- Age: {demographics['age']} years old")
    if demographics.get("gender"):
        lines.append(f"- Gender: {demographics['gender']}")
    if demographics.get("marital_status"):
        lines.append(f"- Marital status: {demographics['marital_status']}")
    if demographics.get("diet"):
        lines.append(f"- Diet: {demographics['diet']}")

    # Cultural context
    cultural = profile.get("cultural_context", {})
    if cultural.get("religion"):
        lines.append(f"- Religion: {cultural['religion']}")
    if cultural.get("practices"):
        lines.append(f"- Religious practices: {', '.join(cultural['practices'])}")
    if cultural.get("festivals"):
        lines.append(f"- Festivals: {', '.join(cultural['festivals'])}")
    if cultural.get("region"):
        lines.append(f"- Region: {cultural['region']}")

    if len(lines) == 1:
        return None  # Only header, nothing populated

    lines.append("\nUse this profile to personalize responses. Address them by name if known.")
    lines.append("Respect their religious beliefs, dietary preferences, and cultural background.")
    return "\n".join(lines)

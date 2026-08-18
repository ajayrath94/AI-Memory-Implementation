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

import re
import os
import json
from typing import Optional
from supabase_store import get_client, get_session_messages


# ── Get / Save ─────────────────────────────────────────────────────────────────

def get_user_profile(user_id: str) -> Optional[dict]:
    db     = get_client()
    result = db.table("user_profile").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None


def ensure_profile_exists(user_id: str):
    """Guarantee a user_profile row exists so user_behavioral_events (FK to
    user_profile) can insert. On a new user the profile is otherwise created only
    at the END of enrichment, after events already tried to write. Call BEFORE events."""
    if not user_id:
        return
    try:
        from supabase_store import get_client
        db = get_client()
        existing = db.table("user_profile").select("user_id").eq("user_id", user_id).execute()
        if not existing.data:
            db.table("user_profile").insert({"user_id": user_id}).execute()
    except Exception as e:
        print(f"[Profile] ensure_profile_exists: {e}")


# ── Resolve before merge ──────────────────────────────────────────────────────
# String canonicalisation cannot tell that "knee pain" and "knees health" are
# one concern while "back pain" is another — and neither can cosine alone:
# measured on this data, "joint pain"/"back pain" scores 0.92, ABOVE pairs that
# should merge. entity_resolver does vector retrieval then LLM adjudication,
# which is the only combination that separates them. Resolving here, at write
# time, is what stops the lists fragmenting in the first place; the batch
# cleaner only mops up what already accumulated.

_RESOLVE_KEYS = {
    "conditions": "health condition",
    "concerns":   "health concern",
    "sports":     "sport",
    "music":      "music interest",
    "entertainment": "entertainment interest",
    "hobbies":    "hobby",
}
# "medications" is deliberately absent: "BP tablet (old)" and "(new)" record a
# switch, and resolving them together would erase it.


def _resolve_incoming(updates: dict, existing: dict, user_id: str) -> dict:
    """Rewrite new list items to the canonical name already stored, where the
    resolver confirms they are the same thing. Never drops: an unmatched item
    passes through unchanged and becomes a new entry."""
    if not user_id:
        return updates

    try:
        from memory.entity_resolver import resolve
    except Exception as e:
        print(f"[Profile] resolver unavailable: {e}")
        return updates

    out = dict(updates)
    for section in ("health", "interests"):
        new_block = updates.get(section)
        old_block = existing.get(section) or {}
        if not isinstance(new_block, dict) or not isinstance(old_block, dict):
            continue
        section_out = dict(new_block)
        for key, entity_type in _RESOLVE_KEYS.items():
            incoming = new_block.get(key)
            pool = [x for x in (old_block.get(key) or []) if isinstance(x, str)]
            if not isinstance(incoming, list) or not pool:
                continue
            resolved = []
            for item in incoming:
                if not isinstance(item, str) or not item.strip():
                    continue
                try:
                    r = resolve(item, entity_type, "", user_id, against=pool)
                    resolved.append(r["name"])
                except Exception as e:
                    print(f"[Profile] resolve failed for {item!r}: {e}")
                    resolved.append(item)
            section_out[key] = resolved
        out[section] = section_out
    return out


def save_user_profile(user_id: str, updates: dict):
    """
    Merge updates into existing profile.
    Never overwrites a field with empty/None — only enriches.
    """
    db       = get_client()
    existing = get_user_profile(user_id) or {}

    owner   = updates.get("name") or existing.get("name") or ""
    updates = _resolve_incoming(updates, existing, user_id)
    merged  = _deep_merge(existing, updates, owner, user_id)
    merged["user_id"]    = user_id
    merged["updated_at"] = "now()"

    db.table("user_profile").upsert(merged, on_conflict="user_id").execute()
    print(f"[Profile] Updated profile for {user_id}")



# ── List canonicalisation ─────────────────────────────────────────────────────
# The session extractor writes free-form descriptive strings, so the same entity
# arrives phrased differently every run ("Shubham", "Shubham (son)", "Shubham -
# sends medication"). Exact-match dedup never fires against that, which is how
# profile lists grew unbounded. We compare on a stripped identity key instead
# and keep the cleanest surface form we have seen.

_PAREN = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
_TAIL  = re.compile(r"\s+[-\u2013\u2014]\s+.*$")
_HEDGE = re.compile(
    r"\b(appears?\s+to\s+be|seems?\s+to\s+be|appears?|possibly|probably|"
    r"maybe|likely|mentioned\s+as|mentioned\s+in\s+conversation|mentioned|"
    r"known\s+person|unclear|unknown)\b", re.I)
_FRAGMENT_PREFIX = ("in ", "at ", "on ", "the ", "with ", "from ", "for ")


# ── Reserved entities ─────────────────────────────────────────────────────────
# Nancy is the companion, not a person in the user's life — but she is named in
# almost every turn, so the extractor keeps proposing her as a relative. The
# user's own name has the same problem from self-reference ("Shobha ne kaha").
# Both are dropped before dedup so they can never reach the profile.

def _reserved_names(owner: str = "", user_id: str = "") -> set:
    """Companion names (current and historical) plus the profile owner's own
    name. The companion set comes from memory.persona_names so a renamed
    companion is still filtered — see that module for why history is kept."""
    from memory.persona_names import get_reserved_names as _companion_names
    r = _companion_names(user_id) if user_id else {"nancy", "nancy ai", "nancy app"}
    r = set(r)
    if owner:
        o = re.sub(r"[^\w\s]", " ", owner).strip().lower()
        if o:
            r.add(o)
            r.update(o.split())      # first name alone
    return r


def _is_reserved(key: str, owner: str = "", user_id: str = "") -> bool:
    if not key:
        return False
    reserved = _reserved_names(owner, user_id)
    if key in reserved:
        return True
    return key.split()[0] in reserved if key.split() else False


# Relation words that arrive with no name attached ("Daughter - living abroad",
# "Beta (son/child)"). These are placeholders the extractor emits when it knows
# a relative exists but not who — they are not entities and must not persist as
# names. Hinglish included: the extractor works in the language the user speaks.
_RELATION_WORDS = {
    "son", "daughter", "child", "children", "kid", "kids", "husband", "wife",
    "spouse", "mother", "father", "parent", "brother", "sister", "sibling",
    "grandson", "granddaughter", "grandchild", "grandchildren", "uncle", "aunt",
    "cousin", "nephew", "niece", "friend", "neighbour", "neighbor", "caregiver",
    "beta", "beti", "bahu", "damad", "pota", "poti", "bhai", "behen", "bhen",
    "maa", "ma", "papa", "pita", "pati", "patni", "dada", "dadi", "nana", "nani",
    "mama", "mami", "chacha", "chachi", "bua", "saas", "sasur", "devar", "jeth",
}

# Leading relation labels: "Son: Arjun" and "Arjun" are one person.
_LABEL = re.compile(
    r"^\s*(son|daughter|child|husband|wife|spouse|mother|father|brother|sister|"
    r"grandson|granddaughter|grandchild|beta|beti|friend|caregiver)\s*:\s*",
    re.I)


_GENERIC = {
    "chronic", "urgent", "urgent health concern", "health concern", "concern",
    "concerns", "issue", "issues", "problem", "problems", "general", "other",
    "unknown", "unclear", "various", "misc", "none", "n a", "health", "status",
}


def _clean_surface(s: str) -> str:
    """Strip parentheticals, dash-tails and hedges but keep original casing."""
    t = _LABEL.sub("", s)
    t = _PAREN.sub(" ", t)
    t = _TAIL.sub("", t)
    t = _HEDGE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip(" ,;:-\u2013\u2014")
    return t


# Strip a trailing prepositional phrase: "Arjun in Mumbai" and "Arjun" are one
# person. Only after a name-shaped head, so "in Bangalore" is untouched here and
# falls to the fragment check below.
_TRAILING_PP = re.compile(
    r"^(.*?\S)\s+(in|at|from|near|of|with|living\s+in|lives\s+in|based\s+in)\s+\S.*$",
    re.I)

# Function words that can never be the head of an entity name. Hedge removal
# leaves debris ("mentioned but location unknown" -> "but location"); rather
# than chase every phrasing, require the remainder to still look like a name.
_STOPHEADS = {
    "but", "and", "or", "the", "a", "an", "who", "which", "that", "this",
    "there", "here", "not", "no", "is", "was", "has", "have", "been", "be",
    "some", "any", "one", "someone", "somebody", "person", "people", "location",
    "status", "details", "detail", "info", "information", "context",
}


def _canonical_key(s) -> str:
    """Identity key for dedup. Returns '' for items that should be dropped."""
    if not isinstance(s, str):
        return ""
    t = _clean_surface(s).lower()
    m = _TRAILING_PP.match(t)
    if m:
        t = m.group(1)
    t = t.split("/")[0]          # "knee pain/dard" -> "knee pain"
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) < 2 or t in _GENERIC or t in _RELATION_WORDS:
        return ""
    if t.startswith(_FRAGMENT_PREFIX):
        return ""
    words = t.split()
    if words[0] in _STOPHEADS:
        return ""
    if all(w in _STOPHEADS or w in _RELATION_WORDS or w in _GENERIC for w in words):
        return ""
    return t


def _flatten_item(item):
    """The extractor occasionally emits a dict instead of a string (the prompt
    asks for children 'with details', so the model sometimes obliges with
    structure). Rare and schema-less — four entries across 81 profiles, four
    different key sets. Collapse to the name so it dedups with the string form
    rather than being silently discarded."""
    if isinstance(item, dict):
        return (item.get("name") or item.get("value") or "").strip()
    return item


def _merge_list(existing, new, cap: int = 25, owner: str = "", user_id: str = "") -> list:
    best, order = {}, []
    for item in (_flatten_item(x) for x in list(existing or []) + list(new or [])):
        k = _canonical_key(item)
        if not k or _is_reserved(k, owner, user_id):
            continue
        val = _clean_surface(item) if isinstance(item, str) else item
        if not val:
            continue
        if k not in best:
            best[k] = val
            order.append(k)
        elif len(val) < len(best[k]):
            best[k] = val
    return [best[k] for k in order][:cap]


def _deep_merge(base: dict, updates: dict, owner: str = "", user_id: str = "") -> dict:
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
            result[key] = _deep_merge(existing_val, new_val, owner, user_id)
        elif isinstance(new_val, list) and isinstance(existing_val, list):
            result[key] = _merge_list(existing_val, new_val, owner=owner, user_id=user_id)
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

    Reads USER turns only. Including Nancy's replies let the extractor treat the
    companion's own words as evidence about the user: in one profile "Shubham"
    was named exactly once, by Nancy, and became the user's spouse, child AND
    grandchild across successive sessions. Nancy herself was repeatedly filed as
    a family member. The schema below reads as a form to fill in, so the model
    fills it from whatever proper nouns are in range — the rules exist to make
    an empty field the expected answer rather than a failure.
    """
    messages = get_session_messages(session_id)
    if not messages:
        return {}

    convo = []
    for msg in messages:
        if msg.get("role") == "user":
            content = (msg.get("content") or "")[:500].strip()
            if content:
                convo.append(content)
    if not convo:
        return {}
    convo_text = "\n".join(f"- {line}" for line in convo[-20:])

    # The companion's name is per-user (bot_personas.bot_name). A companion may
    # also be styled as a relative — "Shubham", relationship "son" — in which
    # case the user says "mera beta Shubham" about the COMPANION. Nothing
    # distinguishes that from a real son of the same name, so for familial
    # personas the name is off-limits even when a relation is stated.
    from memory.persona_names import get_companion_name, is_familial_persona
    bot_name = get_companion_name(user_id)
    familial_note = ""
    if is_familial_persona(user_id):
        familial_note = (
            f" This companion is styled as a relative, so the user may address"
            f" them as one (\"mera beta {bot_name}\", \"{bot_name} beta\")."
            f" That is still the companion, not a real relative — never record"
            f" \"{bot_name}\" in family under any relation.")

    prompt = f"""These are statements the user made. Extract only what the user
stated about themselves.

RULES — these override the schema:

0. "{bot_name}" is the name of the AI companion the user is talking to. The
   user addresses the companion by name constantly. The companion is NEVER a
   family member, friend or contact, and must never appear anywhere in the
   output.{familial_note} Nor may the user's own name appear in "family" — a
   person is not their own relative.

1. The schema is a shape, not a checklist. Most fields are empty most of the
   time. An empty field is the CORRECT answer when the user did not say it.
2. Do not infer a relationship from a name. A name with no stated relationship
   does not go in "family" at all.
3. Do not guess which relation someone is. "Mera beta Shubham" is a son.
   "Shubham called" is a person with no stated relation — omit them.
   If the user refers to a relative without naming them ("meri beti", "my
   son"), omit them too. A relation word is not a name — never write "beta",
   "beti", "son" or "daughter" as if it were one.
4. Do not infer religion, caste, community or politics from greetings, food,
   festivals or names. Record these ONLY if the user states the practice
   directly. "Namaste" is a greeting, not a religious practice.
5. Do not infer living situation, loneliness, or family estrangement. Record
   only what is stated outright.
6. Never use hedging words in a value ("appears to be", "possibly", "seems",
   "mentioned"). If you would need one, the field should be empty instead.
7. Names go in name fields; descriptions do not. Write "Arjun", not
   "Arjun - son, doctor in Mumbai". Put a location in the location field.

User's statements:
{convo_text}

Extract into this exact JSON structure (use empty string/dict/list if not found):
{{
  "name": "user's own name, only if they said it",
  "age_group": "under-50/50-60/60-70/70-80/80+, only if age was stated",
  "location": "city or region the user says they live in",
  "language_pref": "hindi/english/hinglish based on how they write",
  "family": {{
    "spouse": "name ONLY if user said husband/wife/pati/patni",
    "children": ["name ONLY if user said beta/beti/son/daughter"],
    "grandchildren": ["name ONLY if user said pota/poti/grandson/granddaughter"],
    "other": ["name AND stated relation, e.g. 'Meera (sister)'; omit if unstated"]
  }},
  "health": {{
    "conditions": ["condition the user says they have"],
    "medications": ["medication the user says they take"],
    "concerns": ["symptom or worry the user stated"]
  }},
  "interests": {{
    "sports": ["sports the user says they follow"],
    "music": ["music the user says they like"],
    "entertainment": ["TV/movies/shows the user says they watch"],
    "religion": ["religious practice ONLY if the user describes doing it"],
    "hobbies": ["other hobbies the user states"]
  }},
  "personality": {{
    "traits": ["trait clearly evidenced in how the user writes"],
    "emotional_state": "emotional state the user expressed",
    "communication_style": "how they communicate"
  }},
  "life_context": {{
    "occupation": "job the user says they have or had",
    "living_situation": "ONLY if the user states who they live with",
    "notable_events": ["event the user described"]
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
    current = profile.get("current_location")
    home    = profile.get("home_location") or profile.get("location")
    if current and home and current.lower() != home.lower():
        lines.append(f"- Currently in: {current} (home: {home})")
    elif current:
        lines.append(f"- Location: {current}")
    elif home:
        lines.append(f"- Location: {home}")
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

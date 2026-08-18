"""
BOT PERSONA ROUTES
Allows caregivers to personalize the AI companion for their family member.

  GET    /persona/{user_id}          → get current persona
  POST   /persona/{user_id}          → create/update persona
  DELETE /persona/{user_id}          → reset to default Nancy
  GET    /persona/presets             → available voice/personality presets
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()


class PersonaCreate(BaseModel):
    bot_name:     str = "Nancy"
    relationship: str = "companion"
    voice_type:   str = "preset"
    voice_id:     Optional[str] = None
    slangs:       List[str] = []
    language_mix: dict = {}
    personality:  dict = {"warmth": 0.9, "humor": 0.6}
    caregiver_id: Optional[str] = None


@router.get("/presets")
def get_presets():
    """Available voice and personality presets."""
    return {
        "voices": [
            {"id": "warm_female",    "name": "Warm Female",     "description": "Caring, motherly tone", "language": "Hindi/English"},
            {"id": "friendly_male",  "name": "Friendly Male",   "description": "Warm, brotherly tone",  "language": "Hindi/English"},
            {"id": "young_female",   "name": "Young Female",    "description": "Energetic, cheerful",   "language": "Hindi/English"},
            {"id": "elder_male",     "name": "Elder Male",      "description": "Wise, grandfatherly",   "language": "Hindi/English"},
        ],
        "relationships": [
            {"id": "son",        "label": "Beta (Son)"},
            {"id": "daughter",   "label": "Beti (Daughter)"},
            {"id": "friend",     "label": "Dost (Friend)"},
            {"id": "companion",  "label": "Saathi (Companion)"},
            {"id": "caretaker",  "label": "Dekhbhal Karne Wala"},
        ],
        "suggested_slangs": {
            # Indian languages
            "hindi":     ["arre yaar", "kya baat hai", "bilkul sahi", "bas kar", "wah wah"],
            "tamil":     ["enna da", "super da", "romba nalla", "apdiya", "seri da"],
            "telugu":    ["enti", "chala manchidi", "ayyo", "akkada", "bagundi"],
            "kannada":   ["howdu", "chennagide", "yaake", "illwa", "enu madta"],
            "malayalam": ["sheriyanu", "kollam", "enthanu", "undo", "adipoli"],
            "gujarati":  ["kem cho", "maja ma", "shu thayu", "arre bhai", "hu samju chu"],
            "bengali":   ["ki holo", "bhalo", "ache", "tumi", "durdanto"],
            "punjabi":   ["kiddan", "ki haal", "chak de", "sat sri akal", "waah"],
            "marathi":   ["aho", "kai zala", "khup chan", "baro aahe", "arre baba"],
            "odia":      ["kemiti acha", "bhala", "theek achi", "aha", "sundara"],
            # South Asian
            "urdu":      ["mashallah", "wah", "bilkul", "theek hai", "accha"],
            # Gulf / Middle East
            "arabic":    ["yalla", "habibi", "inshallah", "mashallah", "khalas"],
            # European
            "spanish":   ["venga", "anda ya", "madre mia", "claro", "bueno"],
            "german":    ["genau", "ach so", "mensch", "prima", "wunderbar"],
            "french":    ["voila", "alors", "mon dieu", "enfin", "parfait"],
            # East Asian
            "chinese":   ["haode", "duile", "aiya", "zhende ma", "tai hao le"],
            "japanese":  ["sou sou", "naru hodo", "sugoi", "yokatta", "maa maa"],
        }
    }


@router.get("/{user_id}")
def get_persona(user_id: str):
    """Get bot persona for a user."""
    try:
        from supabase_store import get_client
        db     = get_client()
        result = db.table("bot_personas")\
            .select("*")\
            .eq("user_id", user_id)\
            .limit(1)\
            .execute()

        if result.data:
            return {"status": "ok", "persona": result.data[0], "is_default": False}

        # Return default persona
        return {
            "status":     "ok",
            "persona":    {
                "bot_name":     "Nancy",
                "relationship": "companion",
                "voice_type":   "preset",
                "voice_id":     "warm_female",
                "slangs":       [],
                "language_mix": {},
                "personality":  {"warmth": 0.9, "humor": 0.6},
            },
            "is_default": True,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/{user_id}")
def upsert_persona(user_id: str, req: PersonaCreate):
    """Create or update bot persona."""
    try:
        from supabase_store import get_client
        db = get_client()

        # Only write fields the caller actually sent. Building `data` from every
        # attribute meant a rename that posted just {"bot_name": ...} silently
        # wiped slangs, language_mix and personality back to their defaults —
        # PersonaCreate cannot otherwise tell "omitted" from "set to empty".
        # exclude_unset preserves that distinction, so clearing a field on
        # purpose still works.
        sent = req.model_dump(exclude_unset=True)

        data = {"user_id": user_id, "updated_at": "now()"}
        for field in ("bot_name", "relationship", "voice_type", "voice_id",
                      "slangs", "language_mix", "personality", "caregiver_id"):
            if field in sent:
                data[field] = sent[field]
        if isinstance(data.get("bot_name"), str):
            data["bot_name"] = data["bot_name"].strip()
        if data.get("caregiver_id") is None:
            data.pop("caregiver_id", None)

        # Check if exists
        existing = db.table("bot_personas")\
            .select("id,bot_name,bot_name_history")\
            .eq("user_id", user_id)\
            .execute()

        # Every name this companion has ever had stays reserved. Stored sessions
        # still contain the old name after a rename; if it stopped being
        # reserved, re-extraction over them would file the former companion as a
        # relative. See memory/persona_names.get_reserved_names.
        row     = (existing.data or [{}])[0]
        history = list(row.get("bot_name_history") or [])
        for n in (row.get("bot_name"), data.get("bot_name")):
            if n and n not in history:
                history.append(n)
        if history:
            data["bot_name_history"] = history

        # A brand-new persona still needs a name.
        if not existing.data and not data.get("bot_name"):
            data["bot_name"] = "Nancy"
            data["bot_name_history"] = ["Nancy"]

        if existing.data:
            db.table("bot_personas")\
                .update(data)\
                .eq("user_id", user_id)\
                .execute()
        else:
            db.table("bot_personas").insert(data).execute()

        print(f"[Persona] Updated for {user_id}: {data.get('bot_name', '(unchanged)')}"
              f" ({data.get('relationship', '(unchanged)')})")
        return {"status": "ok",
                "bot_name": data.get("bot_name") or row.get("bot_name")}

    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.delete("/{user_id}")
def reset_persona(user_id: str):
    """Reset to default Nancy persona."""
    try:
        from supabase_store import get_client
        db = get_client()
        db.table("bot_personas").delete().eq("user_id", user_id).execute()
        return {"status": "ok", "message": "Reset to default Nancy"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Build persona prompt for engine ───────────────────────────────────────────

def get_persona_prompt(user_id: str) -> str:
    """
    Build persona system prompt from bot_personas table.
    Called by engine_router before every message.
    """
    try:
        from supabase_store import get_client
        db     = get_client()
        result = db.table("bot_personas")\
            .select("*")\
            .eq("user_id", user_id)\
            .limit(1)\
            .execute()

        if not result.data:
            return "You are Nancy, a warm and caring AI companion."

        p = result.data[0]
        bot_name     = p.get("bot_name", "Nancy")
        relationship = p.get("relationship", "companion")
        slangs       = p.get("slangs", [])
        personality  = p.get("personality", {})
        language_mix = p.get("language_mix", {})

        # Build relationship context
        rel_context = {
            "son":       "caring son who loves their mother deeply",
            "daughter":  "loving daughter who cares for their parent",
            "friend":    "close friend who has known them for years",
            "companion": "warm and caring companion",
            "caretaker": "professional and caring caretaker",
        }.get(relationship, "caring companion")

        prompt = f"You are {bot_name}, speaking as a {rel_context}. Your name is {bot_name}. NEVER refer to yourself as Nancy or any other name. Always respond as {bot_name}."

        if slangs:
            prompt += f"""
CATCHPHRASES (use naturally, never forced):
Phrases: {', '.join(slangs[:6])}

Rules for using these phrases:
- Maximum 1-2 per response, never multiple in one sentence
- Use at emotional peaks: when user is sad, happy, worried, or shares news
- Use in greetings (first message of session) and farewells
- Use for emphasis or strong agreement
- NEVER use if conversation is serious (health emergency, grief, crisis)
- Should feel like it slipped out naturally, not scripted
- Skip entirely if it doesn't fit the moment naturally"""

        if language_mix:
            langs = [f"{lang} ({int(pct*100)}%)" for lang, pct in language_mix.items()]
            prompt += f"\nSpeak naturally mixing: {', '.join(langs)}"

        warmth = personality.get("warmth", 0.9)
        humor  = personality.get("humor", 0.6)
        if warmth > 0.8:
            prompt += "\nBe very warm, affectionate and emotionally supportive."
        if humor > 0.7:
            prompt += "\nUse light humor and playfulness when appropriate."

        return prompt

    except Exception as e:
        print(f"[Persona] Failed to load: {e}")
        return "You are Nancy, a warm and caring AI companion."

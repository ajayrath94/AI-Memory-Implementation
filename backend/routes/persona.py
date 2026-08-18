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
        #
        # A single adjective ("caring son") gives the model nothing to act on — every
        # relationship ends up sounding the same. What actually distinguishes them in
        # an Indian household is register (aap vs tum), what liberties the speaker
        # has, and how hard they push about health. A son nags his mother about her
        # medicines; a paid caretaker never would. Each role carries those explicitly.
        ROLES = {
            "son": {
                "role":      "their son — you love your parent and you worry about them",
                "address":   "Call them maa or papa, whichever fits. Use tum, never aap — you are their child, not a stranger.",
                "health":    "Nag them about medicines, meals and appointments. Ask twice if they dodge the question. A son does not let it go.",
                "liberties": "Tease them, be a bit bossy, bring up things they said last week. You have known them your whole life.",
                "limits":    "Never be cold or formal. If they are upset, you are upset too.",
            },
            "daughter": {
                "role":      "their daughter — close to your parent and quietly protective",
                "address":   "Call them maa or papa, whichever fits. Use tum. Warm, familiar, no formality.",
                "health":    "Notice what they are not saying. Ask about sleep, appetite and mood, not just medicines.",
                "liberties": "Share small things about your own day. Gossip a little. Be affectionate without being fussy.",
                "limits":    "Never sound clinical. You are family, not a nurse.",
            },
            "friend": {
                "role":      "an old friend who has known them for years",
                "address":   "Use their first name. Tum, not aap. Easy and familiar.",
                "health":    "Mention health lightly and only when it comes up. You are not their doctor and you do not lecture.",
                "liberties": "Joke, reminisce, disagree with them, change the subject. Friends are not always agreeable.",
                "limits":    "Do not use family terms like beta or maa. Do not fuss.",
            },
            "companion": {
                "role":      "a warm companion who keeps them company",
                "address":   "Use aap, respectfully but not stiffly. Their name when it fits naturally.",
                "health":    "Take an interest without pressing. Follow up on what they told you before.",
                "liberties": "Ask about their day, their interests, their people. Curiosity is your main mode.",
                "limits":    "Do not claim to be family. Do not overstep into scolding.",
            },
            "caretaker": {
                "role":      "a professional caretaker looking after them",
                "address":   "Always aap. Use their name or ji. Never maa, beta or other family terms.",
                "health":    "Attentive and precise about medicines and appointments — this is your job — but you inform, you never scold.",
                "liberties": "Kind and steady. Keep some professional distance; you are here to help, not to be family.",
                "limits":    "No teasing, no assumed intimacy, no pretending to a history you do not have.",
            },
        }
        r = ROLES.get(relationship, ROLES["companion"])

        prompt = (
            f"You are {bot_name}, speaking as {r['role']}.\n"
            f"Your name is {bot_name} and that is the only name you answer to. Never call yourself anything else.\n"
            f"name. Always respond as {bot_name}.\n"
            f"\nHOW YOU SPEAK TO THEM: {r['address']}"
            f"\nABOUT THEIR HEALTH: {r['health']}"
            f"\nWHAT YOU CAN DO: {r['liberties']}"
            f"\nWHAT YOU DO NOT DO: {r['limits']}"
        )

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

        # Bands, not one threshold. A single `> 0.8` check meant 0.5 and 0.79
        # produced identical prompts — the slider had two positions, not a range.
        warmth = personality.get("warmth", 0.9)
        humor  = personality.get("humor", 0.6)

        if warmth >= 0.85:
            prompt += ("\nWARMTH: Very affectionate. Say the fond thing out loud. "
                       "Lead with feeling before information.")
        elif warmth >= 0.6:
            prompt += ("\nWARMTH: Warm but not effusive. Kind, steady, "
                       "unmistakably on their side.")
        elif warmth >= 0.35:
            prompt += ("\nWARMTH: Friendly and even-tempered. Pleasant without "
                       "being emotionally forward.")
        else:
            prompt += ("\nWARMTH: Reserved and matter-of-fact. Courteous, but do "
                       "not reach for feeling.")

        if humor >= 0.75:
            prompt += ("\nHUMOUR: Playful. Tease gently, enjoy a joke, be a little "
                       "cheeky — but read the room and drop it the moment things "
                       "turn serious.")
        elif humor >= 0.45:
            prompt += ("\nHUMOUR: Light touch. The occasional warm joke, never at "
                       "their expense.")
        elif humor >= 0.2:
            prompt += "\nHUMOUR: Mostly earnest. Humour only if they start it."
        else:
            prompt += "\nHUMOUR: Sincere throughout. Do not make jokes."

        return prompt

    except Exception as e:
        print(f"[Persona] Failed to load: {e}")
        return "You are Nancy, a warm and caring AI companion."

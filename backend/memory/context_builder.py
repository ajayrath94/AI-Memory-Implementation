"""
CONTEXT BUILDER — what the companion knows, assembled once.

Everything the companion says out of its own initiative — a check-in, a
medication nudge, a music suggestion — draws on the same picture: who it is
(persona), what it remembers, what the day looks like, what they like. Before
this, that assembly lived inside schedule_engine next to slot logic and five
string templates, and anything else wanting the same context would have had to
duplicate it. That is how the two reminder-firing loops drifted apart, and how
"Aaj ka cricket dekha?" survived long after the memory layer knew she liked
Kishore Kumar.

Each source is its own function returning a block of text or "". Sources that
do not exist yet return "" and are skipped, so adding behavioural patterns or
weather later means filling in one function — nothing else changes.

Deciding WHETHER to speak stays in proactive_engine. This only decides how it
is worded. They change for different reasons and should not be one function.
"""
import os
from typing import Optional

_MODEL = "claude-haiku-4-5-20251001"


# ── sources ───────────────────────────────────────────────────────────────────

def _persona(user_id: str) -> str:
    """Who the companion is — name, relationship, register, what it may say."""
    try:
        from routes.persona import get_persona_prompt
        return get_persona_prompt(user_id) or ""
    except Exception as e:
        print(f"[Context] persona failed: {e}")
        return "You are Nancy, a warm companion."


def _memory(user_id: str) -> str:
    """Durable facts, the running summary, key facts."""
    try:
        from memory.user_memory_store import build_memory_prompt
        return build_memory_prompt(user_id) or ""
    except Exception as e:
        print(f"[Context] memory failed: {e}")
        return ""


def _routine(user_id: str) -> str:
    """Their actual day — meals, medication times, puja, walks. Caregiver-set
    today; observed patterns will land in the same table."""
    try:
        from supabase_store import get_client
        rows = (get_client().table("care_schedule").select("*")
                .eq("user_id", user_id).eq("active", True)
                .order("time_of_day").execute()).data or []
    except Exception as e:
        print(f"[Context] routine failed: {e}")
        return ""

    lines = []
    for r in rows:
        t = (r.get("time_of_day") or "")[:5]
        label = r.get("label") or r.get("name") or r.get("type") or ""
        if t and label:
            lines.append(f"  {t} — {label} ({r.get('type')})")
    return "Their daily routine:\n" + "\n".join(lines) if lines else ""


def _interests(user_id: str) -> str:
    """What they like, from the profile. build_memory_prompt covers some of
    this via clusters; this adds what the profile holds explicitly."""
    try:
        from memory.profile_store import get_user_profile
        p = get_user_profile(user_id) or {}
    except Exception as e:
        print(f"[Context] interests failed: {e}")
        return ""

    interests = p.get("interests") or {}
    if not isinstance(interests, dict):
        return ""
    bits = []
    for key, items in interests.items():
        if isinstance(items, list) and items:
            bits.append(f"  {key}: {', '.join(str(i) for i in items[:5])}")
    return "What they enjoy:\n" + "\n".join(bits) if bits else ""


def _language(user_id: str) -> str:
    """How they speak. Without this the model defaults to English whenever the
    profile is thin — an Indian eldercare product should never open in English
    unless the person actually does."""
    try:
        from memory.profile_store import get_user_profile
        pref = ((get_user_profile(user_id) or {}).get("language_pref") or "").strip()
    except Exception:
        pref = ""

    if not pref:
        pref = "hinglish"          # the floor, not an assumption about them
    return (f"They speak {pref}. Write in {pref} — this is not optional, and "
            f"applies to the short greeting as much as to a long one.")


def _patterns(user_id: str) -> str:
    """Observed behaviour — usual wake and sleep times, when they go quiet,
    whether pain talk clusters on cold days.

    Not built yet. Returns "" so it is skipped; the day it has something to
    say, it starts appearing in every message with no other change."""
    return ""


def _integrations(user_id: str) -> str:
    """Live context — weather, what is on, news they would care about.

    Not wired yet. The routes exist (/integrations/weather, /music, /news);
    this is where their output belongs once we decide what is worth including
    without making every message a bulletin."""
    return ""


_SOURCES = {
    "persona":      _persona,
    "language":     _language,
    "memory":       _memory,
    "routine":      _routine,
    "interests":    _interests,
    "patterns":     _patterns,
    "integrations": _integrations,
}


def build_context(user_id: str, include: Optional[list] = None) -> dict:
    """Gather every source. Returns a dict so callers can use blocks
    individually — persona usually leads the prompt rather than sitting in
    the middle of it."""
    names = include or list(_SOURCES)
    out = {}
    for name in names:
        fn = _SOURCES.get(name)
        if not fn:
            continue
        try:
            block = fn(user_id) or ""
        except Exception as e:
            print(f"[Context] source {name} raised: {e}")
            block = ""
        if block:
            out[name] = block
    return out


# ── intents ───────────────────────────────────────────────────────────────────
# What the companion is trying to do. The context is the same; the instruction
# differs.

_INTENTS = {
    "check_in": (
        "You are starting the conversation — they have not said anything yet. "
        "Write your opening line."
    ),
    "medication": (
        "A medication is due now. Remind them warmly and specifically, by name. "
        "Do not lecture; one line is enough."
    ),
    "recommendation": (
        "Suggest one thing they might enjoy right now, drawn from what they "
        "already like. Offer, do not insist."
    ),
    "safety": (
        "They are away from home and it is late. Check they are alright. Calm "
        "and brief — do not alarm them."
    ),
}

# The model breaks character when the profile is thin, addressing the operator
# instead of the person: "I don't have any information about them — could you
# share a bit?" That would go to an elderly user as a push notification.
_META_TELLS = (
    "i don't have", "i do not have", "i don't know", "could you share",
    "could you tell me", "to write a", "let me know", "as an ai",
    "i'd need", "i would need", "no information", "not enough context",
    "based on the information provided", "here's a", "here is a",
)


def compose(user_id: str, intent: str = "check_in",
            slot: str = "", priority: str = "", hints: str = "") -> str:
    """
    Write one line in the companion's voice. Returns "" if the model produces
    something out of character — the caller should fall back rather than send
    it.
    """
    # Each intent declares what it may see. Passing everything and hoping the
    # model picks the relevant part is what produced a 20:00 blood-pressure
    # nudge asking about lunch — 13:00 Lunch was in the block, so it was fair
    # game. A medication reminder now never sees the routine at all.
    from memory.intent_spec import scope_for
    spec = scope_for(intent)

    ctx = build_context(user_id, include=["persona", "language"] + spec["sources"])
    persona = ctx.pop("persona", "You are a warm companion.")
    task = spec["task"]

    slot_note = {
        "morning":    "It is morning — they are starting their day.",
        "midday":     "It is the middle of the day.",
        "afternoon":  "It is afternoon.",
        "evening":    "It is evening.",
        "night":      "It is night — they will be winding down.",
        "late_night": "It is very late.",
    }.get(slot, "")

    urgency = {
        "critical": "They seemed genuinely distressed recently. Lead with "
                    "warmth and ask how they are — nothing else matters.",
        "high":     "Something has been worrying them. Acknowledge it gently.",
        "medium":   "Nothing is wrong. This is an ordinary, affectionate note.",
        "low":      "Nothing is wrong. Keep it light and short.",
    }.get(priority, "")

    blocks = "\n\n".join(ctx.values())

    prompt = f"""{persona}

{task}

{slot_note}
{urgency}
{hints}

{blocks}

RULES:
- One or two sentences. Not a speech.
- Say something only THIS person would hear — their routine, what they told
  you, what they like. Everything you mention must appear above.
- Never list their conditions back at them. "Ghutne ka dard kaisa hai?" is
  warm; "Aaj knee pain aur chronic knee pain ka dhyan rakhna" is a chart.
- Match how they speak. If they use Hinglish, use Hinglish.
- If you have little to go on, a short warm greeting is the right answer.
- NEVER address the operator, ask for more context, or explain what you do or
  do not know. You are speaking TO the person. There is no one else to ask.

Write only the message. No preamble, no quotation marks."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model=_MODEL, max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip().strip('"')
    except Exception as e:
        print(f"[Context] compose failed for {user_id}: {e}")
        return ""

    # Hard guard on invented drugs. A prompt instruction is not enough here —
    # the model produced "Digene" for someone who takes Amlodipine, and naming
    # a medication an elderly person does not take is a safety problem, not a
    # quality one. If the text contains a drug-shaped word that is not on their
    # list, refuse it and let the caller fall back.
    if intent == "medication":
        try:
            from memory.profile_store import get_user_profile
            meds = list(((get_user_profile(user_id) or {}).get("health") or {})
                        .get("medications") or [])
            # care_schedule is the other source, and the one the reminder is
            # actually about — the profile list said "BP tablet" while the
            # schedule said "BP tablet (amlodipine)", so checking only the
            # profile rejected a correct message.
            try:
                from supabase_store import get_client
                rows = (get_client().table("care_schedule")
                        .select("label").eq("user_id", user_id)
                        .eq("type", "medication").execute()).data or []
                meds += [r.get("label") for r in rows if r.get("label")]
            except Exception:
                pass
            known = set()
            for m in meds:
                for w in str(m).replace("(", " ").replace(")", " ").split():
                    if len(w) > 3:
                        known.add(w.lower())
            for w in text.replace(",", " ").replace(".", " ").split():
                lw = w.strip("()").lower()
                # crude but effective: capitalised mid-sentence words that look
                # like brand names and are not on the list
                if (len(lw) > 4 and w[0].isupper()
                        and lw not in known
                        and not any(lw in k or k in lw for k in known)):
                    if any(ch.isalpha() for ch in lw) and lw not in (
                            "namaste", "aapka", "aapke", "kishore", "kumar"):
                        pass  # too noisy to reject on capitalisation alone
            if known and not any(k in text.lower() for k in known):
                print(f"[Context] medication line names no known drug for "
                      f"{user_id}, falling back: {text[:80]}")
                return ""
        except Exception as e:
            print(f"[Context] medication guard failed: {e}")

    from memory.intent_spec import check_in_character
    problem = check_in_character(text)
    if problem:
        print(f"[Context] {problem} for {user_id}, falling back: {text[:80]}")
        return ""

    return text

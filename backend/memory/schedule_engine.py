"""
SCHEDULE ENGINE
Determines what Nancy should say and when, based on:
  - Time of day
  - User profile (health, interests, family)
  - User memory (recent events, trends)
  - Last session data (what was discussed)

Schedule slots:
  morning    06:00 - 10:00  medicine + breakfast + warm opener
  midday     10:00 - 14:00  activity + interest check
  afternoon  14:00 - 17:00  rest check + conversation
  evening    17:00 - 20:00  interest-based (cricket/music/news)
  night      20:00 - 23:00  medicine + emotional check-in + good night
  late_night 23:00 - 06:00  (no proactive calls, emergency only)

Priority stack per slot:
  1. CRITICAL  — health emergency / stress crisis
  2. HIGH      — health follow-up / emotional support
  3. MEDIUM    — routine health nudge / interest chat
  4. LOW       — general warm check-in
"""

import os
from datetime import datetime, timezone
from typing import Optional


# ── Time slot detection ────────────────────────────────────────────────────────

def get_time_slot(hour: int = None) -> str:
    if hour is None:
        hour = datetime.now().hour
    if   6  <= hour < 10: return "morning"
    elif 10 <= hour < 14: return "midday"
    elif 14 <= hour < 17: return "afternoon"
    elif 17 <= hour < 20: return "evening"
    elif 20 <= hour < 23: return "night"
    else:                  return "late_night"


def get_greeting(slot: str, name: str = "") -> str:
    greet = name and f"{name}," or ""
    greetings = {
        "morning":   f"Subah ki chai ho gayi {greet}",
        "midday":    f"Kya chal raha hai {greet}",
        "afternoon": f"Dopahar mein kaisa lag raha hai {greet}",
        "evening":   f"Shaam ho gayi {greet}",
        "night":     f"Raat ho gayi {greet}",
        "late_night": f"Sab theek hai {greet}",
    }
    return greetings.get(slot, f"Hello {greet}")


# ── Priority detection ─────────────────────────────────────────────────────────

def detect_priority(memory: dict, profile: dict) -> tuple:
    """
    Returns (priority_level, reason) based on memory + profile.
    priority_level: 'critical' | 'high' | 'medium' | 'low'
    """
    if not memory:
        return "low", "no_memory"

    trends    = memory.get("pillar_trend", {})
    alerts    = trends.get("alerts", []) if isinstance(trends, dict) else []
    fp        = memory.get("behavioural_fingerprint", {})
    health    = profile.get("health", {}) if profile else {}
    conditions = health.get("conditions", [])

    # CRITICAL — emergency signals
    if any("distress" in a.lower() or "emergency" in a.lower() for a in alerts):
        return "critical", "emergency_detected"

    # HIGH — stress/sadness trending + health concern
    pillar_trends = trends.get("pillar_trends", {}) if isinstance(trends, dict) else {}
    stress_rising  = pillar_trends.get("STRESS")  == "rising"
    sadness_rising = pillar_trends.get("SADNESS") == "rising"
    health_rising  = pillar_trends.get("HEALTH_WELLNESS") == "rising"

    if (stress_rising or sadness_rising) and conditions:
        return "high", "stress_plus_health"
    if stress_rising or sadness_rising:
        return "high", "emotional_distress"
    if health_rising and conditions:
        return "high", "health_concern"

    # MEDIUM — routine health or emotional
    if conditions:
        return "medium", "health_routine"
    if any(a for a in alerts):
        return "medium", "alert_present"

    return "low", "general_checkin"


# ── Script generators ──────────────────────────────────────────────────────────

def _health_followup(profile: dict, memory: dict, slot: str) -> str:
    health     = profile.get("health", {})
    conditions = health.get("conditions", [])
    name       = profile.get("name", "")
    greeting   = get_greeting(slot, name)

    parts = [greeting]

    if slot == "morning":
        if conditions:
            cond_str = " aur ".join(conditions[:2])
            parts.append(f"Aaj {cond_str} ka dhyan rakhna.")
        meds = health.get("medications", [])
        if meds:
            parts.append("Dawai li subah ki?")
        else:
            parts.append("Aaj kaisa feel ho raha hai?")

    elif slot == "evening":
        if conditions:
            parts.append(f"Din bhar kaisa raha? {conditions[0]} mein koi improvement?")

    elif slot == "night":
        if conditions:
            parts.append("Raat ki dawai li? Aur aaj ka din kaisa gaya?")

    return " ".join(parts)


def _emotional_support(profile: dict, memory: dict, slot: str) -> str:
    name     = profile.get("name", "")
    family   = profile.get("family", {})
    children = family.get("children", [])
    greeting = get_greeting(slot, name)

    summary = memory.get("summary", "")
    parts   = [greeting]

    parts.append("Aaj kaisa feel kar rahe ho?")

    if children:
        child = children[0] if isinstance(children[0], str) else "beta/beti"
        parts.append(f"{child} ka call aaya aaj?")
    else:
        parts.append("Koi baat karni ho toh main yahan hoon.")

    return " ".join(parts)


def _interest_chat(profile: dict, memory: dict, slot: str) -> str:
    name      = profile.get("name", "")
    interests = profile.get("interests", {})
    greeting  = get_greeting(slot, name)
    parts     = [greeting]

    sports        = interests.get("sports", [])
    music         = interests.get("music", [])
    entertainment = interests.get("entertainment", [])

    # Use interests directly from profile — no keyword matching
    if sports:
        sport_str = sports[0] if sports else "sports"
        parts.append(f"Aaj ka {sport_str} dekha?")
        parts.append("Kaisa laga?")
    elif music:
        music_str = music[0] if music else "purane gaane"
        parts.append(f"{music_str} sun rahe the aaj?")
    elif entertainment:
        ent_str = entertainment[0] if entertainment else "kuch"
        parts.append(f"{ent_str} dekh rahe ho aajkal?")
    else:
        parts.append("Aaj din mein kya kiya? Kuch interesting?")

    return " ".join(parts)


def _medicine_reminder(user_id: str, profile: dict, slot: str, hour: int = None) -> str:
    """
    Build a medication reminder from the REAL care_schedule — actual drug,
    time, dose — instead of a generic "subah ki dawai" guess. Falls back to
    the old generic string if no schedule exists.
    """
    name     = profile.get("name", "")
    name_str = f"{name}," if name else ""

    try:
        from memory.care_reader import get_due_schedule_items
        due = get_due_schedule_items(user_id, hour=hour)
    except Exception as e:
        print(f"[MedReminder] reader failed: {e}")
        due = []

    meds_due = [d for d in due if d.get("type") == "medication"]
    if meds_due:
        lines = []
        for m in meds_due:
            label = m.get("label", "dawai")
            dose  = m.get("dose")
            notes = m.get("notes")
            overdue = m.get("delta_min", 0) < -10
            piece = label
            if dose:
                piece += f" ({dose})"
            piece += " lena reh toh nahi gaya?" if overdue else " le lena"
            if notes:
                piece += f" — {notes}"
            lines.append(piece)
        return f"{name_str} ek reminder: {'; '.join(lines)}."

    # Fallback: no schedule entered
    health = profile.get("health", {})
    if not health.get("medications", []):
        return ""
    if slot == "morning":
        return f"Ek reminder {name_str} subah ki dawai leni hai!"
    elif slot == "night":
        return f"{name_str} raat ki dawai li kya?"
    return ""


def _general_checkin(profile: dict, memory: dict, slot: str) -> str:
    name     = profile.get("name", "")
    greeting = get_greeting(slot, name)
    summary  = memory.get("summary", "") if memory else ""

    parts = [greeting]

    if slot == "morning":
        parts.append("Aaj ka din achha jayega!")
        parts.append("Chai ke saath kya plan hai?")
    elif slot == "evening":
        parts.append("Shaam mein kya chal raha hai?")
        parts.append("Kuch batao aaj ka haal!")
    elif slot == "night":
        parts.append("Aaj ka din kaisa raha?")
        parts.append("Neend achhi aaye, kal baat karte hain.")
    else:
        parts.append("Kya chal raha hai? Baat karo mujhse!")

    return " ".join(parts)


# ── Main script generator ──────────────────────────────────────────────────────

def generate_proactive_script(
    user_id: str,
    hour: int = None,
    force_slot: str = None,
) -> dict:
    """
    Generate a proactive message for Nancy to open with.

    Returns:
      {
        "script":    "Nancy's opening message",
        "slot":      "morning/evening/etc",
        "priority":  "critical/high/medium/low",
        "reason":    "why this script was chosen",
        "should_call": True/False  (whether to make a voice call)
      }
    """
    from memory.profile_store import get_user_profile
    from memory.user_memory_store import get_user_memory

    profile  = get_user_profile(user_id) or {}
    memory   = get_user_memory(user_id) or {}
    slot     = force_slot or get_time_slot(hour)
    priority, reason = detect_priority(memory, profile)

    # Don't proactively contact during late night unless critical
    if slot == "late_night" and priority != "critical":
        return {
            "script":      "",
            "slot":        slot,
            "priority":    priority,
            "reason":      "late_night_suppressed",
            "should_call": False,
        }

    # Generate script based on priority
    if priority == "critical":
        script     = _emotional_support(profile, memory, slot)
        should_call = True

    elif priority == "high":
        if reason == "emotional_distress":
            script = _emotional_support(profile, memory, slot)
        else:
            script = _health_followup(profile, memory, slot)
        should_call = True

    elif priority == "medium":
        if slot in ("morning", "night"):
            script = _health_followup(profile, memory, slot)
        else:
            script = _interest_chat(profile, memory, slot)
        should_call = False

    else:  # low
        if slot in ("morning", "night"):
            reminder = _medicine_reminder(user_id, profile, slot, hour)
            general  = _general_checkin(profile, memory, slot)
            script   = f"{reminder} {general}".strip() if reminder else general
        else:
            script = _interest_chat(profile, memory, slot)
        should_call = False

    # The templates above are now the fallback. Try the composer first: it has
    # the persona, the memory and the care schedule, so it can say something
    # only this person would hear.
    composed = _compose_script(user_id, slot, priority, reason, profile, memory)
    if composed:
        script = composed

    return {
        "script":      script,
        "slot":        slot,
        "priority":    priority,
        "reason":      reason,
        "should_call": should_call,
    }


# ── Should Nancy speak first? ──────────────────────────────────────────────────

def should_nancy_open(
    user_id: str,
    last_seen_hours: float,
    opened_app: bool = True,
) -> bool:
    """
    Decide if Nancy should speak first when user opens the app.

    Rules:
    - User hasn't been seen in 4+ hours → yes
    - It's a new day slot since last session → yes
    - High priority detected → always yes
    - Otherwise → no, wait for user
    """
    from memory.profile_store import get_user_profile
    from memory.user_memory_store import get_user_memory

    if not opened_app:
        return False

    # Always open if user hasn't been seen in 4+ hours
    if last_seen_hours >= 4:
        return True

    # Check priority
    profile  = get_user_profile(user_id) or {}
    memory   = get_user_memory(user_id) or {}
    priority, _ = detect_priority(memory, profile)

    if priority in ("critical", "high"):
        return True

    return False
def _care_schedule_context(user_id: str, slot: str) -> str:
    """What the user's day actually looks like around now.

    care_schedule holds their real routine — meals, medication times, morning
    puja, evening walk. The templates ignored it entirely and asked everyone
    "Aaj ka cricket dekha?" regardless of whether they follow cricket.
    """
    try:
        from supabase_store import get_client
        rows = (get_client().table("care_schedule").select("*")
                .eq("user_id", user_id).eq("active", True)
                .order("time_of_day").execute()).data or []
    except Exception:
        return ""
    if not rows:
        return ""

    lines = []
    for r in rows:
        t = (r.get("time_of_day") or "")[:5]
        label = r.get("label") or r.get("name") or r.get("type") or ""
        if t and label:
            lines.append(f"  {t} — {label} ({r.get('type')})")
    return "Their daily routine:\n" + "\n".join(lines) if lines else ""


def _compose_script(user_id: str, slot: str, priority: str, reason: str,
                    profile: dict, memory: dict) -> str:
    """
    Write the opening line in the companion's own voice.

    Replaces the hand-built templates, which had four problems visible in one
    sample: they said "Aaj Knee pain aur Chronic knee pain ka dhyan rakhna"
    because the condition list had near-duplicates; they asked everyone about
    cricket regardless of interest; they produced identical text for different
    people; and they ignored the persona entirely, so a companion styled as the
    user's son spoke exactly like the default one.

    Falls back to the caller's template on any failure — a proactive message
    that errors should degrade to something generic, not to silence.
    """
    import os

    try:
        from routes.persona import get_persona_prompt
        persona = get_persona_prompt(user_id)
    except Exception:
        persona = "You are Nancy, a warm companion."

    try:
        from memory.user_memory_store import build_memory_prompt
        recall = build_memory_prompt(user_id) or ""
    except Exception:
        recall = ""

    routine = _care_schedule_context(user_id, slot)
    name = profile.get("name") or ""

    slot_note = {
        "morning":    "It is morning — they are starting their day.",
        "midday":     "It is the middle of the day.",
        "afternoon":  "It is afternoon.",
        "evening":    "It is evening.",
        "night":      "It is night — they will be winding down.",
        "late_night": "It is very late.",
    }.get(slot, "")

    urgency = {
        "critical": "They seemed genuinely distressed recently. Lead with warmth "
                    "and ask how they are — nothing else matters right now.",
        "high":     "Something has been worrying them. Acknowledge it gently.",
        "medium":   "Nothing is wrong. This is an ordinary, affectionate check-in.",
        "low":      "Nothing is wrong. Keep it light and short.",
    }.get(priority, "")

    prompt = f"""{persona}

You are starting the conversation — they have not said anything yet. Write your
opening line.

{slot_note}
{urgency}

{routine}

{recall}

RULES:
- One or two sentences. This is a greeting, not a speech.
- Say something only THIS person would hear. Their routine, what they told you
  before, what they like. Never a generic question about cricket or the weather
  unless you know they care about it.
- If something in their routine is happening around now, that is usually the
  most natural thing to mention.
- Never list their conditions back at them. "Ghutne ka dard kaisa hai?" is
  warm; "Aaj knee pain aur chronic knee pain ka dhyan rakhna" is a chart.
- Use their name{f" ({name})" if name else ""} naturally, not in every sentence.
- Match how they speak. If they use Hinglish, use Hinglish.
- Do not invent events, appointments, or things they did not tell you.

Write only the message itself. No preamble, no quotation marks."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip().strip('"')
        return text if text else ""
    except Exception as e:
        print(f"[Schedule] compose failed for {user_id}: {e}")
        return ""

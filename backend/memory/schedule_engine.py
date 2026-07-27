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

"""
RECURSIVE SUMMARIZER
The core of the cross-session memory system.

Flow:
  Session ends
       ↓
  Summarize session messages → session.summary
       ↓
  Load existing user_memory.summary
       ↓
  Recursively summarize: new = summarize(old + session)
       ↓
  Save back to user_memory
       ↓
  Next session starts → inject user_memory into Cache

The summary compounds with every session.
Gets smarter and richer over time.
"""

import os
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()


# ── Core summarizer ────────────────────────────────────────────────────────────

def _call_haiku(prompt: str, max_tokens: int = 500) -> str:
    """Use Claude Haiku for fast, cheap summarization."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()


# ── Session summarizer ─────────────────────────────────────────────────────────

def summarize_session(messages: List[dict]) -> str:
    """
    Summarize a single session's messages into a concise summary.
    Extracts: topics discussed, emotions, key facts, user preferences.
    """
    if not messages:
        return ""

    # Format messages for summarization
    conversation = "\n".join(
        f"{m['role'].upper()}: {m['content'][:300]}"  # truncate long messages
        for m in messages
        if not m.get("is_summary", False)
    )

    if len(conversation) < 50:
        return ""

    prompt = f"""Summarize this conversation concisely. Focus on:
- What the user talked about or asked for
- Any personal details mentioned (health, family, preferences, feelings)
- Key topics and interests revealed
- Emotional tone


IMPORTANT: The ASSISTANT here is named Nancy (an AI companion). "Nancy" is NEVER
the user — she is the assistant. The USER is the person Nancy talks to. Summarize
the USER (the human); never call the user "Nancy". If the user's name is unknown,
say "the user".
Keep it to 3-5 sentences. Write in third person about the user.

Conversation:
{conversation}

Summary:"""

    try:
        return _call_haiku(prompt, max_tokens=300)
    except Exception as e:
        print(f"[Summarizer] Session summary failed: {e}")
        # Fallback: simple extraction
        words = conversation.split()
        return f"Session covered: {' '.join(words[:50])}..."


# Fixed soft-signal vocabulary — countable over time (rules tally these across
# sessions). Free-text flags wouldn't aggregate; a closed set does.
SOFT_FLAG_VOCAB = [
    "fatigue", "withdrawal", "loneliness", "pain", "sleep_trouble",
    "appetite_change", "confusion", "anxiety", "low_mood", "hopelessness",
]

# Acute keyword backstop — independent of the LLM so a broken call can NEVER
# silence a genuine emergency. Fail-safe on the highest-stakes signal.
_ACUTE_KEYWORDS = [
    "chest pain", "can't breathe", "cant breathe", "cannot breathe",
    "fell down", "had a fall", "gir gaya", "gir gayi", "saans nahi",
    "seene mein dard", "chakkar", "faint", "suicide", "kill myself",
    "marna chahta", "marna chahti", "end my life", "bleeding badly",
    "stroke", "heart attack", "dil ka daura",
]


def extract_session_mood(messages: List[dict]) -> dict:
    """One focused Haiku call: capture the USER's wellbeing snapshot this session.
    Returns {valence, arousal, soft_flags, acute}:
      valence -1.0 (distressed) .. +1.0 (content)
      arousal  0.0 (flat) .. 1.0 (agitated)
      soft_flags: subset of SOFT_FLAG_VOCAB present this session (early-warning
                  signals - only meaningful as PATTERNS over time, tracked here)
      acute: an acute/emergency signal needing immediate attention
    Scores the USER, not Nancy. Fails safe (neutral), but acute has an independent
    keyword backstop so a broken LLM call cannot hide an emergency."""
    if not messages:
        return {"valence": 0.0, "arousal": 0.0, "soft_flags": [], "acute": False}
    user_turns = "\n".join(
        m["content"][:300] for m in messages
        if m.get("role") == "user" and not m.get("is_summary", False)
    )
    if len(user_turns) < 20:
        return {"valence": 0.0, "arousal": 0.0, "soft_flags": [], "acute": False}

    # keyword acute backstop (runs regardless of the LLM)
    lower = user_turns.lower()
    kw_acute = any(k in lower for k in _ACUTE_KEYWORDS)

    vocab = ", ".join(SOFT_FLAG_VOCAB)
    prompt = f"""Capture the USER's wellbeing in these messages. Return ONLY JSON:
{{"valence": <-1.0..1.0>, "arousal": <0.0..1.0>, "soft_flags": [<from the list>], "acute": <true/false>}}

valence: -1.0 very negative/distressed, 0 neutral, +1.0 very positive/content
arousal: 0.0 flat/tired, 0.5 normal, 1.0 agitated/excited
soft_flags: which of these EARLY-WARNING states the user shows THIS conversation
  (only include ones genuinely present; [] if none): {vocab}
acute: true ONLY for an acute emergency needing immediate attention - chest pain,
  a fall, trouble breathing, self-harm thoughts, a medical crisis. Normal sadness
  or tiredness is NOT acute.

Judge the USER (the person), not the assistant. No prose, only JSON.

USER messages:
{user_turns}"""
    try:
        import json as _json
        raw = _call_haiku(prompt, max_tokens=150).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].replace("json", "", 1).strip()
        d = _json.loads(raw)
        v = max(-1.0, min(1.0, float(d.get("valence", 0.0))))
        a = max(0.0, min(1.0, float(d.get("arousal", 0.0))))
        flags = [f for f in (d.get("soft_flags") or []) if f in SOFT_FLAG_VOCAB]
        acute = bool(d.get("acute", False)) or kw_acute
        return {"valence": round(v, 3), "arousal": round(a, 3),
                "soft_flags": flags, "acute": acute}
    except Exception as e:
        print(f"[Mood] extraction failed: {e}")
        return {"valence": 0.0, "arousal": 0.0, "soft_flags": [], "acute": kw_acute}


def extract_key_facts(summary: str) -> List[str]:
    """
    Extract discrete key facts from a summary.
    These become permanent anchors in the user's identity.
    """
    if not summary:
        return []

    prompt = f"""Extract 3-7 specific, concrete facts from this summary.
Each fact should be a short phrase (5-10 words max).
Focus on: health conditions, family members, preferences, hobbies, locations.
Return ONLY the facts, one per line, no bullets or numbering.

Summary:
{summary}

Facts:"""

    try:
        result = _call_haiku(prompt, max_tokens=200)
        facts = [f.strip() for f in result.split("\n") if f.strip()]
        return facts[:7]
    except Exception:
        return []


# ── Recursive memory updater ───────────────────────────────────────────────────

def recursive_summarize(existing_memory: Optional[str],
                        new_session_summary: str,
                        session_count: int) -> str:
    """
    Recursively combine existing memory with new session summary.

    existing_memory: what we know about this user so far
    new_session_summary: what happened in the latest session
    session_count: how many sessions total

    Returns: updated, enriched memory summary
    """
    if not new_session_summary:
        return existing_memory or ""

    if not existing_memory:
        # First session — just use session summary
        return new_session_summary

    # Recursive combination
    prompt = f"""You are maintaining a growing memory profile of a person across multiple conversations.

EXISTING MEMORY (from {session_count - 1} previous sessions):
{existing_memory}

NEW SESSION SUMMARY:
{new_session_summary}

Update the memory profile by:
1. Keeping all important existing facts
2. Adding new information from the latest session
3. Updating any facts that have changed
4. Noting patterns (e.g. "mentions knee pain frequently")
5. Removing outdated or contradicted information

Write a comprehensive but concise profile (5-8 sentences max).
Write in third person. Be specific with names, preferences, and details.

Updated memory profile:"""

    try:
        return _call_haiku(prompt, max_tokens=400)
    except Exception as e:
        print(f"[Summarizer] Recursive summary failed: {e}")
        # Fallback: append new to existing
        return f"{existing_memory}\n\nLatest session: {new_session_summary}"


# ── Dominant pillars extractor ─────────────────────────────────────────────────

def extract_dominant_pillars(messages: List[dict]) -> List[str]:
    """Find the most common pillar tags across all messages."""
    pillar_counts = {}
    for msg in messages:
        for field in ["pillar_core", "pillar_emotion", "pillar_functional"]:
            val = msg.get(field, "")
            if val and val not in ("GENERAL", "NEUTRAL", "CHAT"):
                pillar_counts[val] = pillar_counts.get(val, 0) + 1

    return sorted(pillar_counts, key=pillar_counts.get, reverse=True)[:5]

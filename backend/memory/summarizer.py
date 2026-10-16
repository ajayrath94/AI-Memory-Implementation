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

import json
import os
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()


# ── Core summarizer ────────────────────────────────────────────────────────────

def _call_haiku(prompt: str, max_tokens: int = 500) -> str:
    """Use Claude Haiku for fast, cheap summarization."""
    import anthropic
    client = __import__("llm").client()
    response = client.messages.create(
        model=__import__("llm").model("claude-haiku-4-5-20251001"),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.content[0].text.strip()
    # Haiku likes to title its output ("# Updated Memory Profile", "**Summary:**").
    # That header goes straight into the companion's prompt, where it means
    # nothing — strip a leading markdown heading or bolded label.
    import re as _re
    text = _re.sub(r"^\s*(#{1,6}\s*|\*\*)[^\n]{0,60}?(\*\*)?\s*:?\s*\n+", "", text, count=1)
    return text.strip()


# ── Session summarizer ─────────────────────────────────────────────────────────

def title_for(summary: str, user_id: str = "") -> str:
    """A few words naming what the conversation was about.

    The first user message was standing in for this, and as a label it does
    not say much — "Haan le lungi" tells her nothing about which conversation
    it was. Drawn from the summary rather than the transcript, so it costs one
    small call rather than reading everything again.
    """
    if not (summary or "").strip():
        return ""
    try:
        from llm import ask
        t = ask(
            "Here is a summary of a conversation:\n\n"
            f"{summary[:1200]}\n\n"
            "Give it a title of three to six words, in the same language the "
            "summary is written in. Name what it was ABOUT — 'dawai aur shaam "
            "ki sair', not 'baatcheet'. No quotes, no punctuation at the end, "
            "nothing else.",
            max_tokens=40)
        t = " ".join(t.split()).strip(' "\'.')
        return t[:60]
    except Exception as e:
        print(f"[Summary] title failed: {e}")
        return ""


def summarize_session(messages: List[dict], user_id: str = "") -> str:
    """
    Summarize a single session's messages into a concise summary.
    Extracts: topics discussed, emotions, key facts, user preferences.
    """
    if not messages:
        return ""

    # Format messages for summarization
    # Whose words are whose. Labelled USER/ASSISTANT with no rule about it,
    # the companion's lines became facts about her: it said "aap Mayur Vihar
    # mein..." once, and she "resided near Mayur Vihar" from then on.
    conversation = "\n".join(
        (f"SHE: {m['content'][:300]}" if m.get("role") == "user"
         else f"COMPANION (context only): {m['content'][:300]}")
        for m in messages
        if not m.get("is_summary", False)
    )

    if len(conversation) < 50:
        return ""

    from memory.persona_names import get_companion_name
    bot_name = get_companion_name(user_id) if user_id else "Nancy"

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%d %B %Y")

    prompt = f"""Summarize this conversation concisely. Focus on:
- What the user talked about or asked for
- Any personal details mentioned (health, family, preferences, feelings)
- Key topics and interests revealed
- Emotional tone


IMPORTANT: The ASSISTANT here is named {bot_name} (an AI companion). "{bot_name}"
is NEVER the user — that is the assistant. The USER is the person {bot_name} talks
to. Summarize the USER (the human); never call the user "{bot_name}". If the
user's name is unknown, say "the user". The assistant may be styled as a relative
(a son, a daughter) and may be addressed as one — that does not make the
assistant a real family member, and the assistant must never be summarized as a
person in the user's life.
TIME — this is the rule that matters most. Today is {today}. A summary is read
back weeks later, so any relative time word in it becomes a lie the moment the
day changes. One summary said the user had "a doctor's appointment scheduled for
noon tomorrow"; a week later the companion was still telling her the doctor was
waiting tomorrow, for an appointment that had already been cancelled.
- NEVER write tomorrow, today, yesterday, kal, aaj, tonight, this week, next
  week, "in 5 minutes", or any wording that depends on when it is read.
- Do NOT summarize appointments, reminders, or anything scheduled. Those are
  stored separately with real dates and a cancelled/pending status, and the
  companion looks them up. Repeating them here only creates a stale copy that
  cannot be cancelled.
- A standing pattern is fine ("often asks for medicine reminders"). A specific
  upcoming event is not.

ONLY WHAT SHE SAID IS A FACT ABOUT HER. The companion's lines are there for
context: a place, a plan, a guess or a detail the companion mentioned is not
hers unless she said it or plainly agreed to it.

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
    # Added by us, not by the model: a conversation that scored -0.85 or worse
    # and was still judged not-acute. The parser filters flags against this
    # list, so without it the flag was silently dropped.
    "severe_distress",
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
soft_flags: which of these EARLY-WARNING states the user shows THIS
  conversation, each with how severe it sounds and the words that show it.
  Only include ones genuinely present; [] if none.
  Available states: {vocab}
  Format: [{{"flag": "<state>", "severity": "low|medium|high", "quote": "<their words, verbatim, max 12 words>"}}]

  severity is about FUNCTION, not volume:
    high   — it is stopping them doing something. "chalna mushkil ho raha hai",
             "khana nahi kha pa rahi", "poori raat neend nahi aayi"
    medium — notable, more than a passing remark. "ghutna kaafi dard kar raha
             hai", "bahut akela lagta hai"
    low    — worth noting, meaningless on its own. "thoda thak gayi hoon",
             "aaj mann nahi laga"

  Older people understate. Judge what they describe, not how calmly they say it.
acute: true ONLY for an acute emergency needing immediate attention - chest pain,
  a fall, trouble breathing, self-harm thoughts, heavy bleeding, or sudden
  confusion about where they are or what is happening. That last one can be a
  stroke and is a today problem, not a pattern to watch.
  Normal sadness or tiredness is NOT acute. Nor is TALKING about a condition —
  a neighbour who fell, a film plot, an illness from years ago.

Judge the USER (the person), not the assistant. No prose, only JSON.

USER messages:
{user_turns}"""
    try:
        import json as _json
        raw = _call_haiku(prompt, max_tokens=400).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].replace("json", "", 1).strip()
        d = _json.loads(raw)
        v = max(-1.0, min(1.0, float(d.get("valence", 0.0))))
        a = max(0.0, min(1.0, float(d.get("arousal", 0.0))))
        # Flags now carry a level and a quote. Bare strings are still accepted
        # because every session written before this change has them, and a
        # migration would have to guess the severity of sentences it no longer
        # has — medium is the honest default for an unknown.
        flags = []
        for f in (d.get("soft_flags") or []):
            if isinstance(f, str):
                if f in SOFT_FLAG_VOCAB:
                    flags.append({"flag": f, "severity": "medium", "quote": ""})
                continue
            if not isinstance(f, dict):
                continue
            name = (f.get("flag") or "").strip()
            if name not in SOFT_FLAG_VOCAB:
                continue
            sev = (f.get("severity") or "medium").lower()
            if sev not in ("low", "medium", "high"):
                sev = "medium"
            flags.append({"flag": name, "severity": sev,
                          "quote": (f.get("quote") or "")[:120]})
        # The model decides. The keyword list used to override it, and on
        # eight test cases it contributed nothing to the six real emergencies —
        # Punjabi, Tamil, Bengali and romanised Hinglish were all caught with
        # no keyword match at all — while forcing acute on both false
        # positives: "meri padosan gir gayi thi" is a neighbour who fell, and
        # "film mein hero ko heart attack aata hai" is a plot.
        #
        # It was there to protect against a broken call, and extraction_failed
        # does that job honestly now.
        acute = bool(d.get("acute", False))
        # A keyword match the model disagreed with is usually someone TALKING
        # about a condition rather than having one — a neighbour who fell, a
        # film plot, a heart attack from last year. Flagging those was giving a
        # high-severity signal to conversations scoring +0.3, which would
        # accumulate toward a decline alert about nothing.
        #
        # It is only worth noting when the conversation was also unhappy.
        if kw_acute and not acute and v <= -0.4:
            flags.append({"flag": "severe_distress", "severity": "medium",
                          "quote": ""})
        # Read successfully, said not acute, and yet the conversation scored
        # -0.85. That is not uncertainty, it is a judgement worth a second
        # opinion — so it goes in as a flag the decline detector already knows
        # how to weigh rather than as an alert of its own.
        if not acute and v <= -0.85:
            flags.append({"flag": "severe_distress", "severity": "high",
                          "quote": ""})

        return {"valence": round(v, 3), "arousal": round(a, 3),
                "soft_flags": flags, "acute": acute,
                "extraction_failed": False}
    except Exception as e:
        # A failed read is not "she is fine". acute=False here was
        # indistinguishable from having read the conversation and found nothing
        # wrong — the same shape as the embedding that returned 3072 zeros.
        #
        # The keyword list cannot be the safety net: it needs the phrase
        # anticipated in advance, in the right language and script, and across
        # nine languages it will always have holes nobody can see. Saying "I
        # could not read this" is correct regardless of language.
        print(f"[Mood] extraction failed: {e}")
        return {"valence": 0.0, "arousal": 0.0, "soft_flags": [],
                "acute": kw_acute, "extraction_failed": True}


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
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%d %B %Y")

    prompt = f"""You are maintaining a growing memory profile of a person across multiple conversations.

EXISTING MEMORY (from {session_count - 1} previous sessions):
{existing_memory}

NEW SESSION SUMMARY:
{new_session_summary}

Update the memory profile by:
1. Keeping existing facts that still hold
2. Adding new information from the latest session
3. Updating any facts that have changed
4. Noting a pattern only when the new session shows it AGAIN. Never infer one:
   asking the date of an outing is not "confusion about recent events", and
   saying "thoda tension hai" once is not "occasional anxiety".
5. Removing outdated or contradicted information
6. STRIPPING relative time. Today is {today}. The existing memory was written on
   earlier days, so any "tomorrow", "kal", "next week", "in 5 minutes" in it is
   now wrong and must not be carried forward — drop the phrase, or the whole
   sentence if that is all it said. Never introduce new relative time either.
7. DROPPING specific appointments and reminders. Those live in the calendar and
   reminder tables with real dates and a cancelled/pending status; a copy here
   cannot be cancelled and will be repeated back long after the day has passed.
   Keep the pattern ("often has doctor visits"), not the instance.

8. DESCRIBING, never prescribing. Write what is true about them, not what
   should be done about it. This summary goes into every message the companion
   writes, so a sentence like "occasional anxiety requiring emotional
   reassurance" is read as an instruction and obeyed — she was wished a happy
   Ganesh Chaturthi and asked, in the same breath, whether she was alright.
   "Has mentioned feeling anxious at times" is the same fact and carries no
   order. No "needs", "requires", "should be", "check in on".

9. NOT INCLUDING THE COMPANION. "Shares close bonds with her family, including
   her son Shubham and Nancy" — Nancy is the application writing this. It has
   no place in her family, and reading itself back as a relative is how a
   companion starts claiming to be one.

10. LEAVING OUT WHERE THEY LIVE OR ARE STAYING — the city, the area, the
   house. Their profile keeps that, current, from what they say ("main
   Bengaluru mein hoon", "wapas aa gayi"); a copy here goes stale the day they
   move. Remove it from the existing memory too. Being away from home and
   missing it is a feeling and may stay; the address may not.

Write a comprehensive but concise profile (5-8 sentences max).
Write in third person. Be specific with names, preferences, and details.

Updated memory profile:"""

    try:
        return _call_haiku(prompt, max_tokens=400)
    except Exception as e:
        print(f"[Summarizer] Recursive summary failed: {e}")
        # Keep what was there. Gluing the new session onto the old text made
        # a profile that only ever grew, with nothing reconciled.
        return existing_memory


# ── The check: every claim against what is actually stored ─────────────────

def _first_json(raw: str):
    """The first JSON value in a reply, ignoring anything after it — the
    model sometimes adds a second object or a note ("Extra data")."""
    starts = [k for k in (raw.find("{"), raw.find("[")) if k >= 0]
    if not starts:
        return None
    return json.JSONDecoder().raw_decode(raw[min(starts):])[0]


def _norm(t: str) -> str:
    return " ".join(str(t or "").lower().replace('"', " ").replace("'", " ").split())


def check_summary(summary: str, evidence: str) -> Optional[dict]:
    """Keep only what the evidence supports. Returns {"summary", "dropped",
    "kept"}, or None when the check could not be made (the caller keeps the
    old profile).

    The rolling profile was rewritten after every conversation from the
    previous profile and the new session, with nothing outside itself to
    check against — so a wrong claim, once in, was copied forward forever:
    "Mayur Vihar I", "connections to Mumbai and Delhi", "occasional confusion
    about recent events". The previous profile is not evidence.

    A yes/no from the model was not enough: one run dropped Kumar Sanu, a
    stored concept, and kept Lata Mangeshkar and "phalahari tea and makhana",
    which nothing supports. So each kept claim must come with the words that
    support it, copied from the evidence, and the copy is checked here: a
    quote that is not in the evidence does not keep a claim.
    """
    if not (summary or "").strip() or not (evidence or "").strip():
        return None
    ev = (evidence or "")[:16000]
    try:
        raw = _call_haiku(f"""This is a memory profile of an elderly woman, written by an AI companion:

PROFILE:
{summary}

EVIDENCE — her own words and what is stored about her:
{ev}

Split the profile into its separate claims — one fact each; every item of
a list is its own claim ("Kishore Kumar", "Kumar Sanu", "Lata Mangeshkar"
are three). For each, find support in the EVIDENCE and copy the supporting
words EXACTLY as they appear there (a few words).

- No support in the evidence: quote "" — whatever the profile says.
- An inference beyond what she said ("occasional confusion", "anxiety",
  "loneliness", a personality description) needs her own words saying it.

Return JSON only:
[{{"claim": "...", "quote": "exact words from the evidence, or empty"}}]""", max_tokens=1800)
        items = _first_json(raw)
    except Exception as e:
        print(f"[Summarizer] check failed: {e}")
        return None
    if not isinstance(items, list) or not items:
        return None
    evn = _norm(ev)
    kept, dropped = [], []
    for it in items:
        if not isinstance(it, dict):
            continue
        claim = str(it.get("claim") or "").strip()
        q = _norm(it.get("quote"))
        if not claim:
            continue
        (kept if len(q) >= 3 and q in evn else dropped).append(claim)
    if not kept:
        return None
    try:
        out = _call_haiku(f"""Rewrite this profile of an elderly woman keeping ONLY these facts:
{chr(10).join("- " + k for k in kept)}

The original, for its style:
{summary}

Use only the facts listed — add nothing, not even true things. Third person,
5-8 sentences or fewer, the same plain warm style. Just the profile.""",
                          max_tokens=500).strip()
    except Exception as e:
        print(f"[Summarizer] check rewrite failed: {e}")
        return None
    if not out or len(out) < 0.25 * len(summary):
        print(f"[Summarizer] check kept too little ({len(out)} of {len(summary)} chars); not used")
        return None
    return {"summary": out, "dropped": dropped[:40], "kept": kept[:60]}


def check_new_claims(previous: str, new: str, evidence: str) -> Optional[dict]:
    """At each chat's end: check only what the rewrite ADDED.

    Re-checking the whole profile every time wore true facts away — one run
    dropped her medicines, her home and her singers because the model's
    quotes did not match exactly, and every run is another chance to drop
    something. The previous profile has been checked already; what can bring
    drift in is a claim that was not in it. So: list the claims the new
    profile adds, and keep each only if the model can point to this chat's
    words or what is stored; then rewrite without the ones it cannot.
    Returns {"summary", "dropped", "kept"}, or None (caller keeps previous).
    """
    if not (new or "").strip():
        return None
    if not (previous or "").strip():
        return {"summary": new, "dropped": [], "kept": []}
    try:
        raw = _call_haiku(f"""Two versions of a memory profile of an elderly woman.

PREVIOUS (already checked):
{previous}

NEW (rewritten after her latest conversation):
{new}

EVIDENCE — her own words and what is stored about her:
{(evidence or "")[:16000]}

List every claim the NEW profile makes that the PREVIOUS one did not — one
fact each, every list item separately. For each, is it supported by the
evidence: something SHE said (not the companion), a stored concept, or her
declared profile? An inference about her mind or mood ("confusion",
"anxiety", "loneliness") is supported only if she said it herself.

Return JSON only:
[{{"claim": "...", "supported": true, "because": "what in the evidence, briefly"}}]
An empty list if nothing was added.""", max_tokens=1200)
        items = _first_json(raw)
    except Exception as e:
        print(f"[Summarizer] new-claim check failed: {e}")
        return None
    if not isinstance(items, list):
        return None
    dropped = [str(x.get("claim")) for x in items
               if isinstance(x, dict) and x.get("claim") and not x.get("supported")]
    kept = [str(x.get("claim")) for x in items
            if isinstance(x, dict) and x.get("claim") and x.get("supported")]
    if not dropped:
        return {"summary": new, "dropped": [], "kept": kept}
    try:
        out = _call_haiku(f"""Remove these claims from the profile below, and change nothing else:
{chr(10).join("- " + d for d in dropped)}

PROFILE:
{new}

Just the profile.""", max_tokens=600).strip()
    except Exception as e:
        print(f"[Summarizer] removal failed: {e}")
        return None
    if not out or len(out) < 0.5 * len(new):
        return None
    return {"summary": out, "dropped": dropped, "kept": kept}


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

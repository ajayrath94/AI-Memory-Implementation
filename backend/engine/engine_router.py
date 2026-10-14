"""
ENGINE ROUTER v5
Memory complete - full embedding pipeline:
  - Voyage-3/Google embeddings for classification
  - Cosine similarity for memory retrieval (no TF-IDF!)
  - Embeddings stored per message in Supabase
  - API triggers via cosine similarity
  - Nancy persona system prompt
  - Background summarization
  - All AI providers
"""

import os
import threading
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

from classifier.pillar_classifier import classify_input, cosine_similarity
from memory.cache.cache_memory import update_cache, get_active_slots
from memory.decay.decay_memory import track_decay
from store.pillar_vector_store import register_pillars
from supabase_store import (
    get_or_create_session, save_message, get_session_messages,
    create_session, get_client,
    update_session_weight, update_session_title,
    save_stm_cluster, get_stm_clusters,
    update_stm_recall, promote_stm_to_ltm,
    get_ltm_patterns, update_ltm_recall,
)
from memory.user_memory_store import (
    build_memory_prompt, seed_cache_from_memory,
    process_session_end,
)

RECALL_THRESHOLD    = 0.65   # higher threshold for embedding similarity
MUTE_THRESHOLD      = 0.5    # below this, a pillar is muted entirely
PROMOTION_THRESHOLD = 3
VERBATIM_COUNT      = 4


# ── Memory retrieval (embedding-based) ────────────────────────────────────────

def _retrieve_memory(
    query_embedding: List[float],
    session_id: str,
    user_id: str = "default",
    top_k: int = 5,
    query_text: str = "",
) -> Optional[str]:
    """
    Pure embedding cosine similarity.
    No TF-IDF. No keyword matching. Done.
    """
    # stm_clusters and ltm_patterns are dropped. Both were retired — session-
    # keyed fragments and undated lines that produced "abhi Janmashtami hai"
    # a fortnight after the festival — and the thread does this properly now.
    stm = []
    # ltm_patterns is retired, not read.
    #
    # Eighteen rows for one user and almost none of them was memory: the
    # companion's own greetings recalled twenty times, "USER_PATTERN: NUDGE,
    # SADNESS, SEARCH" seventeen, a reminder from August that had long since
    # passed, and her one-word replies. The Janmashtami row said "abhi
    # Janmashtami hai toh mandir jana hai" with no date and was recalled
    # twenty-eight times, a fortnight after Janmashtami.
    #
    # The thread does this properly now — dated, compressed, and rendered as
    # "twelve days ago" rather than as an undated line that reads as today.
    ltm = []

    all_entries = [(e, "stm") for e in stm] + [(e, "ltm") for e in ltm]
    if not all_entries:
        return None

    results = []
    # User pillar priorities bias what gets recalled: a pillar marked
    # important surfaces more readily, a de-prioritised one is suppressed.
    try:
        from memory.pillar_weights import get_pillar_weights
        pillar_weights = get_pillar_weights(user_id)
    except Exception as e:
        print(f"[Retrieve] weights unavailable: {e}")
        pillar_weights = {}

    for entry, tier in all_entries:
        # Use stored embedding if available
        stored_emb = entry.get("embedding", [])
        if stored_emb and len(stored_emb) > 0:
            score = cosine_similarity(query_embedding, stored_emb)
        else:
            # Fallback: simple word overlap for old entries
            q_words = set(entry.get("text", "").lower().split())
            score   = 0.1 if q_words else 0.0

        # Two-stage scoring. Relevance (cosine) decides what is eligible;
        # user priority only decides ordering. This stops a high weight from
        # dragging in memories that are not actually relevant.
        weight = pillar_weights.get(entry.get("pillar"), 1.0)
        if weight < MUTE_THRESHOLD:
            continue

        if score >= RECALL_THRESHOLD:
            new_strength = min(1.0, entry["strength"] + 0.05)
            new_count    = entry["recall_count"] + 1
            # The old tiers are neither read nor written now.
            #
            # Promotion here ran backwards: three recalls in one conversation
            # moved a memory DOWN into long-term storage, so the subjects she
            # returned to most were archived first. And what ltm_patterns
            # collected was not memory — the companion's own greetings
            # recalled twenty times, "USER_PATTERN: NUDGE, SADNESS, SEARCH"
            # seventeen, and "abhi Janmashtami hai toh mandir jana hai" at
            # twenty-eight, undated, a fortnight after Janmashtami.
            #
            # The recall counts kept climbing after we stopped reading them,
            # which is how that row was found again after being deleted.
            #
            # memory_stm and memory_ltm do this properly: dated, compressed by
            # neglect, and rendered as "twelve days ago" rather than as a line
            # that reads as now.
            if tier == "stm":
                pass          # nothing to write back to

            results.append({
                "text":  entry["text"],
                "score": score,
                "rank":  score * weight,
                "tier":  tier,
            })

    if not results:
        return None

    results.sort(key=lambda x: x["rank"], reverse=True)
    # Clean what reaches Nancy: strip the internal tier/score tag and the
    # "PILLAR:" prefix so she sees plain recalled content, not plumbing metadata.
    def _clean(t: str) -> str:
        t = t.strip()
        if ":" in t[:20]:
            head, _, rest = t.partition(":")
            if head.isupper() and len(head) <= 16:
                t = rest.strip()
        return t
    lines = []
    for r in results[:top_k]:
        cleaned = _clean(r["text"])
        if cleaned and len(cleaned) > 3:
            lines.append(cleaned)

    # And what HAPPENED, with the day it happened on.
    #
    # Asked "doctor ke paas kab gayi thi", the reply was "haal hi mein" —
    # recently — while the event sat in storage with 2026-09-05 on it. STM and
    # LTM hold what was said; only events carry the date, and retrieval was
    # not reading them.
    try:
        from memory.events import find_events
        for e in find_events(user_id, query_text or "", limit=3):
            when = str(e.get("happened_on") or "")[:10]
            what = str(e.get("label") or "").strip()
            if what:
                lines.append(f"{when}: {what}" if when else what)
    except Exception as e:
        print(f"[Retrieve] events failed: {e}")

    return "\n".join(lines) if lines else None


# ── Context builder ────────────────────────────────────────────────────────────

def _build_context(session_id: str, model: str) -> list:
    """
    Build context window from session messages:
      - pos 1-4:  verbatim (most recent first, reversed at end)
      - pos 5-7:  truncated to 200 chars
      - pos 8+:   summarized as a single block via Haiku

    FIX: was `elif pos == 8` which only fired exactly at position 8.
         The `else: break` below it meant positions 9+ exited without
         ever summarizing. Changed to `elif pos >= 8` so the summarize
         branch always fires for older messages regardless of loop position,
         and the group slice is computed once then we break.
    """
    all_msgs = get_session_messages(session_id)
    msgs     = [m for m in all_msgs if m["role"] in ("user", "assistant")]
    if not msgs:
        return []

    reversed_msgs = list(reversed(msgs))
    context_parts = []

    for i, msg in enumerate(reversed_msgs):
        pos = i + 1
        if pos <= VERBATIM_COUNT:
            context_parts.append({"role": msg["role"], "content": msg["content"]})
        elif 5 <= pos <= 7:
            truncated = msg["content"][:200] + ("..." if len(msg["content"]) > 200 else "")
            context_parts.append({"role": msg["role"], "content": truncated})
        elif pos >= 8:
            # Summarize everything from pos 8 onward in one shot, then stop.
            group   = [m for m in reversed(reversed_msgs[7:])]
            summary = _summarize_group(group, model)
            if summary:
                context_parts.append({"role": "user", "content": summary})
            break

    context_parts.reverse()
    return context_parts


def _summarize_group(messages: list, model: str) -> str:
    if not messages:
        return ""
    text = "\n".join(f"{m['role'].upper()}: {m['content'][:200]}" for m in messages)
    try:
        import anthropic
        client = __import__("llm").client()
        res    = client.messages.create(
            model=__import__("llm").model("claude-haiku-4-5-20251001"), max_tokens=150,
            messages=[{"role": "user",
                       "content": f"Summarize in 2 sentences preserving key facts:\n\n{text}"}]
        )
        return f"[Earlier in conversation]: {res.content[0].text}"
    except Exception:
        return f"[Earlier]: {' '.join(text.split()[:60])}..."


# ── Cache → STM (with embedding) ──────────────────────────────────────────────

# Tracks last-written STM content per (session_id, pillar) to avoid duplicate inserts.
# Key: (session_id, pillar)  Value: hash of text content
_stm_last_written: dict[tuple, str] = {}


def _compress_cache_to_stm(session_id: str, query_embedding: List[float]):
    """
    Store cache slots in STM with their embeddings.
    FIX: Only writes a new STM row when the content for that pillar has
         actually changed since the last insert — prevents flooding stm_clusters
         with near-duplicate rows on every message turn.
    """
    import hashlib

    slots = get_active_slots(session_id=session_id)
    # Only real content becomes a memory. EMOTION / FUNCTIONAL / MODIFIER slots
    # are classification metadata, not things the person said — keeping them out
    # stops rows like "MODIFIER: URGENCY" diluting retrieval.
    _NOT_MEMORIES = {"RAW", "EMOTION", "FUNCTIONAL", "MODIFIER"}
    meaningful = [s for s in slots if s["strength"] > 0.3 and s["pillar"] not in _NOT_MEMORIES]
    if not meaningful:
        return

    groups = {}
    for s in meaningful:
        groups.setdefault(s["pillar"], []).append(s["value"])

    for pillar, values in groups.items():
        text     = f"{pillar}: {', '.join(sorted(set(values)))}"
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cache_key = (session_id, pillar)

        # Skip if this exact content was already written for this session+pillar
        if _stm_last_written.get(cache_key) == text_hash:
            continue

        try:
            db = __import__('supabase_store', fromlist=['get_client']).get_client()
            db.table("stm_clusters").insert({
                "session_id":   session_id,
                "pillar":       pillar,
                "text":         text,
                "strength":     1.0,
                "recall_count": 0,
                "pillar_tags":  [pillar],
                "embedding":    query_embedding,
            }).execute()
            _stm_last_written[cache_key] = text_hash
        except Exception as e:
            print(f"[STM] Save failed: {e}")


# ── Food, in the background ───────────────────────────────────────────────────

def _food_notes(user_id: str) -> str:
    """Everything that bears on what she eats, in one place, for when food
    comes up — and only then.

    The chat had pieces: interests sometimes, diet only if a form had it,
    health deliberately left out, and what she had said she dislikes never at
    all — it was saved by the food tool and read by nobody but the recipe
    search. So "aaj sham ko kya banaya jaye" was answered without knowing she
    takes a blood-pressure tablet, and "namak kam rakhna" was luck.
    """
    lines = []
    try:
        from memory.profile_store import get_user_profile
        p = get_user_profile(user_id) or {}
    except Exception as e:
        print(f"[Food] profile read failed: {e}")
        p = {}

    demo = p.get("demographics") or {}
    food = p.get("food") or {}
    health = p.get("health") or {}

    diet = food.get("diet") or demo.get("diet")
    if diet:
        lines.append(f"- Diet: {diet}")

    def _list(v):
        return [str(x) for x in (v if isinstance(v, list) else [v]) if x]

    likes = _list(food.get("likes"))
    dislikes = _list(food.get("dislikes"))
    avoid = _list(food.get("avoid")) + _list(food.get("avoids"))
    if likes:
        lines.append(f"- Likes: {', '.join(likes[:10])}")
    if dislikes:
        lines.append(f"- Does not like: {', '.join(dislikes[:10])}")
    if avoid:
        lines.append(f"- Does not eat: {', '.join(avoid[:10])}")

    # Dishes she enjoys, from what she has talked about.
    try:
        from memory.offers import hers
        dishes = [v["label"] for v in sorted(hers(user_id).values(),
                                             key=lambda v: -float(v.get("strength") or 0))
                  if (v.get("category") or "") == "khana"
                  and not (v.get("state") is not None and v["state"] < 0)][:6]
        if dishes:
            lines.append(f"- Enjoys: {', '.join(dishes)}")
    except Exception as e:
        print(f"[Food] interests read failed: {e}")

    # Food she turned down when it was offered.
    try:
        from memory.offers import _refused
        no = sorted(_refused(user_id))[:8]
        if no:
            lines.append(f"- Turned down when offered: {', '.join(no)}")
    except Exception:
        pass

    # What her health means at the table — decided by the model from her
    # conditions and medicines as written, in whatever language. This was a
    # list of English words ("blood pressure", "kidney"), and a condition
    # recorded as "hipertensión" got no rule at all.
    try:
        from memory.food_rules import rules as _food_rules, raw_line as _raw
        fr = _food_rules(user_id)
        if fr.get("chat_notes"):
            lines.append("- For their health: " + "; ".join(fr["chat_notes"]))
        if fr.get("doctor_decides"):
            lines.append("- Their doctor sets their diet: suggest nothing specific "
                         "for that condition")
        if not fr.get("ok"):
            r = _raw(fr)
            if r:
                lines.append("- " + r)
    except Exception as e:
        print(f"[Food] rules failed: {e}")

    # Meat today is a date, not a flag: Tuesdays, Shravan, her own days.
    try:
        from memory.diet import can_eat_meat_today
        v = can_eat_meat_today(user_id)
        if v and not v.get("ok"):
            lines.append("- Today: nothing with meat, fish or egg")
    except Exception:
        pass

    if not lines:
        return ""
    return ("\nFOOD — background, for when food comes up. Use it to make any food "
            "you suggest or discuss right for them. Never bring food up because of "
            "it, never read it back to them, and never explain why something is "
            "or is not suitable unless they ask.\n" + "\n".join(lines) + "\n")


# ── Nancy system prompt ────────────────────────────────────────────────────────

def _build_system_prompt(classified, user_memory: Optional[str],
                          session_memory: Optional[str],
                          user_id: str = "") -> str:
    """Nancy — warm, chatty, memory-aware Indian companion."""

    # Load custom bot persona
    try:
        from routes.persona import get_persona_prompt
        _persona_base = get_persona_prompt(user_id)
    except Exception:
        _persona_base = "You are Nancy, a warm and caring AI companion."

    nancy_persona = _persona_base + """ Be fully in character. Never break character or mention being an AI unless directly asked. You are chatty and genuinely care about the person you're talking to.

YOUR PERSONALITY:
- Warm, friendly, and conversational — like a caring friend
- You remember past conversations, and let that shape how you respond
  without ever reciting it back
- You speak THEIR language — the LANGUAGE note at the very end says which
- You ask follow-up questions — you're genuinely curious
- You celebrate small things enthusiastically
- You're patient, never rush, never dismiss
- You have opinions and share them when asked
- You follow THEIR lead. Reply to what they raised; do not bring in a new
  subject of your own — a match, a film, a song, a show — and do not offer to
  look something up they did not ask about. When they say they are resting,
  let them rest: a warm line is the whole reply.

CRITICAL RULES:
- NEVER say "I don't have any record of previous conversations"
- NEVER say "Each conversation starts fresh"
- NEVER say "I can't remember past sessions"
- You DO have memory — use it naturally without announcing it
- Don't say "Based on my memory..." just use the knowledge

CONVERSATION STYLE:
- Respond to what they actually said. Do not run through a checklist.
- ONE question per message at most. Often zero is right — a warm
  acknowledgement can be a complete reply.
- Do NOT ask after their health conditions. You know about them so you can be
  considerate, not so you can check on them. If THEY raise it, respond warmly;
  otherwise leave it alone.
- Keep it short. Two or three sentences. They read this on a phone.
- Draw topics from what you actually know about this person, below — never
  from generic assumptions about what people their age enjoy.
- When they put something aside — "later", "not now", "this evening",
  "I have puja now", in whatever words — let it go. Do not bring it back in this
  conversation, and do not keep steering towards it. One morning a film was
  raised three times after she had said who watches films this early.
- Never tell them what they usually do, like or feel unless it is in your
  notes below, word for word in substance. "Aap puja ke baad film dekhne ka
  mood kar leti hain" was invented, and a companion who makes up your habits
  is one you stop trusting.
- Never state a clock time from their routine. Name the part of the day
  (breakfast time, the afternoon) in their language, or say nothing.
- Their message usually answers the last thing you said. Read it that way
  first: after "phone kiya?", "haan dhyan hai, kar diya" is about the call.
- A word that looks like a typo or a misheard word is what they most likely
  meant, given what you last said. Never turn an unclear word into a new
  person: "Haan dhyan hai" became "Dhyanesh", and she was asked how long
  it had been since she spoke to him. If you truly cannot tell, ask simply.
- You cannot hear their voice or see their face. Never say how they sound
  or look.
- They are where their notes say they are. Staying away from home is where
  they live for now; never say they are out unless they said so.
TOOL RESULTS:
- When you use a tool (weather, music search, news, places) and get results back, always share the concrete details — real numbers, real titles, real links
- For music/video results specifically: always include the actual youtube_url for each song you mention, so the person can tap and actually play it, not just talk about the song
- Never say you don\'t have access to real-time data — if you have a tool for it, use it\n"""

    # Inject personal profile (who they are)
    try:
        from memory.profile_store import build_profile_prompt
        profile_prompt = build_profile_prompt(user_id)
    except Exception:
        profile_prompt = None

    if profile_prompt:
        nancy_persona += f"\n{profile_prompt}\n"

    # Inject pillar weight preferences
    try:
        from memory.pillar_weights import build_weights_prompt
        weights_prompt = build_weights_prompt(user_id)
        if weights_prompt:
            nancy_persona += f"\n{weights_prompt}\n"
    except Exception:
        pass

    if user_memory:
        # Framing matters as much as content here. Headed "WHAT YOU KNOW ABOUT
        # THIS PERSON", the model read the block back out loud — "dekh rahi hoon
        # aapko khichdi pasand hai". These are notes, and dated ones.
        nancy_persona += (
            "\nBACKGROUND ON THIS PERSON — your own private notes.\n"
            "Never read them back, never say what you can see or remember, and\n"
            "never mention more than one of them in a single message. Bracketed\n"
            "ages are when it was last mentioned; anything more than a few days\n"
            "old is PAST, not a current plan.\n"
            f"{user_memory}\n"
        )

    if session_memory:
        nancy_persona += f"\nFROM THIS CONVERSATION:\n{session_memory}\n"

    # ── Temporal awareness: Nancy must know the user's real local time so she
    # can greet correctly AND resolve relative times ("kal", "12 baje") into
    # actual dates for reminders. ──────────────────────────────────────────────
    try:
        from memory.time_context import time_context as _tctx
        _tc = _tctx(user_id)
        nancy_persona += f"""
RIGHT NOW — the user's local time is {_tc['local_time']} ({_tc['slot']}), timezone {_tc['timezone']}.
Greet and reference time based on THIS. When the user mentions a relative time
("kal", "aaj shaam", "parso", "12 baje", "subah"), resolve it against this
current local time into a concrete date and time.
"""
    except Exception:
        pass
    # ── Her lists, and whether she is going through one in a shop ─────────────
    # Without this the chat cannot know "mil gaya" means the sabudana it just
    # read out, or that "bazar" already has six things on it.
    try:
        from memory.lists import hint as _list_hint
        nancy_persona += _list_hint(user_id)
    except Exception as _lh:
        print(f"[Router] list hint failed: {_lh}")

    # ── Food, in the background ──────────────────────────────────────────────
    try:
        nancy_persona += _food_notes(user_id)
    except Exception as _fn:
        print(f"[Router] food notes failed: {_fn}")

    # ── Her festival, if she keeps one and it is running ─────────────────────
    # The chat did not know. On day three of a Navratri she keeps, she asked
    # what to cook tonight and was offered red lentil soup and garlicky kale.
    # The proactive messages and the offers knew; the conversation, where she
    # actually asks, did not.
    try:
        from memory.festival_brief import for_user as _festival_for
        _f = _festival_for(user_id)
        if _f:
            line = f"\nTODAY: {_f['name']}, day {_f.get('day_of')} of {_f.get('days')}."
            if _f.get("fasting") and _f.get("she_keeps_it"):
                line += (f" She keeps this fast. It avoids {_f.get('fast_avoids')}."
                         f" What is eaten instead: {_f.get('eaten_instead')}."
                         " Any food you suggest or discuss must keep this fast.")
            elif _f.get("fasting"):
                line += (" Many people fast during it and you do not know whether"
                         " she does: ask before suggesting food.")
            nancy_persona += line + "\n"
    except Exception as _fe:
        print(f"[Router] festival read failed: {_fe}")

    # ── Current context with priority ────────────────────────────────────────
    nancy_persona += f"""
CURRENT CONTEXT:
- Topic:      {classified.core} (priority: {classified.core_priority})
- Emotion:    {classified.emotion} (priority: {classified.emotion_priority})
- Intent:     {classified.functional} (priority: {classified.functional_priority})
- Language:   {classified.language}
- Modifiers:  {', '.join(classified.modifiers) if classified.modifiers else 'none'}
"""

    # ── Priority-based behaviour instructions ─────────────────────────────────
    if classified.core_priority == "HIGH":
        nancy_persona += f"""
⚠️ HIGH PRIORITY — {classified.core}:
This is the person's PRIMARY concern right now. Address it directly and warmly before anything else.
"""
    if classified.emotion_priority == "HIGH" and classified.emotion in ("FEAR", "STRESS", "SADNESS"):
        nancy_persona += f"""
💙 EMOTIONAL SUPPORT NEEDED — {classified.emotion}:
The person is emotionally vulnerable right now. Lead with empathy. Don't rush to solutions.
Speak softly and simply, in their language — ask what happened, tell them not to worry.
"""
    if classified.emotion_priority == "HIGH" and classified.emotion == "LOVE":
        nancy_persona += """
❤️ WARM MOMENT:
The person is expressing love or affection. Match their warmth. Celebrate it.
"""
    if classified.emotion_priority == "HIGH" and classified.emotion in ("JOY", "OPTIMISM"):
        nancy_persona += """
🎉 HAPPY MOMENT:
The person is in a good mood! Be enthusiastic and celebratory with them.
"""

    # ── Matrix-based response guidance ────────────────────────────────────────
    core_matrix = classified.core_matrix
    if core_matrix and classified.core_priority in ("HIGH", "MEDIUM"):
        subject  = core_matrix.get("SUBJECT", {}).get("primary", "")
        action   = core_matrix.get("ACTION",  {}).get("primary", "")
        context  = core_matrix.get("CONTEXT", {}).get("primary", "")
        if subject or action or context:
            nancy_persona += f"""
RESPONSE FOCUS for {classified.core}:
- Who/What:  {subject}
- Core need: {action}
- Context:   {context}
Use this to shape your response — ask about the right things, not generic questions.
"""

    # ── Urgency handling ──────────────────────────────────────────────────────
    if "URGENCY" in classified.modifiers:
        nancy_persona += "\nURGENT REQUEST: Respond immediately and practically. No pleasantries first.\n"
    if "TEMPORAL" in classified.modifiers:
        nancy_persona += "TIME-SENSITIVE: The person is referencing a specific time. Acknowledge it.\n"
    if "LOCATION" in classified.modifiers:
        nancy_persona += "LOCATION-SPECIFIC: They need local information. Ask which city/area if not clear.\n"

    # ── API triggers ──────────────────────────────────────────────────────────
    if classified.api_triggers:
        top_trigger = list(classified.api_triggers.keys())[0]
        score       = list(classified.api_triggers.values())[0]
        nancy_persona += f"\nDETECTED ACTION: {top_trigger} (confidence: {round(score*100)}%) — offer to help with this specifically.\n"

    # ── Grammatical gender — LAST, deliberately ──────────────────────────
    # Hindi and most Indian languages inflect verbs for the speaker's gender.
    # A female companion saying "main gaya tha" reads as broken to any native
    # speaker, and it is the most visible flaw in the output. This sits at the
    # very end because a short instruction placed early loses to the thousands
    # of characters of context above it — the same reason declared.Language
    # puts its instruction last.
    nancy_persona += _gender_instruction(user_id)

    # ── Her health right now: what is open, what is over, what may be asked ──
    try:
        from memory.episodes import prompt_note as _episode_note
        nancy_persona += _episode_note(user_id)
    except Exception as _en:
        print(f"[Router] episode note failed: {_en}")

    # ── Language — the very last word ────────────────────────────────────
    # The prompt above is full of Hinglish examples, and it used to say
    # outright "you speak Hinglish". Her chosen language — the same
    # instruction the proactive messages use — never reached the chat, so a
    # Tamil speaker, or a Spanish one, was pulled towards Hinglish, most of
    # all when upset. It goes last because the last instruction is the one
    # that holds.
    nancy_persona += _language_instruction(user_id)

    return nancy_persona


def _language_instruction(user_id: str = "") -> str:
    try:
        from memory.context_builder import _language
        lang = _language(user_id)
    except Exception as e:
        print(f"[Router] language read failed: {e}")
        lang = ("Write back in whatever language and script they wrote in.")
    return ("\nLANGUAGE — THIS DECIDES THE LANGUAGE OF EVERY REPLY.\n"
            f"{lang}\n"
            "Quoted examples anywhere above are illustrations of tone and "
            "meaning only — never copy their language.\n")


def _gender_instruction(user_id: str = "") -> str:
    """Explicit verb-form instruction for the companion's grammatical gender.

    Read from bot_personas.gender when that column exists and is set; otherwise
    inferred from the voice preset, which already encodes it (warm_female,
    elder_male, ...). Defaults to female, matching the default persona's
    warm_female voice.
    """
    gender = ""
    try:
        from supabase_store import get_client
        rows = (get_client().table("bot_personas")
                .select("*")
                .eq("user_id", user_id).limit(1).execute()).data or []
        p = rows[0] if rows else {}
        gender = str(p.get("gender") or "").strip().lower()
        if gender not in ("male", "female"):
            vid = str(p.get("voice_id") or "").lower()
            if "female" in vid:
                gender = "female"
            elif "male" in vid:
                gender = "male"
    except Exception as e:
        print(f"[Persona] gender lookup failed, defaulting female: {e}")

    if gender == "male":
        return (
            "\nGRAMMATICAL GENDER — THIS OVERRIDES EVERYTHING ABOVE EXCEPT LANGUAGE.\n"
            "You are male. Speaking about YOURSELF in Hindi, Hinglish or any\n"
            "gendered language (Spanish: cansado, Portuguese: obrigado),\n"
            "always use MASCULINE forms:\n"
            "  main kar raha hoon / main gaya tha / de sakta hoon\n"
            "  main confuse ho gaya tha / dekh raha hoon\n"
            "Never feminine forms for yourself. Every message, however short.\n"
            "Verb forms for the PERSON you are speaking to follow THEIR gender,\n"
            "not yours.\n"
        )

    return (
        "\nGRAMMATICAL GENDER — THIS OVERRIDES EVERYTHING ABOVE EXCEPT LANGUAGE.\n"
        "You are female. Speaking about YOURSELF in Hindi, Hinglish or any\n"
        "gendered language (Spanish: cansada, Portuguese: obrigada),\n"
        "always use FEMININE forms:\n"
        "  main kar rahi hoon        (NOT kar raha hoon)\n"
        "  main gayi thi             (NOT gaya tha)\n"
        "  de sakti hoon             (NOT de sakta hoon)\n"
        "  main confuse ho gayi thi  (NOT ho gaya tha)\n"
        "  dekh rahi hoon            (NOT dekh raha hoon)\n"
        "Never masculine forms for yourself. Every message, however short.\n"
        "Verb forms for the PERSON you are speaking to follow THEIR gender,\n"
        "not yours.\n"
    )


# ── Auto title ─────────────────────────────────────────────────────────────────

def _generate_title(text: str, classified) -> str:
    words   = text.split()[:6]
    snippet = " ".join(words)
    return f"{classified.core} · {snippet}"


# ── AI Providers ───────────────────────────────────────────────────────────────

def _call_anthropic(model, system, messages):
    import anthropic
    c = __import__("llm").client()
    r = c.messages.create(model=model, max_tokens=1024, system=system, messages=messages)
    return r.content[0].text

def _call_gemini(model, system, messages):
    from google import genai
    from google.genai import types
    client  = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    history = []
    for msg in messages[:-1]:
        role = "user" if msg["role"] == "user" else "model"
        history.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
    response = client.models.generate_content(
        model=model,
        contents=history + [types.Content(role="user", parts=[types.Part(text=messages[-1]["content"])])],
        config=types.GenerateContentConfig(system_instruction=system, max_output_tokens=1024)
    )
    return response.text

def _call_oc(model, system, messages, api_key, base_url=None):
    from openai import OpenAI
    kw = {"api_key": api_key}
    if base_url:
        kw["base_url"] = base_url
    c = OpenAI(**kw)
    r = c.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}] + messages,
        max_tokens=1024
    )
    return r.choices[0].message.content

def _call_mistral(model, system, messages):
    from mistralai import Mistral
    c = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
    r = c.chat.complete(
        model=model,
        messages=[{"role": "system", "content": system}] + messages,
        max_tokens=1024
    )
    return r.choices[0].message.content

def _to_litellm_model(model: str) -> tuple:
    """
    Map our existing model-name conventions to LiteLLM's provider-prefixed
    model strings. Returns (litellm_model, extra_kwargs) where extra_kwargs
    carries an explicit api_key/api_base for providers LiteLLM doesn\'t have
    a named integration for (same passthrough trick as the old _call_oc).
    """
    if model.startswith("claude"):
        return f"anthropic/{model}", {}
    elif model.startswith("gemini"):
        return f"gemini/{model}", {"api_key": os.getenv("GEMINI_API_KEY")}
    elif model.startswith("grok"):
        return f"openai/{model}", {"api_key": os.getenv("XAI_API_KEY"), "api_base": "https://api.x.ai/v1"}
    elif model.startswith("mistral") or model.startswith("codestral"):
        return f"mistral/{model}", {"api_key": os.getenv("MISTRAL_API_KEY")}
    elif model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        return f"openai/{model}", {"api_key": os.getenv("OPENAI_API_KEY")}
    elif model.startswith("llama") or model.startswith("deepseek-r1-distill") or model.startswith("mixtral"):
        return f"groq/{model}", {"api_key": os.getenv("GROQ_API_KEY")}
    elif "sonar" in model:
        return f"perplexity/{model}", {}
    elif model.startswith("deepseek"):
        return f"deepseek/{model}", {"api_key": os.getenv("DEEPSEEK_API_KEY")}
    elif model.startswith("qwen"):
        return f"openai/{model}", {"api_key": os.getenv("QWEN_API_KEY"), "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1"}
    elif model.startswith("glm"):
        return f"openai/{model}", {"api_key": os.getenv("ZHIPU_API_KEY"), "api_base": "https://open.bigmodel.cn/api/paas/v4"}
    elif model.startswith("moonshot"):
        return f"openai/{model}", {"api_key": os.getenv("MOONSHOT_API_KEY"), "api_base": "https://api.moonshot.cn/v1"}
    elif model.startswith("command"):
        return f"cohere/{model}", {"api_key": os.getenv("COHERE_API_KEY")}
    elif "/" in model:
        return f"openai/{model}", {"api_key": os.getenv("TOGETHER_API_KEY"), "api_base": "https://api.together.xyz/v1"}
    else:
        return "anthropic/claude-sonnet-4-20250514", {}


def _route(model, system, messages, user_id="default"):
    """
    Universal LLM call with tool-calling, working across every provider
    via LiteLLM. Runs an agentic loop: if the model requests one or more
    tools, we execute them and feed results back until we get a final
    plain-text answer.
    """
    import litellm
    from engine.tools import get_tool_schemas, execute_tool

    litellm_model, extra_kwargs = _to_litellm_model(model)
    full_messages = [{"role": "system", "content": system}] + messages
    collected_tool_results = []  # raw structured data (real URLs etc) for the frontend

    for _ in range(5):  # hard cap so a misbehaving loop can\'t run forever
        response = litellm.completion(
            model=litellm_model,
            messages=full_messages,
            tools=get_tool_schemas(),
            **extra_kwargs,
        )
        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)

        if not tool_calls:
            return msg.content or "", collected_tool_results

        full_messages.append(msg.model_dump())

        for call in tool_calls:
            import json as _json
            try:
                args = _json.loads(call.function.arguments or "{}")
            except Exception:
                args = {}
            result = execute_tool(call.function.name, args, user_id=user_id)
            collected_tool_results.append({"tool": call.function.name, "data": result})
            full_messages.append({
                "role":         "tool",
                "tool_call_id": call.id,
                "content":      _json.dumps(result),
            })

    return "Sorry, I got stuck trying to look that up — can you ask again?", collected_tool_results


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def process_input(text: str, model: str,
                        session_id: Optional[str],
                        user_id: str = "default") -> dict:

    # 1. Resolve session with the HYBRID model (continuation window + gap rollover).
    #    - If the user has a recent session (within CONTINUATION_WINDOW_HOURS),
    #      continue it — coming back soon resumes, no fragmentation.
    #    - Otherwise start a fresh session; the previous one has "ended" and will
    #      be summarized below. We do NOT trust the client-supplied session_id for
    #      this decision (it was the source of the summary-never-fires bug).
    from supabase_store import (get_latest_session, _hours_since,
                                CONTINUATION_WINDOW_HOURS,
                                get_previous_unsummarized_session)
    latest = get_latest_session(user_id)
    if latest and _hours_since(latest.get("updated_at", "")) < CONTINUATION_WINDOW_HOURS:
        session = latest                      # continuation — reuse recent session
        is_new  = False
        db = get_client()
        db.table("sessions").update({"model": model, "updated_at": "now()"}).eq("id", latest["id"]).execute()
    else:
        session = create_session(model, user_id)   # gap or first ever — new session
        is_new  = True
    sid = session["id"]
    update_session_weight(sid)

    # What she meant, for understanding; what she wrote, for the record.
    # The keyboard and the transcriber both change her words — "carbon" for
    # tarbuz, "Dhyanesh" for "dhyan hai" — and everything below used to read
    # them as written. Her own words are what is saved and shown.
    original = text
    corrected = False
    if text and text.strip():
        try:
            from memory.meant import what_she_meant
            text, corrected = what_she_meant(user_id, text)
        except Exception as _me:
            print(f"[Router] meaning step failed: {_me}")
            text = original

    # If the companion offered something and this is the answer, attribute it
    # before anything else reads the message. Costs nothing when no suggestion
    # is open, which is most turns. Fire-and-forget: a failed attribution must
    # never block the reply.
    if text and text.strip():
        def _react():
            try:
                from memory.suggestions import handle_reply
                handle_reply(user_id, text, sid)
                # Close the delivery loop. record_outcome has existed
                # since the beginning, with a docstring about knowing
                # what we SENT but not what LANDED — and nothing ever
                # called it, so 0 of 33 events had responded_at set and
                # the cadence budget had nothing to read.
                from memory.cadence import mark_engaged
                mark_engaged(user_id)

                # "Purani wali" — if a question about which film she meant is
                # open, her reply settles it and enrichment can proceed. Cheap
                # when nothing is pending, which is nearly always.
                # An answer to a probe says which direction she follows —
                # "haan, unke gaane ache hain" is worth more than the song
                # itself, because it transfers to every film and singer.
                from memory.axes import handle_probe_reply
                handle_probe_reply(user_id, text, sid)

                # "Aaj khichdi banayi thi" confirms lunch without answering
                # anything, and that is where most confirmations come from.
                # Costs nothing when nothing is past due and unanswered, which
                # is most of the day.
                # Is she in danger right now?
                #
                # The alert engine ran only at session end, so "saans nahi aa
                # rahi" at two in the morning reached her son when the session
                # closed — hours later, or whenever the backstop sweep got to
                # it. The most important path in the product was the slowest.
                #
                # One question, read in any language, on the message itself.
                try:
                    from memory.alert_engine import alert_now
                    alert_now(user_id, text)
                except Exception as _ae:
                    print(f"[Router] urgent check failed: {_ae}")

                # Did she just settle something about herself?
                #
                # "Main shakahari hoon", "ab Bangalore mein rehti hoon",
                # "janamdin 14 March ko hai". Usually nothing — most of what
                # she says is about her day, not about her. Costly ones are
                # asked about before they are believed.
                try:
                    from memory.anchors import hear, settle
                    settle(user_id, text)        # her answer to a question
                    _ah = hear(user_id, text)    # and anything new

                    # And her days. "Mangalvar aur Shanivar ko vrat rakhti
                    # hoon" is four facts: two fasts, no meat on either, and
                    # a temple visit worth having something to say about.
                    from memory.observances import hear as _obs_hear
                    _obs_hear(user_id, text)
                    if _ah:
                        print(f"[Anchor] asking about: {_ah[:60]}")
                except Exception as _ke:
                    print(f"[Anchor] read failed: {_ke}")

                # (A second copy of the anchor block above stood here, so
                # every message was heard twice: two model calls, and a fact
                # said once counted as said twice.)

                from memory.day import note_from_message
                note_from_message(user_id, text)

                # Whatever she just touched comes back up. Recall REVIVES
                # rather than promotes — what was built did the opposite,
                # pushing frequently recalled things down into long-term
                # storage, so the subjects she returned to most were archived
                # first.
                #
                # It also leaves a behavioural event, because strength alone
                # says she mentioned something and the event log is what says
                # WHEN. Arjun reached 2.29 across six mentions with an event
                # count of one, so his trajectory could never form.
                try:
                    from memory.clusters import reactivate
                    reactivate(user_id, text)
                except Exception as _re:
                    print(f"[Router] reactivate failed: {_re}")

                from memory.ambiguity import (needs_asking, match_answer,
                                              resolve)
                pend = needs_asking(user_id)
                if pend:
                    imdb = match_answer(pend, text)
                    if imdb:
                        resolve(user_id, pend["cluster_id"], imdb)
                        from memory.enrich import enrich_cluster
                        enrich_cluster(user_id, pend["cluster_id"], force=True)
            except Exception as e:
                print(f"[Suggest] reply handling failed: {e}")
        threading.Thread(target=_react, daemon=True).start()

    # 2. On a genuinely new session, summarize the PREVIOUS unsummarized session.
    #    get_previous_unsummarized_session returns a real session UUID whose
    #    messages actually exist — so the summarizer finds them (the fix).
    if is_new:
        def _bg():
            try:
                prev = get_previous_unsummarized_session(user_id, exclude_id=sid)
                if prev:
                    process_session_end(prev["id"], user_id)
                    print(f"[BG] Summarized previous session {prev['id'][:8]}")
            except Exception as e:
                print(f"[BG] Session end failed: {e}")
        threading.Thread(target=_bg, daemon=True).start()

    # 3. Seed cache from user memory on new session
    if is_new:
        seed_cache_from_memory(user_id, sid)

    # 4. Classify with EMBEDDINGS (no keyword matching!)
    classified = classify_input(text)
    embedding  = classified.embedding  # real 1024-dim vector

    # Health episodes: a cold that starts, is checked on and ends. Read in the
    # background against what is open — "theek hai" closes the cold it is
    # about. See memory/episodes.py.
    def _episodes(_t=text, _p=classified.core):
        try:
            from memory.meant import _last_said
            from memory.episodes import hear
            hear(user_id, _t, said=_last_said(user_id), pillar=_p)
        except Exception as _ee:
            print(f"[Router] episodes failed: {_ee}")
    threading.Thread(target=_episodes, daemon=True).start()

    # 5. Save user message with embedding
    save_message(
        session_id=sid, role="user", content=original, model=model,
        pillar_core=classified.core,
        pillar_emotion=classified.emotion,
        pillar_functional=classified.functional,
        pillar_modifiers=classified.modifiers,
        pillar_score=classified.core_score,
        pillar_vector=classified.pillar_vector,
        embedding=embedding,
    )

    # 6. Auto-title on first message
    msgs = get_session_messages(sid)
    if len(msgs) == 1:
        update_session_title(sid, _generate_title(text, classified))

    # 7. Update cache + decay
    update_cache(classified, session_id=sid, model=model)
    register_pillars(classified, session_id=sid, model=model)
    track_decay()

    # 7b. Enrich user profile from this message (pillar-driven, no extra API call)
    try:
        from memory.profile_enricher import enrich_profile_from_message
        enrich_profile_from_message(text, classified, user_id, sid)
    except Exception as e:
        print(f"[ProfileEnricher] {e}")

    # 8. Compress cache → STM with embedding
    _compress_cache_to_stm(sid, embedding)

    # 9. Cross-session user memory
    # Her message goes too, so the thread can be found by TAG rather than
    # only by recency — she says "Rajesh" and the days about him are a lookup.
    # What is due right now, folded into the reply rather than pushed.
    #
    # She may be mid-conversation when her lunch time passes, and a separate
    # push arriving while she is already talking is absurd. Skipping it is
    # worse: her thyronorm and amlodipine are taken with food, so the meal
    # and the tablet are the same question.
    #
    # One line at the end of whatever she raised — not the whole reply, and
    # not an offer. A song can wait for its own moment; a tablet cannot.
    try:
        from memory.context_builder import _due_now
        _dn = _due_now(user_id)
    except Exception as _de:
        print(f"[Router] due-now failed: {_de}")
        _dn = ""

    user_memory = build_memory_prompt(user_id, current_embedding=embedding,
                                      _query_text=text)
    if _dn:
        user_memory = (user_memory or '') + _dn

    # 10. Within-session memory (EMBEDDING-BASED!)
    # The text as well as the vector: events are matched on what she asked,
    # and the date is the answer to "kab".
    session_memory = _retrieve_memory(embedding, sid, user_id, query_text=text)

    # 11. Build context window
    context_messages = _build_context(sid, model)
    # The model sees her words and, when they were garbled, what she meant —
    # so it answers the meaning and can still check a word with her.
    _turn = (f"{original}\n[what they meant: {text}]" if corrected else original)
    if context_messages and context_messages[-1].get("role") == "user" \
            and context_messages[-1].get("content") == original:
        context_messages[-1] = {"role": "user", "content": _turn}
    else:
        context_messages.append({"role": "user", "content": _turn})

    # 12. Nancy system prompt
    system_prompt = _build_system_prompt(classified, user_memory, session_memory, user_id)

    # 13. Call AI
    reply, tool_results = _route(model, system_prompt, context_messages, user_id=user_id)

    # Did the reply ask about the health problem that was due? Then it is not
    # asked again today.
    def _asked(_r=reply):
        try:
            from memory.episodes import mark_asked_if
            mark_asked_if(user_id, _r)
        except Exception as _ae:
            print(f"[Router] episode ask-check failed: {_ae}")
    threading.Thread(target=_asked, daemon=True).start()

    # 14. Save assistant message with embedding
    save_message(
        session_id=sid, role="assistant", content=reply, model=model,
        pillar_core=classified.core,
        pillar_emotion=classified.emotion,
        pillar_functional=classified.functional,
        pillar_modifiers=classified.modifiers,
        pillar_score=classified.core_score,
        pillar_vector=classified.pillar_vector,
        embedding=embedding,
    )

    # 14b. Reminder detection — if the user asked to be reminded of something,
    # store it with an absolute fire_at and surface a structured event the app
    # renders as a confirmation card. None when no reminder is present.
    reminder_event = None
    try:
        from memory.reminder_engine import detect_and_store_reminder
        reminder_event = detect_and_store_reminder(user_id, text, sid)
    except Exception as e:
        print(f"[Reminder] detect failed: {e}")

    return {
        "reply":         reply,
        "session_id":    sid,
        "classified":    classified.to_dict(),
        "memory_used":   user_memory is not None or session_memory is not None,
        "model":         model,
        "api_triggers":  classified.api_triggers,
        "language":      classified.language,
        "tool_results":  tool_results,
        "reminder":      reminder_event,
    }


async def end_session(session_id: str, user_id: str = "default") -> dict:
    def _bg():
        try:
            process_session_end(session_id, user_id)
        except Exception as e:
            print(f"[BG] end_session failed: {e}")
    threading.Thread(target=_bg, daemon=True).start()
    return {"status": "summarizing", "session_id": session_id}

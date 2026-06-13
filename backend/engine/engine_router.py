"""
ENGINE ROUTER v4 — Recursive Memory
Full pipeline with cross-session recursive summarization.

On session start: load user_memory → seed cache → inject into prompt
On session end:   summarize session → recursive update user_memory
"""

import os
from typing import Optional
from dotenv import load_dotenv

from classifier.pillar_classifier import classify_input
from memory.cache.cache_memory import update_cache, get_active_slots, apply_decay
from memory.decay.decay_memory import track_decay
from store.pillar_vector_store import register_pillars

load_dotenv()

from supabase_store import (
    get_or_create_session, save_message, get_session_messages,
    update_session_weight, update_session_title,
    save_stm_cluster, get_stm_clusters,
    update_stm_recall, promote_stm_to_ltm,
    get_ltm_patterns, update_ltm_recall,
)
from memory.user_memory_store import (
    build_memory_prompt,
    seed_cache_from_memory,
    process_session_end,
)

RECALL_THRESHOLD    = 0.15
PROMOTION_THRESHOLD = 3
VERBATIM_COUNT      = 4


# ── Cosine similarity ──────────────────────────────────────────────────────────

def _cosine_sim(query: str, candidates: list) -> list:
    if not candidates:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        vec    = TfidfVectorizer(min_df=1, stop_words="english")
        matrix = vec.fit_transform([query] + candidates)
        return cosine_similarity(matrix[0:1], matrix[1:]).flatten().tolist()
    except Exception:
        return [0.0] * len(candidates)


# ── Memory retrieval ───────────────────────────────────────────────────────────

def _retrieve_session_memory(text: str, session_id: str,
                              pillar_tags: list) -> Optional[str]:
    """Search STM + LTM for relevant memories in current session."""
    stm = get_stm_clusters(session_id)
    ltm = get_ltm_patterns()

    all_entries = [(e, "stm") for e in stm] + [(e, "ltm") for e in ltm]
    if not all_entries:
        return None

    texts  = [e[0]["text"] for e in all_entries]
    scores = _cosine_sim(text, texts)

    results = []
    for (entry, tier), score in zip(all_entries, scores):
        if pillar_tags and entry.get("pillar_tags"):
            overlap = len(set(pillar_tags) & set(entry["pillar_tags"]))
            score  += overlap * 0.1

        if score > RECALL_THRESHOLD:
            new_strength = min(1.0, entry["strength"] + 0.1)
            new_count    = entry["recall_count"] + 1
            if tier == "stm":
                update_stm_recall(entry["id"], new_strength, new_count)
                if new_count >= PROMOTION_THRESHOLD:
                    promote_stm_to_ltm(entry)
            else:
                update_ltm_recall(entry["id"], new_strength, new_count)
            results.append(f"[{tier.upper()} {round(score*100)}%] {entry['text']}")

    return "\n".join(results[:5]) if results else None


# ── Context builder (compression pyramid) ─────────────────────────────────────

def _build_context(session_id: str, model: str) -> list:
    """Build message history using compression pyramid."""
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
        elif pos == 8:
            group = [m for m in reversed(reversed_msgs[7:20])]
            summary = _summarize_group(group, model)
            if summary:
                context_parts.append({"role": "user", "content": summary})
            break
        else:
            break

    context_parts.reverse()
    return context_parts


def _summarize_group(messages: list, model: str) -> str:
    if not messages:
        return ""
    text = "\n".join(f"{m['role'].upper()}: {m['content'][:200]}" for m in messages)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        res = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user",
                       "content": f"Summarize in 2 sentences preserving key facts:\n\n{text}"}]
        )
        return f"[Earlier in conversation]: {res.content[0].text}"
    except Exception:
        words = text.split()
        return f"[Earlier]: {' '.join(words[:60])}..."


# ── Cache → STM compression ────────────────────────────────────────────────────

def _compress_cache_to_stm(session_id: str):
    slots = get_active_slots()
    meaningful = [s for s in slots if s["strength"] > 0.3 and s["pillar"] != "RAW"]
    if not meaningful:
        return
    groups = {}
    for s in meaningful:
        groups.setdefault(s["pillar"], []).append(s["value"])
    for pillar, values in groups.items():
        text = f"{pillar}: {', '.join(set(values))}"
        save_stm_cluster(session_id, pillar, text,
                         pillar_tags=[pillar], strength=1.0)


# ── Auto session title ─────────────────────────────────────────────────────────

def _generate_title(text: str, classified) -> str:
    words   = text.split()[:6]
    snippet = " ".join(words)
    return f"{classified.core} · {snippet}"


# ── System prompt ──────────────────────────────────────────────────────────────

def _build_system_prompt(classified, user_memory: Optional[str],
                          session_memory: Optional[str]) -> str:
    prompt = """You are a warm, patient, memory-aware AI companion.\n"""

    # Cross-session user memory (most important)
    if user_memory:
        prompt += f"\n{user_memory}\n"

    # Within-session memory
    if session_memory:
        prompt += f"\nFrom our conversation so far:\n{session_memory}\n"

    # Current context
    prompt += f"""
Current topic classification:
- Domain:  {classified.core}
- Emotion: {classified.emotion}
- Intent:  {classified.functional}

Be warm, patient and helpful. Reference what you know about this person naturally.
Never say "As I mentioned in our previous conversation" — just use the knowledge naturally.
"""
    return prompt


# ── AI Providers ───────────────────────────────────────────────────────────────

def _call_anthropic(model, system, messages):
    import anthropic
    c = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    r = c.messages.create(model=model, max_tokens=1024,
                          system=system, messages=messages)
    return r.content[0].text

def _call_gemini(model, system, messages):
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    m = genai.GenerativeModel(model, system_instruction=system)
    h = [{"role": "user" if msg["role"] == "user" else "model",
           "parts": [msg["content"]]} for msg in messages[:-1]]
    return m.start_chat(history=h).send_message(messages[-1]["content"]).text

def _call_openai_compat(model, system, messages, api_key, base_url=None):
    from openai import OpenAI
    kw = {"api_key": api_key}
    if base_url: kw["base_url"] = base_url
    c = OpenAI(**kw)
    r = c.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}] + messages,
        max_tokens=1024)
    return r.choices[0].message.content

def _call_mistral(model, system, messages):
    from mistralai import Mistral
    c = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
    r = c.chat.complete(
        model=model,
        messages=[{"role": "system", "content": system}] + messages,
        max_tokens=1024)
    return r.choices[0].message.content

def _route(model, system, messages):
    if model.startswith("claude"):
        return _call_anthropic(model, system, messages)
    elif model.startswith("gemini"):
        return _call_gemini(model, system, messages)
    elif model.startswith("grok"):
        return _call_openai_compat(model, system, messages,
            os.getenv("XAI_API_KEY"), "https://api.x.ai/v1")
    elif model.startswith("mistral") or model.startswith("codestral"):
        return _call_mistral(model, system, messages)
    elif model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        return _call_openai_compat(model, system, messages,
            os.getenv("OPENAI_API_KEY"))
    elif "sonar" in model:
        return _call_openai_compat(model, system, messages,
            os.getenv("PERPLEXITY_API_KEY"), "https://api.perplexity.ai")
    elif model.startswith("llama") or model.startswith("deepseek-r1-distill"):
        return _call_openai_compat(model, system, messages,
            os.getenv("GROQ_API_KEY"), "https://api.groq.com/openai/v1")
    elif model.startswith("deepseek"):
        return _call_openai_compat(model, system, messages,
            os.getenv("DEEPSEEK_API_KEY"), "https://api.deepseek.com/v1")
    elif model.startswith("qwen"):
        return _call_openai_compat(model, system, messages,
            os.getenv("QWEN_API_KEY"),
            "https://dashscope.aliyuncs.com/compatible-mode/v1")
    elif model.startswith("command"):
        import cohere
        c = cohere.Client(api_key=os.getenv("COHERE_API_KEY"))
        h = [{"role": "USER" if m["role"] == "user" else "CHATBOT",
               "message": m["content"]} for m in messages[:-1]]
        return c.chat(model=model, preamble=system,
                      chat_history=h, message=messages[-1]["content"]).text
    elif "/" in model:
        return _call_openai_compat(model, system, messages,
            os.getenv("TOGETHER_API_KEY"), "https://api.together.xyz/v1")
    else:
        return _call_anthropic("claude-sonnet-4-20250514", system, messages)


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def process_input(text: str, model: str,
                        session_id: Optional[str],
                        user_id: str = "default") -> dict:

    # 1. Get/create session
    from supabase_store import get_or_create_session, update_session_weight, update_session_title
    session = get_or_create_session(session_id, model, user_id)
    sid     = session["id"]
    is_new  = session_id != sid  # True if we just created a new session
    update_session_weight(sid)

    # 2. If new session → process previous session end + seed cache
    if is_new and session_id:
        # Process the previous session in background
        try:
            process_session_end(session_id, user_id)
        except Exception as e:
            print(f"[Router] Session end processing failed: {e}")

    # 3. Seed cache from user memory on new session
    if is_new:
        seed_cache_from_memory(user_id, sid)

    # 4. Classify input
    classified = classify_input(text)

    # 5. Save user message
    save_message(
        session_id=sid, role="user", content=text, model=model,
        pillar_core=classified.core, pillar_emotion=classified.emotion,
        pillar_functional=classified.functional,
        pillar_modifiers=classified.modifiers,
        pillar_score=classified.core_score,
    )

    # 6. Auto-title on first message
    msgs = get_session_messages(sid)
    if len(msgs) == 1:
        update_session_title(sid, _generate_title(text, classified))

    # 7. Update cache
    update_cache(classified, session_id=sid, model=model)
    register_pillars(classified, session_id=sid, model=model)
    track_decay()
    _compress_cache_to_stm(sid)

    # 8. Get cross-session user memory
    user_memory = build_memory_prompt(user_id)

    # 9. Get within-session memory
    session_memory = _retrieve_session_memory(
        text, sid,
        pillar_tags=[classified.core, classified.emotion, classified.functional]
    )

    # 10. Build context window
    context_messages = _build_context(sid, model)
    if not context_messages or context_messages[-1].get("content") != text:
        context_messages.append({"role": "user", "content": text})

    # 11. Build system prompt with both memory layers
    system_prompt = _build_system_prompt(classified, user_memory, session_memory)

    # 12. Call AI
    reply = _route(model, system_prompt, context_messages)

    # 13. Save assistant message
    save_message(
        session_id=sid, role="assistant", content=reply, model=model,
        pillar_core=classified.core, pillar_emotion=classified.emotion,
        pillar_functional=classified.functional,
        pillar_modifiers=classified.modifiers,
        pillar_score=classified.core_score,
    )

    return {
        "reply":        reply,
        "session_id":   sid,
        "classified":   classified.to_dict(),
        "memory_used":  user_memory is not None or session_memory is not None,
        "model":        model,
        "user_memory":  bool(user_memory),
    }


# ── Manual session end trigger ─────────────────────────────────────────────────

async def end_session(session_id: str, user_id: str = "default") -> dict:
    """
    Explicitly end a session and trigger summarization.
    Called when user closes the app or starts a new chat.
    """
    try:
        process_session_end(session_id, user_id)
        return {"status": "ok", "session_id": session_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}

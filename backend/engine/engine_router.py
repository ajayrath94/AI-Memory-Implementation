"""
ENGINE ROUTER v3
Full pipeline with Supabase persistence.

1.  Get/create session in Supabase
2.  Save user message to DB
3.  Classify input → pillars
4.  Update cache (in-memory, fast)
5.  Register pillar correlations
6.  Run decay tick
7.  Compress cache → STM in DB
8.  Retrieve memory context from STM + LTM
9.  Build context window (compression pyramid from DB)
10. Call AI provider
11. Save assistant message to DB
12. Auto-generate session title if first message
"""

import os
from typing import Optional
from dotenv import load_dotenv

from classifier.pillar_classifier import classify_input
from memory.cache.cache_memory import update_cache, get_active_slots, apply_decay
from memory.decay.decay_memory import track_decay
from store.pillar_vector_store import register_pillars

load_dotenv()

# Import Supabase store
from supabase_store import (
    get_or_create_session, save_message, get_session_messages,
    update_session_weight, update_session_title,
    upsert_cache_slot, get_cache_slots, delete_cache_slot,
    save_stm_cluster, get_stm_clusters, update_stm_recall, promote_stm_to_ltm,
    get_ltm_patterns, update_ltm_recall, save_ltm_pattern,
)

RECALL_THRESHOLD     = 0.15
PROMOTION_THRESHOLD  = 3
VOID_THRESHOLD       = 0.05
VERBATIM_COUNT       = 4


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

def _retrieve_memory(text: str, session_id: str,
                     pillar_tags: list, user_id: str = "default") -> Optional[str]:
    """Search STM + LTM for relevant memories using cosine similarity."""
    stm = get_stm_clusters(session_id)
    ltm = get_ltm_patterns(user_id)

    all_entries = [(e, "stm") for e in stm] + [(e, "ltm") for e in ltm]
    if not all_entries:
        return None

    texts  = [e[0]["text"] for e in all_entries]
    scores = _cosine_sim(text, texts)

    results = []
    for (entry, tier), score in zip(all_entries, scores):
        # Associative chaining — boost if pillar tags match
        if pillar_tags and entry.get("pillar_tags"):
            overlap = len(set(pillar_tags) & set(entry["pillar_tags"]))
            score  += overlap * 0.1

        if score > RECALL_THRESHOLD:
            new_strength = min(1.0, entry["strength"] + 0.1)
            new_count    = entry["recall_count"] + 1

            if tier == "stm":
                update_stm_recall(entry["id"], new_strength, new_count)
                if new_count >= PROMOTION_THRESHOLD:
                    promote_stm_to_ltm(entry, user_id)
            else:
                update_ltm_recall(entry["id"], new_strength, new_count)

            results.append(f"[{tier.upper()} {round(score*100)}%] {entry['text']}")

    return "\n".join(results[:5]) if results else None


# ── Context builder ────────────────────────────────────────────────────────────

def _build_context(session_id: str, model: str, memory_context: Optional[str]) -> list:
    """Compression pyramid from DB messages."""
    all_msgs = get_session_messages(session_id)
    msgs     = [m for m in all_msgs if m["role"] in ("user", "assistant")]

    if not msgs:
        return []

    reversed_msgs = list(reversed(msgs))
    context_parts = []

    for i, msg in enumerate(reversed_msgs):
        pos = i + 1
        if pos <= VERBATIM_COUNT:
            context_parts.append({"role": msg["role"], "content": msg["content"], "_pos": pos})
        elif 5 <= pos <= 7:
            truncated = msg["content"][:200] + ("..." if len(msg["content"]) > 200 else "")
            context_parts.append({"role": msg["role"], "content": truncated, "_pos": pos})
        elif pos == 8:
            # Summarize group 8-20
            group = reversed_msgs[7:20]
            summary = _summarize_group([m for m in reversed(group)], model)
            if summary:
                context_parts.append({"role": "user", "content": summary, "_pos": pos})
            break
        else:
            break

    context_parts.reverse()
    clean = [{"role": p["role"], "content": p["content"]} for p in context_parts]

    if memory_context:
        clean.insert(0, {"role": "user",      "content": f"[MEMORY]\n{memory_context}"})
        clean.insert(1, {"role": "assistant", "content": "I have reviewed the memory context."})

    return clean


def _summarize_group(messages: list, model: str) -> str:
    if not messages:
        return ""
    text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        res = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": f"Summarize in 2 sentences preserving key facts:\n\n{text}"}]
        )
        return f"[SUMMARY of {len(messages)} messages]: {res.content[0].text}"
    except Exception:
        words = text.split()
        return f"[SUMMARY]: {' '.join(words[:80])}..."


# ── Cache → STM compression ────────────────────────────────────────────────────

def _compress_cache_to_stm(session_id: str, model: str, user_id: str = "default"):
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
    """Generate a short session title from first message + pillars."""
    words  = text.split()[:6]
    snippet = " ".join(words)
    return f"{classified.core} · {snippet}"


# ── AI Providers ───────────────────────────────────────────────────────────────

def _call_anthropic(model, system, messages):
    import anthropic
    c = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    r = c.messages.create(model=model, max_tokens=1024, system=system, messages=messages)
    return r.content[0].text

def _call_gemini(model, system, messages):
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    m = genai.GenerativeModel(model, system_instruction=system)
    h = [{"role": "user" if msg["role"]=="user" else "model", "parts":[msg["content"]]} for msg in messages[:-1]]
    return m.start_chat(history=h).send_message(messages[-1]["content"]).text

def _call_openai_compat(model, system, messages, api_key, base_url=None):
    from openai import OpenAI
    kw = {"api_key": api_key}
    if base_url: kw["base_url"] = base_url
    c = OpenAI(**kw)
    r = c.chat.completions.create(model=model,
        messages=[{"role":"system","content":system}]+messages, max_tokens=1024)
    return r.choices[0].message.content

def _call_mistral(model, system, messages):
    from mistralai import Mistral
    c = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
    r = c.chat.complete(model=model,
        messages=[{"role":"system","content":system}]+messages, max_tokens=1024)
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
        return _call_openai_compat(model, system, messages, os.getenv("OPENAI_API_KEY"))
    elif "sonar" in model:
        return _call_openai_compat(model, system, messages,
            os.getenv("PERPLEXITY_API_KEY"), "https://api.perplexity.ai")
    elif model.startswith("llama") or model.startswith("deepseek-r1-distill") or model.startswith("mixtral"):
        return _call_openai_compat(model, system, messages,
            os.getenv("GROQ_API_KEY"), "https://api.groq.com/openai/v1")
    elif model.startswith("deepseek"):
        return _call_openai_compat(model, system, messages,
            os.getenv("DEEPSEEK_API_KEY"), "https://api.deepseek.com/v1")
    elif model.startswith("qwen"):
        return _call_openai_compat(model, system, messages,
            os.getenv("QWEN_API_KEY"), "https://dashscope.aliyuncs.com/compatible-mode/v1")
    elif model.startswith("glm"):
        return _call_openai_compat(model, system, messages,
            os.getenv("ZHIPU_API_KEY"), "https://open.bigmodel.cn/api/paas/v4")
    elif model.startswith("moonshot"):
        return _call_openai_compat(model, system, messages,
            os.getenv("MOONSHOT_API_KEY"), "https://api.moonshot.cn/v1")
    elif model.startswith("command"):
        import cohere
        c = cohere.Client(api_key=os.getenv("COHERE_API_KEY"))
        h = [{"role":"USER" if m["role"]=="user" else "CHATBOT","message":m["content"]} for m in messages[:-1]]
        return c.chat(model=model, preamble=system, chat_history=h, message=messages[-1]["content"]).text
    elif "/" in model:
        return _call_openai_compat(model, system, messages,
            os.getenv("TOGETHER_API_KEY"), "https://api.together.xyz/v1")
    else:
        return _call_anthropic("claude-sonnet-4-20250514", system, messages)


# ── System prompt ──────────────────────────────────────────────────────────────

def _build_system_prompt(classified, memory_context: Optional[str]) -> str:
    prompt = f"""You are a warm, patient AI companion with memory across conversations.

Current context:
- Domain:   {classified.core}
- Emotion:  {classified.emotion}
- Intent:   {classified.functional}
- Strength: {round(classified.core_score * 100)}%
"""
    if memory_context:
        prompt += f"\nWhat I remember about this person:\n{memory_context}\n"
    prompt += "\nBe warm, patient and helpful. Use memory naturally without making it obvious."
    return prompt


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def process_input(text: str, model: str,
                        session_id: Optional[str],
                        user_id: str = "default") -> dict:

    # 1. Get/create session
    session = get_or_create_session(session_id, model, user_id)
    sid     = session["id"]
    update_session_weight(sid)

    # 2. Classify input
    classified = classify_input(text)

    # 3. Save user message to DB
    save_message(
        session_id=sid, role="user", content=text, model=model,
        pillar_core=classified.core, pillar_emotion=classified.emotion,
        pillar_functional=classified.functional,
        pillar_modifiers=classified.modifiers,
        pillar_score=classified.core_score,
    )

    # 4. Auto-title session on first message
    msgs = get_session_messages(sid)
    if len(msgs) == 1:
        update_session_title(sid, _generate_title(text, classified))

    # 5. Update in-memory cache
    update_cache(classified, session_id=sid, model=model)

    # 6. Register pillar correlations
    register_pillars(classified, session_id=sid, model=model)

    # 7. Decay tick
    track_decay()

    # 8. Compress cache → STM in DB
    _compress_cache_to_stm(sid, model, user_id)

    # 9. Retrieve memory context
    memory_context = _retrieve_memory(
        text, sid,
        pillar_tags=[classified.core, classified.emotion, classified.functional],
        user_id=user_id,
    )

    # 10. Build context window
    context_messages = _build_context(sid, model, memory_context)
    if not context_messages or context_messages[-1].get("content") != text:
        context_messages.append({"role": "user", "content": text})

    # 11. Build system prompt
    system_prompt = _build_system_prompt(classified, memory_context)

    # 12. Call AI
    reply = _route(model, system_prompt, context_messages)

    # 13. Save assistant message to DB
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
        "memory_used":  memory_context is not None,
        "model":        model,
    }

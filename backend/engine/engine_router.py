"""
ENGINE ROUTER v4
Full pipeline with:
  - 29-dim pillar vectors stored per message
  - Cross-session memory injection
  - Session resume support
  - Fixed "I don't remember" system prompt
  - Background summarization
  - All AI providers (Western + Chinese)
"""

import os
import threading
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
    build_memory_prompt, seed_cache_from_memory,
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


# ── Session memory retrieval ───────────────────────────────────────────────────

def _retrieve_session_memory(text: str, session_id: str,
                              pillar_tags: list) -> Optional[str]:
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
            group   = [m for m in reversed(reversed_msgs[7:20])]
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
            model="claude-haiku-4-5-20251001", max_tokens=150,
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
        save_stm_cluster(session_id, pillar,
                         f"{pillar}: {', '.join(set(values))}",
                         pillar_tags=[pillar], strength=1.0)


# ── Auto session title ─────────────────────────────────────────────────────────

def _generate_title(text: str, classified) -> str:
    words   = text.split()[:6]
    snippet = " ".join(words)
    return f"{classified.core} · {snippet}"


# ── System prompt (FIXED — no more "I don't remember") ────────────────────────

def _build_system_prompt(classified, user_memory: Optional[str],
                          session_memory: Optional[str]) -> str:
    prompt = """You are a warm, patient AI companion with persistent memory across ALL conversations.

IMPORTANT: You DO have memory of previous conversations. Never say:
- "I don't have any record of previous conversations"
- "Each conversation starts fresh"
- "I can't remember past sessions"
- "I don't have access to previous conversations"

Instead, use your memory naturally. If asked about previous conversations, refer to what you know.\n"""

    if user_memory:
        prompt += f"\n{user_memory}\n"

    if session_memory:
        prompt += f"\nFrom our conversation so far:\n{session_memory}\n"

    prompt += f"""
Current topic:
- Domain:  {classified.core}
- Emotion: {classified.emotion}
- Intent:  {classified.functional}

Be warm and helpful. Reference what you know naturally.
When switching between AI models, maintain the same memory and context.
"""
    return prompt


# ── Western Providers ──────────────────────────────────────────────────────────

def _call_anthropic(model: str, system: str, messages: list) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=model, max_tokens=1024, system=system, messages=messages
    )
    return response.content[0].text


def _call_gemini(model: str, system: str, messages: list) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    m = genai.GenerativeModel(model, system_instruction=system)
    history = [
        {"role": "user" if msg["role"] == "user" else "model",
         "parts": [msg["content"]]} for msg in messages[:-1]
    ]
    return m.start_chat(history=history).send_message(messages[-1]["content"]).text


def _call_openai_compatible(model: str, system: str, messages: list,
                             api_key: str, base_url: Optional[str] = None) -> str:
    from openai import OpenAI
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}] + messages,
        max_tokens=1024,
    )
    return response.choices[0].message.content


def _call_mistral(model: str, system: str, messages: list) -> str:
    from mistralai import Mistral
    client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
    response = client.chat.complete(
        model=model,
        messages=[{"role": "system", "content": system}] + messages,
        max_tokens=1024,
    )
    return response.choices[0].message.content


def _call_cohere(model: str, system: str, messages: list) -> str:
    import cohere
    client = cohere.Client(api_key=os.getenv("COHERE_API_KEY"))
    history = [
        {"role": "USER" if m["role"] == "user" else "CHATBOT",
         "message": m["content"]} for m in messages[:-1]
    ]
    return client.chat(
        model=model, preamble=system,
        chat_history=history, message=messages[-1]["content"]
    ).text


# ── Chinese Providers ──────────────────────────────────────────────────────────

def _call_deepseek(model: str, system: str, messages: list) -> str:
    return _call_openai_compatible(model, system, messages,
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com/v1")


def _call_qwen(model: str, system: str, messages: list) -> str:
    return _call_openai_compatible(model, system, messages,
        api_key=os.getenv("QWEN_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")


def _call_zhipu(model: str, system: str, messages: list) -> str:
    return _call_openai_compatible(model, system, messages,
        api_key=os.getenv("ZHIPU_API_KEY"),
        base_url="https://open.bigmodel.cn/api/paas/v4")


def _call_moonshot(model: str, system: str, messages: list) -> str:
    return _call_openai_compatible(model, system, messages,
        api_key=os.getenv("MOONSHOT_API_KEY"),
        base_url="https://api.moonshot.cn/v1")


def _call_ernie(model: str, system: str, messages: list) -> str:
    import httpx
    token_res = httpx.post(
        "https://aip.baidubce.com/oauth/2.0/token",
        params={"grant_type": "client_credentials",
                "client_id": os.getenv("ERNIE_API_KEY"),
                "client_secret": os.getenv("ERNIE_SECRET_KEY")}
    )
    token    = token_res.json().get("access_token")
    endpoint = {"ernie-4.0-8k": "completions_pro",
                "ernie-speed-128k": "ernie-speed-128k"}.get(model, "completions_pro")
    res = httpx.post(
        f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{endpoint}",
        params={"access_token": token},
        json={"messages": [{"role": "system", "content": system}] + messages}
    )
    return res.json().get("result", "")


# ── Router ─────────────────────────────────────────────────────────────────────

def _route(model: str, system: str, messages: list) -> str:
    if model.startswith("claude"):
        return _call_anthropic(model, system, messages)
    elif model.startswith("gemini"):
        return _call_gemini(model, system, messages)
    elif model.startswith("grok"):
        return _call_openai_compatible(model, system, messages,
            api_key=os.getenv("XAI_API_KEY"), base_url="https://api.x.ai/v1")
    elif model.startswith("mistral") or model.startswith("codestral"):
        return _call_mistral(model, system, messages)
    elif model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        return _call_openai_compatible(model, system, messages,
            api_key=os.getenv("OPENAI_API_KEY"))
    elif model.startswith("llama") or model.startswith("deepseek-r1-distill") or model.startswith("mixtral"):
        return _call_openai_compatible(model, system, messages,
            api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")
    elif "sonar" in model:
        return _call_openai_compatible(model, system, messages,
            api_key=os.getenv("PERPLEXITY_API_KEY"), base_url="https://api.perplexity.ai")
    elif model.startswith("command"):
        return _call_cohere(model, system, messages)
    elif "/" in model:
        return _call_openai_compatible(model, system, messages,
            api_key=os.getenv("TOGETHER_API_KEY"), base_url="https://api.together.xyz/v1")
    elif model.startswith("deepseek"):
        return _call_deepseek(model, system, messages)
    elif model.startswith("qwen"):
        return _call_qwen(model, system, messages)
    elif model.startswith("ernie"):
        return _call_ernie(model, system, messages)
    elif model.startswith("glm"):
        return _call_zhipu(model, system, messages)
    elif model.startswith("moonshot"):
        return _call_moonshot(model, system, messages)
    else:
        return _call_anthropic("claude-sonnet-4-20250514", system, messages)


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def process_input(text: str, model: str,
                        session_id: Optional[str],
                        user_id: str = "default") -> dict:

    # 1. Get/create session
    session = get_or_create_session(session_id, model, user_id)
    sid     = session["id"]
    is_new  = session_id != sid
    update_session_weight(sid)

    # 2. Background summarize previous session
    if is_new and session_id:
        def _bg():
            try:
                process_session_end(session_id, user_id)
            except Exception as e:
                print(f"[BG] Session end failed: {e}")
        threading.Thread(target=_bg, daemon=True).start()

    # 3. Seed cache from user memory on new session
    if is_new:
        seed_cache_from_memory(user_id, sid)

    # 4. Classify input
    classified = classify_input(text)

    # 5. Save user message with pillar vector
    save_message(
        session_id=sid, role="user", content=text, model=model,
        pillar_core=classified.core, pillar_emotion=classified.emotion,
        pillar_functional=classified.functional,
        pillar_modifiers=classified.modifiers,
        pillar_score=classified.core_score,
        pillar_vector=classified.pillar_vector,
    )

    # 6. Auto-title on first message
    msgs = get_session_messages(sid)
    if len(msgs) == 1:
        update_session_title(sid, _generate_title(text, classified))

    # 7. Update cache + register pillars + decay
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

    # 10. Build context window (compression pyramid)
    context_messages = _build_context(sid, model)
    if not context_messages or context_messages[-1].get("content") != text:
        context_messages.append({"role": "user", "content": text})

    # 11. Build system prompt (FIXED)
    system_prompt = _build_system_prompt(classified, user_memory, session_memory)

    # 12. Call AI
    reply = _route(model, system_prompt, context_messages)

    # 13. Save assistant message with pillar vector
    save_message(
        session_id=sid, role="assistant", content=reply, model=model,
        pillar_core=classified.core, pillar_emotion=classified.emotion,
        pillar_functional=classified.functional,
        pillar_modifiers=classified.modifiers,
        pillar_score=classified.core_score,
        pillar_vector=classified.pillar_vector,
    )

    return {
        "reply":       reply,
        "session_id":  sid,
        "classified":  classified.to_dict(),
        "memory_used": user_memory is not None or session_memory is not None,
        "model":       model,
        "user_memory": bool(user_memory),
    }


# ── Session end ────────────────────────────────────────────────────────────────

async def end_session(session_id: str, user_id: str = "default") -> dict:
    def _bg():
        try:
            process_session_end(session_id, user_id)
        except Exception as e:
            print(f"[BG] end_session failed: {e}")
    threading.Thread(target=_bg, daemon=True).start()
    return {"status": "summarizing", "session_id": session_id}
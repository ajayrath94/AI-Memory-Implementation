"""
ENGINE ROUTER
Full pipeline per turn:
1. Classify input → pillars + matrix
2. Update hot cache
3. Register pillar correlations
4. Run decay tick
5. Compress cache → recall
6. Retrieve memory context (cosine similarity)
7. Build context window (compression pyramid)
8. Build system prompt
9. Route to correct AI provider
10. Save messages with full metadata
"""

import os
from typing import Optional
from dotenv import load_dotenv

from classifier.pillar_classifier import classify_input
from memory.cache.cache_memory import update_cache
from memory.recall.recall_memory import build_memory_context, compress_to_recall
from memory.decay.decay_memory import track_decay
from store.pillar_vector_store import register_pillars
from utils.chat_store import get_or_create_session, save_message, update_session_weight
from utils.context_builder import build_context
from utils.models import ChatMessage, PillarTag

load_dotenv()


# ── Provider handlers ──────────────────────────────────────────────────────────

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
        {"role": "user" if msg["role"] == "user" else "model", "parts": [msg["content"]]}
        for msg in messages[:-1]
    ]
    return m.start_chat(history=history).send_message(messages[-1]["content"]).text


def _call_openai_compatible(model: str, system: str, messages: list,
                             api_key: str, base_url: Optional[str] = None) -> str:
    from openai import OpenAI
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client   = OpenAI(**kwargs)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}] + messages,
        max_tokens=1024,
    )
    return response.choices[0].message.content


def _call_mistral(model: str, system: str, messages: list) -> str:
    from mistralai import Mistral
    client   = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
    response = client.chat.complete(
        model=model,
        messages=[{"role": "system", "content": system}] + messages,
        max_tokens=1024,
    )
    return response.choices[0].message.content


def _call_cohere(model: str, system: str, messages: list) -> str:
    import cohere
    client  = cohere.Client(api_key=os.getenv("COHERE_API_KEY"))
    history = [
        {"role": "USER" if m["role"] == "user" else "CHATBOT", "message": m["content"]}
        for m in messages[:-1]
    ]
    return client.chat(
        model=model, preamble=system,
        chat_history=history, message=messages[-1]["content"]
    ).text


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
    elif "sonar" in model:
        return _call_openai_compatible(model, system, messages,
            api_key=os.getenv("PERPLEXITY_API_KEY"), base_url="https://api.perplexity.ai")
    elif model.startswith("llama") or model.startswith("deepseek-r1-distill") or model.startswith("mixtral"):
        return _call_openai_compatible(model, system, messages,
            api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")
    elif model.startswith("deepseek"):
        return _call_openai_compatible(model, system, messages,
            api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com/v1")
    elif model.startswith("qwen"):
        return _call_openai_compatible(model, system, messages,
            api_key=os.getenv("QWEN_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    elif model.startswith("glm"):
        return _call_openai_compatible(model, system, messages,
            api_key=os.getenv("ZHIPU_API_KEY"), base_url="https://open.bigmodel.cn/api/paas/v4")
    elif model.startswith("moonshot"):
        return _call_openai_compatible(model, system, messages,
            api_key=os.getenv("MOONSHOT_API_KEY"), base_url="https://api.moonshot.cn/v1")
    elif model.startswith("command"):
        return _call_cohere(model, system, messages)
    elif "/" in model:
        return _call_openai_compatible(model, system, messages,
            api_key=os.getenv("TOGETHER_API_KEY"), base_url="https://api.together.xyz/v1")
    else:
        return _call_anthropic("claude-sonnet-4-20250514", system, messages)


# ── System prompt ──────────────────────────────────────────────────────────────

def _build_system_prompt(classified, memory_context: Optional[str]) -> str:
    prompt = f"""You are a memory-aware AI assistant that remembers context across conversations.

Current input classification:
- Core domain:    {classified.core}
- Emotional tone: {classified.emotion}
- User intent:    {classified.functional}
- Modifiers:      {', '.join(classified.modifiers) or 'none'}
- Match strength: {round(classified.core_score * 100)}%
"""
    if memory_context:
        prompt += f"\nLong-term memory context (use this to personalize responses):\n{memory_context}\n"

    prompt += "\nRespond naturally and helpfully. Reference memory context when relevant without making it obvious."
    return prompt


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def process_input(text: str, model: str, session_id: Optional[str]) -> dict:
    # 1. Get or create session
    session = get_or_create_session(session_id, model)
    update_session_weight(session.id)

    # 2. Save user message
    classified = classify_input(text)
    pillar_tag = PillarTag(
        core=classified.core, emotion=classified.emotion,
        functional=classified.functional, modifiers=classified.modifiers,
        matrix=classified.matrix.to_dict()
    )
    user_msg = ChatMessage(
        session_id=session.id, model=model, role="user",
        content=text, pillar=pillar_tag, memory_tier="cache"
    )
    save_message(user_msg)

    # 3. Update cache with classified input
    update_cache(classified, session_id=session.id, model=model)

    # 4. Register pillar correlations
    register_pillars(classified, session_id=session.id, model=model)

    # 5. Run decay tick
    track_decay()

    # 6. Compress cache → recall store
    compress_to_recall(session_id=session.id, model=model)

    # 7. Retrieve memory context
    memory_context = build_memory_context(
        text, pillar_tags=[classified.core, classified.emotion, classified.functional]
    )

    # 8. Build context window (compression pyramid)
    context_messages = build_context(session.id, model, memory_context)

    # 9. Build system prompt
    system_prompt = _build_system_prompt(classified, memory_context)

    # 10. Add current user message if not already in context
    if not context_messages or context_messages[-1].get("content") != text:
        context_messages.append({"role": "user", "content": text})

    # 11. Call AI
    reply = _route(model, system_prompt, context_messages)

    # 12. Save assistant message
    assistant_msg = ChatMessage(
        session_id=session.id, model=model, role="assistant",
        content=reply, pillar=pillar_tag, memory_tier="cache"
    )
    save_message(assistant_msg)

    return {
        "reply":       reply,
        "session_id":  session.id,
        "message_id":  assistant_msg.id,
        "classified":  classified.to_dict(),
        "memory_used": memory_context is not None,
        "model":       model,
    }

"""
ENGINE ROUTER
Routes to the correct AI provider. Full memory pipeline runs before every call.
Providers: Anthropic (claude-*) | OpenAI (gpt-*) | Google (gemini-*)
"""

import os
from typing import Optional
from dotenv import load_dotenv
from classifier.pillar_classifier import classify_input
from memory.cache.cache_memory import update_cache
from memory.recall.recall_memory import build_memory_context, compress_to_recall
from memory.decay.decay_memory import track_decay
from store.pillar_vector_store import register_pillars

load_dotenv()


def _get_anthropic():
    import anthropic
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _get_openai():
    from openai import OpenAI
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _get_gemini():
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    return genai


def _build_system_prompt(memory_context: Optional[str], classified) -> str:
    prompt = f"""You are a memory-aware AI assistant.

Current context:
- Core pillar:       {classified.core}
- Emotion pillar:    {classified.emotion}
- Functional pillar: {classified.functional}
- Modifiers:         {', '.join(classified.modifiers) or 'none'}
"""
    if memory_context:
        prompt += f"\nRelevant memory:\n{memory_context}\n"
    prompt += "\nRespond naturally. Use memory context when relevant."
    return prompt


def _call_anthropic(model: str, system: str, messages: list) -> str:
    client   = _get_anthropic()
    response = client.messages.create(
        model=model, max_tokens=1024, system=system, messages=messages
    )
    return response.content[0].text


def _call_openai(model: str, system: str, messages: list) -> str:
    client        = _get_openai()
    full_messages = [{"role": "system", "content": system}] + messages
    response      = client.chat.completions.create(
        model=model, messages=full_messages, max_tokens=1024
    )
    return response.choices[0].message.content


def _call_gemini(model: str, system: str, messages: list) -> str:
    genai    = _get_gemini()
    m        = genai.GenerativeModel(model, system_instruction=system)
    history  = []
    for msg in messages[:-1]:
        history.append({
            "role":  "user" if msg["role"] == "user" else "model",
            "parts": [msg["content"]]
        })
    chat     = m.start_chat(history=history)
    response = chat.send_message(messages[-1]["content"])
    return response.text


async def process_input(text: str, model: str, history: list) -> dict:
    # 1. Classify
    classified = classify_input(text)
    # 2. Update cache
    update_cache(classified)
    # 3. Track pillar correlations
    register_pillars(classified)
    # 4. Decay tick
    track_decay()
    # 5. Compress cache → recall
    compress_to_recall()
    # 6. Retrieve memory
    memory_context = build_memory_context(text)
    # 7. Build prompt
    system_prompt = _build_system_prompt(memory_context, classified)
    # 8. Format messages
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": text})
    # 9. Route to provider
    if model.startswith("claude"):
        reply = _call_anthropic(model, system_prompt, messages)
    elif model.startswith("gpt"):
        reply = _call_openai(model, system_prompt, messages)
    elif model.startswith("gemini"):
        reply = _call_gemini(model, system_prompt, messages)
    else:
        reply = _call_anthropic("claude-sonnet-4-20250514", system_prompt, messages)

    return {
        "reply": reply,
        "classified": {
            "core":       classified.core,
            "emotion":    classified.emotion,
            "functional": classified.functional,
            "modifiers":  classified.modifiers,
        },
        "memory_used": memory_context is not None,
    }

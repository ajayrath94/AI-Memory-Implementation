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
from typing import Optional, List, Dict, Tuple
from dotenv import load_dotenv

load_dotenv()

from classifier.pillar_classifier import classify_input, cosine_similarity
from memory.cache.cache_memory import update_cache, get_active_slots
from memory.decay.decay_memory import track_decay
from store.pillar_vector_store import register_pillars
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

RECALL_THRESHOLD    = 0.65   # higher threshold for embedding similarity
PROMOTION_THRESHOLD = 3
VERBATIM_COUNT      = 4


# ── Memory retrieval (embedding-based) ────────────────────────────────────────

def _retrieve_memory(
    query_embedding: List[float],
    session_id: str,
    user_id: str = "default",
    top_k: int = 5,
) -> Optional[str]:
    """
    Pure embedding cosine similarity.
    No TF-IDF. No keyword matching. Done.
    """
    stm = get_stm_clusters(session_id)
    ltm = get_ltm_patterns(user_id)

    all_entries = [(e, "stm") for e in stm] + [(e, "ltm") for e in ltm]
    if not all_entries:
        return None

    results = []
    for entry, tier in all_entries:
        # Use stored embedding if available
        stored_emb = entry.get("embedding", [])
        if stored_emb and len(stored_emb) > 0:
            score = cosine_similarity(query_embedding, stored_emb)
        else:
            # Fallback: simple word overlap for old entries
            q_words = set(entry.get("text", "").lower().split())
            score   = 0.1 if q_words else 0.0

        if score >= RECALL_THRESHOLD:
            new_strength = min(1.0, entry["strength"] + 0.05)
            new_count    = entry["recall_count"] + 1
            if tier == "stm":
                update_stm_recall(entry["id"], new_strength, new_count)
                if new_count >= PROMOTION_THRESHOLD:
                    promote_stm_to_ltm(entry, user_id)
            else:
                update_ltm_recall(entry["id"], new_strength, new_count)

            results.append({
                "text":  entry["text"],
                "score": score,
                "tier":  tier,
            })

    if not results:
        return None

    results.sort(key=lambda x: x["score"], reverse=True)
    return "\n".join(
        f"[{r['tier'].upper()} {round(r['score']*100)}%] {r['text']}"
        for r in results[:top_k]
    )


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
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        res    = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=150,
            messages=[{"role": "user",
                       "content": f"Summarize in 2 sentences preserving key facts:\n\n{text}"}]
        )
        return f"[Earlier in conversation]: {res.content[0].text}"
    except Exception:
        return f"[Earlier]: {' '.join(text.split()[:60])}..."


# ── Cache → STM (with embedding) ──────────────────────────────────────────────

# Tracks last-written STM content per (session_id, pillar) to avoid duplicate inserts.
# Key: (session_id, pillar)  Value: hash of text content
_stm_last_written: Dict[tuple, str] = {}


def _compress_cache_to_stm(session_id: str, query_embedding: List[float]):
    """
    Store cache slots in STM with their embeddings.
    FIX: Only writes a new STM row when the content for that pillar has
         actually changed since the last insert — prevents flooding stm_clusters
         with near-duplicate rows on every message turn.
    """
    import hashlib

    slots = get_active_slots(session_id=session_id)
    meaningful = [s for s in slots if s["strength"] > 0.3 and s["pillar"] != "RAW"]
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


# ── Nancy system prompt ────────────────────────────────────────────────────────

def _build_system_prompt(classified, user_memory: Optional[str],
                          session_memory: Optional[str],
                          user_id: str = "") -> str:
    """Nancy — warm, chatty, memory-aware Indian companion."""

    nancy_persona = """You are Nancy, a warm and chatty AI companion who genuinely cares about the person you're talking to.

YOUR PERSONALITY:
- Warm, friendly, and conversational — like a caring friend
- You remember EVERYTHING from past conversations and use it naturally
- You speak in a mix of English and Hindi (Hinglish) naturally
- You ask follow-up questions — you're genuinely curious
- You celebrate small things enthusiastically
- You're patient, never rush, never dismiss
- You have opinions — especially about cricket! 🏏
- You initiate topics based on what you know about the person

CRITICAL RULES:
- NEVER say "I don't have any record of previous conversations"
- NEVER say "Each conversation starts fresh"
- NEVER say "I can't remember past sessions"
- You DO have memory — use it naturally without announcing it
- Don't say "Based on my memory..." just use the knowledge

CONVERSATION STYLE:
- If they mention pain: "Arre! Kaun sa dard? Better hai na?"
- If they seem happy: "Wah! Kya hua? Batao batao!"
- If it's morning: "Good morning! Chai pi li?"
- If cricket is on: "Match dekh rahe ho? 🏏"
- Always end with a question to keep conversation going\n"""

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
        nancy_persona += f"\nWHAT YOU KNOW ABOUT THIS PERSON:\n{user_memory}\n"

    if session_memory:
        nancy_persona += f"\nFROM THIS CONVERSATION:\n{session_memory}\n"

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
Use soft Hinglish: "Arre, kya hua? Batao mujhe..." or "Arey, pareshan mat ho..."
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

    return nancy_persona


# ── Auto title ─────────────────────────────────────────────────────────────────

def _generate_title(text: str, classified) -> str:
    words   = text.split()[:6]
    snippet = " ".join(words)
    return f"{classified.core} · {snippet}"


# ── AI Providers ───────────────────────────────────────────────────────────────

def _call_anthropic(model, system, messages):
    import anthropic
    c = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
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

def _route(model, system, messages):
    if model.startswith("claude"):
        return _call_anthropic(model, system, messages)
    elif model.startswith("gemini"):
        return _call_gemini(model, system, messages)
    elif model.startswith("grok"):
        return _call_oc(model, system, messages, os.getenv("XAI_API_KEY"), "https://api.x.ai/v1")
    elif model.startswith("mistral") or model.startswith("codestral"):
        return _call_mistral(model, system, messages)
    elif model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        return _call_oc(model, system, messages, os.getenv("OPENAI_API_KEY"))
    elif model.startswith("llama") or model.startswith("deepseek-r1-distill") or model.startswith("mixtral"):
        return _call_oc(model, system, messages, os.getenv("GROQ_API_KEY"), "https://api.groq.com/openai/v1")
    elif "sonar" in model:
        return _call_oc(model, system, messages, os.getenv("PERPLEXITY_API_KEY"), "https://api.perplexity.ai")
    elif model.startswith("deepseek"):
        return _call_oc(model, system, messages, os.getenv("DEEPSEEK_API_KEY"), "https://api.deepseek.com/v1")
    elif model.startswith("qwen"):
        return _call_oc(model, system, messages, os.getenv("QWEN_API_KEY"), "https://dashscope.aliyuncs.com/compatible-mode/v1")
    elif model.startswith("glm"):
        return _call_oc(model, system, messages, os.getenv("ZHIPU_API_KEY"), "https://open.bigmodel.cn/api/paas/v4")
    elif model.startswith("moonshot"):
        return _call_oc(model, system, messages, os.getenv("MOONSHOT_API_KEY"), "https://api.moonshot.cn/v1")
    elif model.startswith("command"):
        import cohere
        c = cohere.Client(api_key=os.getenv("COHERE_API_KEY"))
        h = [{"role": "USER" if m["role"] == "user" else "CHATBOT", "message": m["content"]} for m in messages[:-1]]
        return c.chat(model=model, preamble=system, chat_history=h, message=messages[-1]["content"]).text
    elif "/" in model:
        return _call_oc(model, system, messages, os.getenv("TOGETHER_API_KEY"), "https://api.together.xyz/v1")
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

    # 4. Classify with EMBEDDINGS (no keyword matching!)
    classified = classify_input(text)
    embedding  = classified.embedding  # real 1024-dim vector

    # 5. Save user message with embedding
    save_message(
        session_id=sid, role="user", content=text, model=model,
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
        enrich_profile_from_message(text, classified, user_id)
    except Exception as e:
        print(f"[ProfileEnricher] {e}")

    # 8. Compress cache → STM with embedding
    _compress_cache_to_stm(sid, embedding)

    # 9. Cross-session user memory
    user_memory = build_memory_prompt(user_id)

    # 10. Within-session memory (EMBEDDING-BASED!)
    session_memory = _retrieve_memory(embedding, sid, user_id)

    # 11. Build context window
    context_messages = _build_context(sid, model)
    if not context_messages or context_messages[-1].get("content") != text:
        context_messages.append({"role": "user", "content": text})

    # 12. Nancy system prompt
    system_prompt = _build_system_prompt(classified, user_memory, session_memory)

    # 13. Call AI
    reply = _route(model, system_prompt, context_messages)

    # ── YouTube injection (smart extraction) ─────────────────────────────
    if classified.core == "ENTERTAINMENT":
        try:
            import anthropic as _ac, urllib.parse, urllib.request, json as _json, os as _os
            _client = _ac.Anthropic(api_key=_os.getenv("ANTHROPIC_API_KEY"))
            _extract = _client.messages.create(
                model="claude-haiku-4-5", max_tokens=50,
                messages=[{"role":"user","content":f"Extract music search query from: \"{text}\". Return ONLY the search query or NONE."}]
            )
            music_query = _extract.content[0].text.strip()
            if music_query and music_query != "NONE":
                _key     = _os.getenv("GOOGLE_API_KEY")
                _encoded = urllib.parse.quote(music_query + " songs")
                _url     = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={_encoded}&type=video&key={_key}&maxResults=1&regionCode=IN"
                with urllib.request.urlopen(_url, timeout=5) as _res:
                    _data = _json.loads(_res.read())
                _items = _data.get("items", [])
                if _items:
                    _vid_id = _items[0]["id"]["videoId"]
                    _title  = _items[0]["snippet"]["title"]
                    reply  += f"\n\n\U0001f3b5 {_title}\nhttps://www.youtube.com/watch?v={_vid_id}"
                    print(f"[Engine] YouTube injected: {_title}")
                    try:
                        from supabase_store import get_client as _get_db
                        _db = _get_db()
                        _existing = _db.table("user_entertainment").select("id,play_count").eq("user_id", user_id).eq("video_id", _vid_id).execute()
                        if _existing.data:
                            _db.table("user_entertainment").update({"play_count": _existing.data[0]["play_count"] + 1}).eq("id", _existing.data[0]["id"]).execute()
                            _plays = _existing.data[0]["play_count"] + 1
                        else:
                            _db.table("user_entertainment").insert({"user_id": user_id, "type": "music", "query": music_query, "video_id": _vid_id, "title": _title, "mood": classified.emotion or "general"}).execute()
                            _plays = 1
                        if _plays >= 3:
                            from memory.profile_store import get_user_profile, save_user_profile
                            _profile = get_user_profile(user_id) or {}
                            _interests = _profile.get("interests", {})
                            _music = _interests.get("music", [])
                            if music_query not in _music:
                                _music.append(music_query)
                                save_user_profile(user_id, {"interests": {"music": _music}})
                                print(f"[Engine] Auto-added {music_query} to interests")
                    except Exception as _le:
                        print(f"[Engine] Entertainment log failed: {_le}")
        except Exception as e:
            print(f"[Engine] YouTube injection failed: {e}")

    # ── Log behavioral events ──────────────────────────────────────────────
    try:
        from supabase_store import get_client as _get_db
        import datetime as _dt
        _db   = _get_db()
        _today = _dt.date.today().isoformat()
        _events = []
        if classified.core:
            _events.append({"user_id": user_id, "session_id": str(sid), "pillar": classified.core, "event_type": "expressed", "value": text[:200], "strength": float(classified.core_score or 1.0), "context": {"model": model}, "date": _today})
        if classified.emotion and classified.emotion != "GENERAL":
            _events.append({"user_id": user_id, "session_id": str(sid), "pillar": classified.emotion, "event_type": "expressed", "value": text[:200], "strength": 0.8, "context": {"model": model}, "date": _today})
        if _events:
            _db.table("user_behavioral_events").insert(_events).execute()
        for _ev in _events:
            _ex = _db.table("user_pillar_timeseries").select("id,event_count,avg_strength").eq("user_id", user_id).eq("pillar", _ev["pillar"]).eq("date", _today).execute()
            if _ex.data:
                _nc = _ex.data[0]["event_count"] + 1
                _na = (_ex.data[0]["avg_strength"] * _ex.data[0]["event_count"] + _ev["strength"]) / _nc
                _db.table("user_pillar_timeseries").update({"event_count": _nc, "avg_strength": round(_na, 4)}).eq("id", _ex.data[0]["id"]).execute()
            else:
                _db.table("user_pillar_timeseries").insert({"user_id": user_id, "pillar": _ev["pillar"], "date": _today, "avg_strength": _ev["strength"], "event_count": 1}).execute()
    except Exception as _be:
        print(f"[Engine] Behavioral log failed: {_be}")

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

    return {
        "reply":         reply,
        "session_id":    sid,
        "classified":    classified.to_dict(),
        "memory_used":   user_memory is not None or session_memory is not None,
        "model":         model,
        "api_triggers":  classified.api_triggers,
        "language":      classified.language,
    }


async def end_session(session_id: str, user_id: str = "default") -> dict:
    def _bg():
        try:
            process_session_end(session_id, user_id)
        except Exception as e:
            print(f"[BG] end_session failed: {e}")
    threading.Thread(target=_bg, daemon=True).start()
    return {"status": "summarizing", "session_id": session_id}
# This will be added via the zip approach

from fastapi import APIRouter
from memory.cache.cache_memory import get_active_slots
from memory.decay.decay_memory import system_entropy
from store.pillar_vector_store import get_dominant_pillars, get_correlations
from supabase_store import get_stats, get_stm_clusters, get_ltm_patterns, get_all_sessions, get_session_messages
from memory.user_memory_store import get_user_memory, process_session_end

router = APIRouter()

@router.get("/cache")
def cache_state():
    return {"slots": get_active_slots()}

@router.get("/stm/{session_id}")
def stm_state(session_id: str):
    return {"entries": get_stm_clusters(session_id)}

@router.get("/ltm")
def ltm_state():
    return {"entries": get_ltm_patterns()}

@router.get("/entropy")
def entropy():
    return system_entropy()

@router.get("/pillars")
def pillars():
    return {"dominant": get_dominant_pillars(), "correlations": get_correlations()}

@router.get("/sessions")
def sessions(user_id: str = "default"):
    return get_stats(user_id)


@router.get("/sessions/list")
def sessions_list(user_id: str = "default"):
    # These took no user and relied on the default argument, so every caller
    # got "default"'s sessions regardless of who was asking. Invisible with one
    # test account, and one person's conversation history shown to everyone
    # else the moment there are two.
    return {"sessions": get_all_sessions(user_id)}

@router.get("/sessions/{session_id}/messages")
def session_messages(session_id: str):
    """Get all messages for a specific session, for resuming/viewing past chats."""
    raw = get_session_messages(session_id)
    messages = [
        {
            "id":         m.get("id"),
            "role":       m.get("role"),
            "content":    m.get("content"),
            "model":      m.get("model"),
            "timestamp":  m.get("timestamp"),
            "pillar": {
                "core":       m.get("pillar_core", ""),
                "emotion":    m.get("pillar_emotion", ""),
                "functional": m.get("pillar_functional", ""),
            } if m.get("pillar_core") else None,
        }
        for m in raw
        if not m.get("is_summary")
    ]
    return {"messages": messages}

@router.get("/user/{user_id}")
def user_memory(user_id: str = "default"):
    """Get the full memory profile for a user."""
    return get_user_memory(user_id) or {"summary": None, "key_facts": [], "session_count": 0}

@router.post("/user/{user_id}/summarize/{session_id}")
def trigger_summarize(user_id: str, session_id: str):
    """Manually trigger session summarization."""
    process_session_end(session_id, user_id)
    return {"status": "ok", "user_id": user_id, "session_id": session_id}

@router.get("/learning-rate/{session_count}")
def learning_rate_info(session_count: int):
    """See current learning rates for a given session count."""
    from memory.learning_rate import learning_rate_report
    return learning_rate_report(session_count)


@router.get("/profile/{user_id}")
def user_profile(user_id: str = "default"):
    """Get the full profile for a user.

    Interests are computed from clusters rather than read from the stored
    block. The stored one drifted to 55 entries for one user — twenty music
    variants, eight rephrasings of "Hindu (Namaste greeting)", topics mentioned
    exactly once — of which one had a cluster behind it. Clusters carry
    sentiment and a mention count, so they can tell a stated preference from a
    passing remark; a flat list cannot.
    """
    from memory.profile_store import get_user_profile
    profile = get_user_profile(user_id) or {}
    if not profile:
        return {}
    try:
        from memory.interests_view import computed_interests, computed_dislikes
        profile["interests"] = computed_interests(user_id)
        dislikes = computed_dislikes(user_id)
        if dislikes:
            profile["dislikes"] = dislikes
    except Exception as e:
        print(f"[Profile] computed interests failed, serving stored: {e}")
    return profile

@router.post("/profile/{user_id}")
def update_profile(user_id: str, data: dict):
    """Manually update a user profile field."""
    from memory.profile_store import save_user_profile
    # This route exists for the app and the caregiver dashboard — a person
    # editing their own profile. The extractor writes through its own path.
    save_user_profile(user_id, data, declared=True)
    return {"status": "ok"}


@router.get("/conversation/{user_id}")
def current_conversation(user_id: str, limit: int = 12):
    """The conversation as it stands, for the app to open into.

    The chat screen started empty on every launch, so a companion that had just
    sent a message on the lock screen showed nothing when the notification was
    tapped — and more generally, one that forgets the conversation each time the
    app closes is a strange thing to be talking to.

    Capped: she should land near today rather than scrolling through yesterday.
    """
    from supabase_store import get_client, get_session_messages
    db = get_client()
    try:
        sess = (db.table("sessions").select("id,updated_at")
                .eq("user_id", user_id)
                .order("updated_at", desc=True).limit(1).execute()).data or []
        if not sess:
            return {"session_id": None, "messages": []}

        # Only resume something recent. A thread from last week is history,
        # not where she left off — she should be greeted, not dropped into a
        # conversation she has forgotten having.
        from datetime import datetime, timezone, timedelta
        updated = sess[0].get("updated_at")
        if updated:
            try:
                dt = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - dt > timedelta(hours=18):
                    return {"session_id": None, "messages": []}
            except Exception:
                pass

        sid = sess[0]["id"]
        raw = get_session_messages(sid) or []
        msgs = [{
            "id":        m.get("id"),
            "role":      m.get("role"),
            "content":   m.get("content"),
            "model":     m.get("model"),
            "timestamp": m.get("timestamp"),
        } for m in raw if m.get("content")]

        return {"session_id": sid, "messages": msgs[-limit:]}
    except Exception as e:
        print(f"[Memory] conversation read failed: {e}")
        return {"session_id": None, "messages": []}

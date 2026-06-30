"""
MEMORY STATE — One-stop endpoint
Returns the FULL memory picture for a user in a single call:
  - Active cache slots (if any session is live)
  - STM clusters (recent, across sessions)
  - LTM patterns (sorted by strength)
  - user_memory (summary, trends, fingerprint)
  - user_profile (who they are)
  - Live alerts (detected, not necessarily sent)

Built for dashboards and pitch demos — one fetch, full state.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/state/{user_id}")
def full_memory_state(user_id: str, session_id: str = None):
    """
    Returns everything known about a user's memory in one response.
    Pass session_id to also include live cache slots for that session.
    """
    from supabase_store import get_client
    db = get_client()

    state = {
        "user_id": user_id,
        "cache":   {},
        "stm":     [],
        "ltm":     [],
        "user_memory": {},
        "profile": {},
        "alerts":  [],
    }

    # ── Cache (only if session_id provided — cache is in-memory per session) ──
    if session_id:
        try:
            from memory.cache.cache_memory import get_active_slots
            state["cache"] = get_active_slots(session_id) or {}
        except Exception as e:
            state["cache"] = {"error": str(e)}

    # ── STM — across recent sessions for this user ─────────────────────────────
    try:
        sessions = db.table("sessions").select("id").eq("user_id", user_id)\
            .order("created_at", desc=True).limit(10).execute()
        session_ids = [s["id"] for s in (sessions.data or [])]

        if session_ids:
            stm_result = db.table("stm_clusters")\
                .select("id,session_id,pillar,text,strength,recall_count,timestamp")\
                .in_("session_id", session_ids)\
                .order("timestamp", desc=True)\
                .limit(30)\
                .execute()
            state["stm"] = stm_result.data or []
    except Exception as e:
        state["stm"] = []
        state["stm_error"] = str(e)

    # ── LTM — sorted by strength (exclude heavy embedding column) ──────────────
    try:
        ltm_result = db.table("ltm_patterns")\
            .select("id,user_id,pattern_name,text,strength,recall_count,timestamp,fused_pillars,overlap_score")\
            .eq("user_id", user_id)\
            .order("strength", desc=True)\
            .limit(20)\
            .execute()
        state["ltm"] = ltm_result.data or []
    except Exception as e:
        state["ltm"] = []
        state["ltm_error"] = str(e)

    # ── user_memory ──────────────────────────────────────────────────────────────
    try:
        from memory.user_memory_store import get_user_memory
        mem = get_user_memory(user_id)
        if mem:
            # Strip heavy embedding vectors before returning
            mem_clean = {k: v for k, v in mem.items() if k != "session_centroids"}
            state["user_memory"] = mem_clean
    except Exception as e:
        state["user_memory_error"] = str(e)

    # ── profile ──────────────────────────────────────────────────────────────────
    try:
        from memory.profile_store import get_user_profile
        profile = get_user_profile(user_id)
        if profile:
            state["profile"] = profile
    except Exception as e:
        state["profile_error"] = str(e)

    # ── live alerts (detected, not sent) ────────────────────────────────────────
    try:
        from memory.alert_engine import detect_alerts
        state["alerts"] = detect_alerts(user_id)
    except Exception as e:
        state["alerts_error"] = str(e)

    # ── summary counts for quick display ────────────────────────────────────────
    state["counts"] = {
        "cache_slots":  len(state["cache"]) if isinstance(state["cache"], dict) else 0,
        "stm_clusters": len(state["stm"]),
        "ltm_patterns": len(state["ltm"]),
        "sessions":     state["user_memory"].get("session_count", 0),
        "alerts":       len(state["alerts"]),
    }

    return state

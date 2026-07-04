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


@router.get("/interests/{user_id}")
def user_interests(user_id: str):
    """
    Returns interests from two sources:
    1. user_profile.interests (extracted by enricher)
    2. ltm_patterns (recurring topics with strength scores)

    Combined into a ranked list for the UI.
    """
    from supabase_store import get_client
    from memory.profile_store import get_user_profile
    db = get_client()

    profile   = get_user_profile(user_id) or {}
    interests = profile.get("interests", {})

    # Flatten profile interests into structured list
    profile_interests = []
    for category, items in interests.items():
        if isinstance(items, list):
            for item in items:
                profile_interests.append({
                    "source":     "profile",
                    "category":   category,
                    "label":      item,
                    "strength":   1.0,
                    "confidence": "confirmed",
                })

    # Get LTM patterns as "noticed topics"
    ltm_interests = []
    try:
        result = db.table("ltm_patterns")\
            .select("text, strength, recall_count, pattern_name")\
            .eq("user_id", user_id)\
            .order("strength", desc=True)\
            .limit(20)\
            .execute()

        for p in (result.data or []):
            text     = p.get("text", "")
            strength = p.get("strength", 0)
            recalls  = p.get("recall_count", 0)
            if strength > 0.5 and recalls >= 2:
                # Extract readable label from text like "CORE: HEALTH_WELLNESS"
                parts = text.split(": ", 1)
                label = parts[1] if len(parts) > 1 else text
                ltm_interests.append({
                    "source":     "ltm",
                    "category":   "observed",
                    "label":      label,
                    "strength":   round(strength, 2),
                    "recall_count": recalls,
                    "confidence": "high" if strength > 0.8 else "medium",
                })
    except Exception as e:
        pass

    return {
        "user_id":          user_id,
        "profile_interests": profile_interests,
        "ltm_interests":     ltm_interests,
        "total":             len(profile_interests) + len(ltm_interests),
    }


@router.post("/interests/{user_id}/add")
def add_interest(user_id: str, data: dict):
    """Add a new interest manually."""
    from memory.profile_store import get_user_profile, save_user_profile
    category = data.get("category", "hobbies")
    label    = data.get("label", "").strip()
    if not label:
        return {"status": "error", "message": "label required"}

    profile   = get_user_profile(user_id) or {}
    interests = profile.get("interests", {})
    if category not in interests:
        interests[category] = []
    if label not in interests[category]:
        interests[category].append(label)
    save_user_profile(user_id, {"interests": interests})
    return {"status": "ok", "added": label, "category": category}


@router.delete("/interests/{user_id}/remove")
def remove_interest(user_id: str, data: dict):
    """Remove an interest."""
    from memory.profile_store import get_user_profile, save_user_profile
    category = data.get("category", "")
    label    = data.get("label", "").strip()

    profile   = get_user_profile(user_id) or {}
    interests = profile.get("interests", {})
    if category in interests and label in interests[category]:
        interests[category].remove(label)
        save_user_profile(user_id, {"interests": interests})
    return {"status": "ok", "removed": label}


@router.patch("/profile/{user_id}/field")
def update_profile_field(user_id: str, data: dict):
    """
    Update a specific profile field.
    Supports: name, location, age_group, language_pref,
              health.conditions, family.children, etc.
    """
    from memory.profile_store import save_user_profile
    field = data.get("field")
    value = data.get("value")
    if not field:
        return {"status": "error", "message": "field required"}

    # Handle nested fields like "health.conditions"
    if "." in field:
        parts  = field.split(".", 1)
        update = {parts[0]: {parts[1]: value}}
    else:
        update = {field: value}

    save_user_profile(user_id, update)
    return {"status": "ok", "field": field, "value": value}

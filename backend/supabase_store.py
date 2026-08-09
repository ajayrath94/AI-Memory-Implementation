"""
SUPABASE STORE v3
Added embedding support to messages and stm_clusters.
"""

import os
import time
from typing import Optional, List, Dict
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

def get_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(url, key)

def create_session(model: str, user_id: str = "default") -> dict:
    db = get_client()
    result = db.table("sessions").insert({
        "model": model, "user_id": user_id, "weight": 1.0, "title": None,
    }).execute()
    return result.data[0]

def get_session(session_id: str) -> Optional[dict]:
    db     = get_client()
    result = db.table("sessions").select("*").eq("id", session_id).execute()
    return result.data[0] if result.data else None

# ── Hybrid session model (continuation window + gap-based rollover) ────────────
# A session CONTINUES if the user returns within CONTINUATION_WINDOW_HOURS
# (no fragmentation — coming back soon resumes the same session). After a longer
# gap, the previous session is considered ended and gets summarized, and a fresh
# session begins. This is what makes cross-session memory build correctly.
CONTINUATION_WINDOW_HOURS = 4

def get_latest_session(user_id: str = "default") -> Optional[dict]:
    """Most recent session for this user (by updated_at)."""
    db = get_client()
    result = (db.table("sessions").select("*")
              .eq("user_id", user_id)
              .order("updated_at", desc=True).limit(1).execute())
    return result.data[0] if result.data else None

def _hours_since(ts_str: str) -> float:
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0
    except Exception:
        return 1e9  # unparseable → treat as very old

def get_previous_unsummarized_session(user_id: str, exclude_id: str = "") -> Optional[dict]:
    """The user's most recent session that still needs summarizing (summary IS NULL)
    and has enough messages. Used to summarize the PREVIOUS session when a new one
    starts. Returns a real session row whose messages actually exist under its id."""
    db = get_client()
    result = (db.table("sessions").select("*")
              .eq("user_id", user_id).is_("summary", "null")
              .order("updated_at", desc=True).limit(5).execute())
    for s in (result.data or []):
        if s["id"] == exclude_id:
            continue
        # must have >=2 non-deleted messages to be worth summarizing
        msgs = (db.table("messages").select("id", count="exact")
                .eq("session_id", s["id"]).not_.is_("is_deleted", "true").execute())
        if (msgs.count or 0) >= 2:
            return s
    return None


def get_or_create_session(session_id: Optional[str], model: str,
                           user_id: str = "default") -> dict:
    if session_id:
        session = get_session(session_id)
        if session:
            db = get_client()
            db.table("sessions").update({
                "model": model, "updated_at": "now()",
            }).eq("id", session_id).execute()
            return session
    return create_session(model, user_id)

def update_session_title(session_id: str, title: str):
    db = get_client()
    db.table("sessions").update({"title": title}).eq("id", session_id).execute()

def update_session_weight(session_id: str):
    session = get_session(session_id)
    if not session:
        return
    from datetime import datetime, timezone
    created  = datetime.fromisoformat(session["created_at"].replace("Z", "+00:00"))
    age_days = (datetime.now(timezone.utc) - created).days
    if age_days <= 1:    weight = 1.0
    elif age_days <= 3:  weight = 0.8
    elif age_days <= 7:  weight = 0.6
    elif age_days <= 14: weight = 0.2
    else:                weight = 0.1
    db = get_client()
    db.table("sessions").update({"weight": weight}).eq("id", session_id).execute()

def get_all_sessions(user_id: str = "default") -> List[dict]:
    db = get_client()
    result = db.table("sessions").select("*").eq("user_id", user_id)\
               .order("updated_at", desc=True).execute()
    return result.data

def save_message(session_id: str, role: str, content: str, model: str,
                 pillar_core: str = "", pillar_emotion: str = "",
                 pillar_functional: str = "", pillar_modifiers: list = None,
                 pillar_score: float = 0.0, is_summary: bool = False,
                 pillar_vector: list = None,
                 embedding: list = None) -> dict:
    """Save message with full pillar data + embedding vector."""
    db = get_client()
    result = db.table("messages").insert({
        "session_id":        session_id,
        "role":              role,
        "content":           content,
        "model":             model,
        "pillar_core":       pillar_core,
        "pillar_emotion":    pillar_emotion,
        "pillar_functional": pillar_functional,
        "pillar_modifiers":  pillar_modifiers or [],
        "pillar_score":      pillar_score,
        "is_summary":        is_summary,
        "memory_tier":       "cache",
        "pillar_vector":     pillar_vector or [],
        "embedding":         embedding or [],
    }).execute()
    return result.data[0]

def get_session_messages(session_id: str, limit: int = 100) -> List[dict]:
    db = get_client()
    # Exclude soft-deleted messages. is_deleted may be null for legacy rows
    # (predating the column) — null means NOT deleted, so filter on `is not true`.
    result = db.table("messages").select("*").eq("session_id", session_id)\
               .not_.is_("is_deleted", "true")\
               .order("timestamp", desc=False).limit(limit).execute()
    return result.data

def get_recent_messages(session_id: str, n: int = 4) -> List[dict]:
    db = get_client()
    result = db.table("messages").select("*").eq("session_id", session_id)\
               .not_.is_("is_deleted", "true")\
               .order("timestamp", desc=True).limit(n).execute()
    return list(reversed(result.data))

def upsert_cache_slot(session_id: str, key: str, value: str,
                      strength: float, pillar: str, access_count: int = 1):
    db = get_client()
    db.table("cache_slots").upsert({
        "session_id": session_id, "key": key, "value": value,
        "strength": strength, "pillar": pillar,
        "access_count": access_count, "timestamp": "now()",
    }, on_conflict="session_id,key").execute()

def get_cache_slots(session_id: str) -> List[dict]:
    db = get_client()
    result = db.table("cache_slots").select("*").eq("session_id", session_id)\
               .order("strength", desc=True).execute()
    return result.data

def delete_cache_slot(session_id: str, key: str):
    db = get_client()
    db.table("cache_slots").delete().eq("session_id", session_id).eq("key", key).execute()

def save_stm_cluster(session_id: str, pillar: str, text: str,
                     strength: float = 1.0, pillar_tags: list = None,
                     embedding: list = None) -> dict:
    """Save STM cluster with optional embedding for similarity search."""
    db = get_client()
    data = {
        "session_id":   session_id,
        "pillar":       pillar,
        "text":         text,
        "strength":     strength,
        "recall_count": 0,
        "pillar_tags":  pillar_tags or [],
    }
    if embedding:
        data["embedding"] = embedding
    result = db.table("stm_clusters").insert(data).execute()
    return result.data[0]

def get_stm_clusters(session_id: str) -> List[dict]:
    db = get_client()
    result = db.table("stm_clusters").select("*").eq("session_id", session_id)\
               .order("strength", desc=True).execute()
    return result.data

def update_stm_recall(cluster_id: str, new_strength: float, recall_count: int):
    db = get_client()
    db.table("stm_clusters").update({
        "strength": new_strength, "recall_count": recall_count,
    }).eq("id", cluster_id).execute()

def promote_stm_to_ltm(cluster: dict, user_id: str = "default"):
    db = get_client()
    db.table("ltm_patterns").insert({
        "user_id":       user_id,
        "pattern_name":  cluster["pillar"],
        "text":          cluster["text"],
        "strength":      cluster["strength"],
        "recall_count":  cluster["recall_count"],
        "fused_pillars": cluster.get("pillar_tags", []),
        "overlap_score": 0.0,
        "embedding":     cluster.get("embedding", []),
    }).execute()
    db.table("stm_clusters").delete().eq("id", cluster["id"]).execute()

def save_ltm_pattern(user_id: str, text: str, pattern_name: str = "",
                     fused_pillars: list = None, overlap_score: float = 0.0,
                     embedding: list = None) -> dict:
    db = get_client()
    data = {
        "user_id": user_id, "pattern_name": pattern_name,
        "text": text, "strength": 1.0, "recall_count": 0,
        "fused_pillars": fused_pillars or [], "overlap_score": overlap_score,
    }
    if embedding:
        data["embedding"] = embedding
    result = db.table("ltm_patterns").insert(data).execute()
    return result.data[0]

def get_ltm_patterns(user_id: str = "default") -> List[dict]:
    db = get_client()
    result = db.table("ltm_patterns").select("*").eq("user_id", user_id)\
               .order("strength", desc=True).execute()
    return result.data

def update_ltm_recall(pattern_id: str, new_strength: float, recall_count: int):
    db = get_client()
    db.table("ltm_patterns").update({
        "strength": new_strength, "recall_count": recall_count,
    }).eq("id", pattern_id).execute()

def get_stats(user_id: str = "default") -> dict:
    db       = get_client()
    sessions  = get_all_sessions(user_id)
    msg_count = db.table("messages").select("id", count="exact").execute()
    stm_count = db.table("stm_clusters").select("id", count="exact").execute()
    ltm_count = db.table("ltm_patterns").select("id", count="exact").execute()
    return {
        "total_sessions": len(sessions),
        "total_messages": msg_count.count or 0,
        "total_stm":      stm_count.count or 0,
        "total_ltm":      ltm_count.count or 0,
        "sessions":       sessions[:10],
    }

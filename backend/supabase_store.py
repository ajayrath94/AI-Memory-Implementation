"""
SUPABASE STORE
Replaces in-memory chat_store.py with persistent Supabase storage.
All sessions, messages, cache slots, STM clusters, LTM patterns stored in DB.
"""

import os
import time
from typing import Optional, List, Dict
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ── Client ─────────────────────────────────────────────────────────────────────

def get_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(url, key)

# ── Sessions ───────────────────────────────────────────────────────────────────

def create_session(model: str, user_id: str = "default") -> dict:
    db = get_client()
    result = db.table("sessions").insert({
        "model":    model,
        "user_id":  user_id,
        "weight":   1.0,
        "title":    None,
    }).execute()
    return result.data[0]


def get_session(session_id: str) -> Optional[dict]:
    db = get_client()
    result = db.table("sessions").select("*").eq("id", session_id).execute()
    return result.data[0] if result.data else None


def get_or_create_session(session_id: Optional[str], model: str, user_id: str = "default") -> dict:
    if session_id:
        session = get_session(session_id)
        if session:
            # Update model and timestamp
            db = get_client()
            db.table("sessions").update({
                "model":      model,
                "updated_at": "now()",
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
    created = datetime.fromisoformat(session["created_at"].replace("Z", "+00:00"))
    age_days = (datetime.now(timezone.utc) - created).days

    if age_days <= 1:   weight = 1.0
    elif age_days <= 3:  weight = 0.8
    elif age_days <= 7:  weight = 0.6
    elif age_days <= 14: weight = 0.2
    else:                weight = 0.1

    db = get_client()
    db.table("sessions").update({"weight": weight}).eq("id", session_id).execute()


def get_all_sessions(user_id: str = "default") -> List[dict]:
    db = get_client()
    result = db.table("sessions").select("*").eq("user_id", user_id).order("updated_at", desc=True).execute()
    return result.data


# ── Messages ───────────────────────────────────────────────────────────────────

def save_message(session_id: str, role: str, content: str, model: str,
                 pillar_core: str = "", pillar_emotion: str = "",
                 pillar_functional: str = "", pillar_modifiers: list = None,
                 pillar_score: float = 0.0, is_summary: bool = False) -> dict:
    db = get_client()
    result = db.table("messages").insert({
        "session_id":         session_id,
        "role":               role,
        "content":            content,
        "model":              model,
        "pillar_core":        pillar_core,
        "pillar_emotion":     pillar_emotion,
        "pillar_functional":  pillar_functional,
        "pillar_modifiers":   pillar_modifiers or [],
        "pillar_score":       pillar_score,
        "is_summary":         is_summary,
        "memory_tier":        "cache",
    }).execute()
    return result.data[0]


def get_session_messages(session_id: str, limit: int = 100) -> List[dict]:
    db = get_client()
    result = db.table("messages").select("*").eq("session_id", session_id)\
               .order("timestamp", desc=False).limit(limit).execute()
    return result.data


def get_recent_messages(session_id: str, n: int = 4) -> List[dict]:
    db = get_client()
    result = db.table("messages").select("*").eq("session_id", session_id)\
               .order("timestamp", desc=True).limit(n).execute()
    return list(reversed(result.data))


# ── Cache slots ────────────────────────────────────────────────────────────────

def upsert_cache_slot(session_id: str, key: str, value: str,
                      strength: float, pillar: str, access_count: int = 1):
    db = get_client()
    db.table("cache_slots").upsert({
        "session_id":   session_id,
        "key":          key,
        "value":        value,
        "strength":     strength,
        "pillar":       pillar,
        "access_count": access_count,
        "timestamp":    "now()",
    }, on_conflict="session_id,key").execute()


def get_cache_slots(session_id: str) -> List[dict]:
    db = get_client()
    result = db.table("cache_slots").select("*").eq("session_id", session_id)\
               .order("strength", desc=True).execute()
    return result.data


def delete_cache_slot(session_id: str, key: str):
    db = get_client()
    db.table("cache_slots").delete().eq("session_id", session_id).eq("key", key).execute()


# ── STM clusters ───────────────────────────────────────────────────────────────

def save_stm_cluster(session_id: str, pillar: str, text: str,
                     strength: float = 1.0, pillar_tags: list = None) -> dict:
    db = get_client()
    result = db.table("stm_clusters").insert({
        "session_id":  session_id,
        "pillar":      pillar,
        "text":        text,
        "strength":    strength,
        "recall_count": 0,
        "pillar_tags": pillar_tags or [],
    }).execute()
    return result.data[0]


def get_stm_clusters(session_id: str) -> List[dict]:
    db = get_client()
    result = db.table("stm_clusters").select("*").eq("session_id", session_id)\
               .order("strength", desc=True).execute()
    return result.data


def update_stm_recall(cluster_id: str, new_strength: float, recall_count: int):
    db = get_client()
    db.table("stm_clusters").update({
        "strength":     new_strength,
        "recall_count": recall_count,
    }).eq("id", cluster_id).execute()


def promote_stm_to_ltm(cluster: dict, user_id: str = "default"):
    """Move a cluster from STM to LTM."""
    db = get_client()
    db.table("ltm_patterns").insert({
        "user_id":       user_id,
        "pattern_name":  cluster["pillar"],
        "text":          cluster["text"],
        "strength":      cluster["strength"],
        "recall_count":  cluster["recall_count"],
        "fused_pillars": cluster.get("pillar_tags", []),
        "overlap_score": 0.0,
    }).execute()
    # Remove from STM
    db.table("stm_clusters").delete().eq("id", cluster["id"]).execute()


# ── LTM patterns ───────────────────────────────────────────────────────────────

def save_ltm_pattern(user_id: str, text: str, pattern_name: str = "",
                     fused_pillars: list = None, overlap_score: float = 0.0) -> dict:
    db = get_client()
    result = db.table("ltm_patterns").insert({
        "user_id":       user_id,
        "pattern_name":  pattern_name,
        "text":          text,
        "strength":      1.0,
        "recall_count":  0,
        "fused_pillars": fused_pillars or [],
        "overlap_score": overlap_score,
    }).execute()
    return result.data[0]


def get_ltm_patterns(user_id: str = "default") -> List[dict]:
    db = get_client()
    result = db.table("ltm_patterns").select("*").eq("user_id", user_id)\
               .order("strength", desc=True).execute()
    return result.data


def update_ltm_recall(pattern_id: str, new_strength: float, recall_count: int):
    db = get_client()
    db.table("ltm_patterns").update({
        "strength":     new_strength,
        "recall_count": recall_count,
    }).eq("id", pattern_id).execute()


# ── Stats ──────────────────────────────────────────────────────────────────────

def get_stats(user_id: str = "default") -> dict:
    db     = get_client()
    sessions = get_all_sessions(user_id)
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

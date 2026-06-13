"""
USER MEMORY STORE
Manages the user_memory table in Supabase.
This is the cross-session persistent memory for each user.

On session end:
  1. Summarize session
  2. Recursively update user_memory
  3. Extract key facts

On session start:
  1. Load user_memory
  2. Inject into system prompt
  3. Seed Cache with key facts
"""

import time
from typing import Optional, List
from supabase_store import get_client, get_session_messages, save_stm_cluster
from memory.summarizer import (
    summarize_session,
    recursive_summarize,
    extract_key_facts,
    extract_dominant_pillars,
)


# ── Get user memory ────────────────────────────────────────────────────────────

def get_user_memory(user_id: str = "default") -> Optional[dict]:
    """Get the current memory profile for a user."""
    db = get_client()
    result = db.table("user_memory").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None


def get_user_memory_summary(user_id: str = "default") -> Optional[str]:
    """Get just the summary text."""
    memory = get_user_memory(user_id)
    return memory["summary"] if memory else None


# ── Save/update user memory ────────────────────────────────────────────────────

def save_user_memory(user_id: str, summary: str,
                     key_facts: List[str] = None,
                     dominant_pillars: List[str] = None,
                     session_count: int = 1):
    """Save or update the user memory profile."""
    db = get_client()
    data = {
        "user_id":          user_id,
        "summary":          summary,
        "key_facts":        key_facts or [],
        "dominant_pillars": dominant_pillars or [],
        "session_count":    session_count,
        "updated_at":       "now()",
    }
    db.table("user_memory").upsert(data, on_conflict="user_id").execute()


# ── On session end ─────────────────────────────────────────────────────────────

def process_session_end(session_id: str, user_id: str = "default"):
    """
    Called when a session ends (or when starting a new one).
    1. Summarize the session
    2. Recursively update user memory
    3. Store in Supabase
    """
    print(f"[UserMemory] Processing session end: {session_id}")

    # 1. Get all messages from this session
    messages = get_session_messages(session_id)
    if not messages or len(messages) < 2:
        print("[UserMemory] Not enough messages to summarize")
        return

    # 2. Summarize this session
    session_summary = summarize_session(messages)
    if not session_summary:
        return

    print(f"[UserMemory] Session summary: {session_summary[:100]}...")

    # 3. Save session summary
    db = get_client()
    db.table("sessions").update({
        "summary": session_summary,
        "summary_generated_at": "now()",
    }).eq("id", session_id).execute()

    # 4. Get existing user memory
    existing = get_user_memory(user_id)
    existing_summary  = existing["summary"]       if existing else None
    existing_count    = existing["session_count"] if existing else 0
    new_count         = existing_count + 1

    # 5. Recursive summarization
    new_summary = recursive_summarize(
        existing_memory=existing_summary,
        new_session_summary=session_summary,
        session_count=new_count,
    )

    # 6. Extract key facts + dominant pillars
    key_facts        = extract_key_facts(new_summary)
    dominant_pillars = extract_dominant_pillars(messages)

    # 7. Save updated memory
    save_user_memory(
        user_id=user_id,
        summary=new_summary,
        key_facts=key_facts,
        dominant_pillars=dominant_pillars,
        session_count=new_count,
    )

    # 8. Also store in STM for immediate recall
    if new_summary:
        save_stm_cluster(
            session_id=session_id,
            pillar="USER_MEMORY",
            text=f"[USER PROFILE] {new_summary}",
            strength=1.0,
            pillar_tags=dominant_pillars,
        )

    print(f"[UserMemory] Updated memory for {user_id} (session {new_count})")
    print(f"[UserMemory] Key facts: {key_facts}")


# ── On session start ───────────────────────────────────────────────────────────

def build_memory_prompt(user_id: str = "default") -> Optional[str]:
    """
    Build the memory context to inject at session start.
    Returns formatted string for system prompt injection.
    """
    memory = get_user_memory(user_id)
    if not memory or not memory.get("summary"):
        return None

    parts = []

    # Main summary
    parts.append(f"What I know about this person:\n{memory['summary']}")

    # Key facts as bullets
    if memory.get("key_facts"):
        facts = "\n".join(f"• {f}" for f in memory["key_facts"])
        parts.append(f"\nKey facts:\n{facts}")

    # Session count
    count = memory.get("session_count", 0)
    if count > 1:
        parts.append(f"\nThis is conversation #{count + 1} with this person.")

    return "\n".join(parts)


def seed_cache_from_memory(user_id: str = "default",
                           session_id: str = ""):
    """
    Seed the in-memory cache with user's key facts at session start.
    This gives the Cache layer a head start with known information.
    """
    from memory.cache.cache_memory import _update_slot

    memory = get_user_memory(user_id)
    if not memory:
        return

    # Seed each key fact as a cache slot
    for i, fact in enumerate(memory.get("key_facts", [])[:5]):
        _update_slot(
            key=f"user_fact_{i}",
            value=fact,
            pillar="USER_IDENTITY",
            session_id=session_id,
            model="",
        )

    # Seed dominant pillars
    for pillar in memory.get("dominant_pillars", [])[:3]:
        _update_slot(
            key=f"dominant_{pillar}",
            value=pillar,
            pillar="USER_PATTERN",
            session_id=session_id,
            model="",
        )

    print(f"[UserMemory] Cache seeded with {len(memory.get('key_facts', []))} facts")

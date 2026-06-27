"""
USER MEMORY STORE v2
Cross-session persistent memory with:
  - Pillar vector storage per session
  - Session centroid computation
  - Trend detection via cosine similarity
  - Behavioural fingerprint
  - Dominant pillars from ALL sessions
"""

import time
import json
from collections import Counter
from typing import Optional, List, Dict
from supabase_store import (
    get_client, get_session_messages,
    save_stm_cluster, get_all_sessions
)
from memory.summarizer import (
    summarize_session, recursive_summarize,
    extract_key_facts,
)
from classifier.pillar_classifier import (
    cosine_similarity, compute_centroid, DIMENSION_ORDER
)


# ── Get user memory ────────────────────────────────────────────────────────────

def get_user_memory(user_id: str = "default") -> Optional[dict]:
    db     = get_client()
    result = db.table("user_memory").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None


def get_user_memory_summary(user_id: str = "default") -> Optional[str]:
    memory = get_user_memory(user_id)
    return memory["summary"] if memory else None


# ── Save user memory ───────────────────────────────────────────────────────────

def save_user_memory(user_id: str, summary: str,
                     key_facts: List[str] = None,
                     dominant_pillars: List[str] = None,
                     session_count: int = 1,
                     pillar_trend: dict = None,
                     behavioural_fingerprint: dict = None,
                     session_centroids: dict = None):
    db   = get_client()
    data = {
        "user_id":                  user_id,
        "summary":                  summary,
        "key_facts":                key_facts or [],
        "dominant_pillars":         dominant_pillars or [],
        "session_count":            session_count,
        "pillar_trend":             pillar_trend or {},
        "behavioural_fingerprint":  behavioural_fingerprint or {},
        "session_centroids":        session_centroids or {},
        "updated_at":               "now()",
    }
    db.table("user_memory").upsert(data, on_conflict="user_id").execute()


# ── Extract dominant pillars from ALL sessions ─────────────────────────────────

def extract_all_dominant_pillars(user_id: str = "default") -> List[str]:
    try:
        all_sessions = get_all_sessions(user_id)
        all_pillars  = []
        for session in all_sessions:
            messages = get_session_messages(session["id"])
            for msg in messages:
                for field in ["pillar_core", "pillar_emotion", "pillar_functional"]:
                    val = msg.get(field, "")
                    if val and val not in ("GENERAL", "NEUTRAL", "CHAT", "", None):
                        all_pillars.append(val)
        if not all_pillars:
            return []
        return [p for p, _ in Counter(all_pillars).most_common(5)]
    except Exception as e:
        print(f"[UserMemory] Failed to extract pillars: {e}")
        return []


# ── Compute session centroid ───────────────────────────────────────────────────

def compute_session_centroid(session_id: str) -> List[float]:
    """Average pillar vectors of all messages in a session."""
    messages = get_session_messages(session_id)
    vectors  = []
    for msg in messages:
        vec = msg.get("pillar_vector", [])
        if vec and len(vec) == len(DIMENSION_ORDER):
            vectors.append(vec)
    return compute_centroid(vectors) if vectors else [0.0] * len(DIMENSION_ORDER)


# ── Trend detection ────────────────────────────────────────────────────────────

def detect_trends(session_centroids: Dict[str, List[float]]) -> dict:
    """
    Detect behavioural trends across session centroids.
    Uses cosine similarity between consecutive sessions.
    """
    if len(session_centroids) < 2:
        return {}

    session_ids = list(session_centroids.keys())
    centroids   = list(session_centroids.values())

    # Compute cosine similarity between consecutive sessions
    similarities = []
    for i in range(len(centroids) - 1):
        sim = cosine_similarity(centroids[i], centroids[i+1])
        similarities.append(sim)

    # Find dominant pillar per session
    session_dominant = []
    for centroid in centroids:
        if any(centroid):
            max_idx = centroid.index(max(centroid))
            session_dominant.append(DIMENSION_ORDER[max_idx])
        else:
            session_dominant.append("GENERAL")

    # Detect cycles (repeating patterns)
    cycle_detected = False
    cycle_length   = 0
    if len(session_dominant) >= 4:
        for length in range(2, len(session_dominant) // 2 + 1):
            pattern = session_dominant[:length]
            repeat  = session_dominant[length:length*2]
            if pattern == repeat:
                cycle_detected = True
                cycle_length   = length
                break

    # Compute pillar trends (increasing/decreasing/stable)
    pillar_trends = {}
    if len(centroids) >= 3:
        for i, dim in enumerate(DIMENSION_ORDER):
            values = [c[i] for c in centroids[-5:]]  # last 5 sessions
            if len(values) >= 2:
                delta = values[-1] - values[0]
                if delta > 0.1:
                    pillar_trends[dim] = "increasing"
                elif delta < -0.1:
                    pillar_trends[dim] = "decreasing"
                else:
                    pillar_trends[dim] = "stable"

    # Detect alerts
    alerts = []
    health_idx   = DIMENSION_ORDER.index("HEALTH_WELLNESS")
    stress_idx   = DIMENSION_ORDER.index("STRESS")
    health_trend = pillar_trends.get("HEALTH_WELLNESS", "stable")
    stress_trend = pillar_trends.get("STRESS", "stable")

    if health_trend == "increasing":
        alerts.append("Health topics increasing across recent sessions")
    if stress_trend == "increasing":
        alerts.append("Stress indicators rising across recent sessions")

    # Check if stress appeared 3 sessions in a row
    if len(session_dominant) >= 3:
        last3 = session_dominant[-3:]
        if all("STRESS" in d or "HEALTH" in d for d in last3):
            alerts.append("Health/Stress topics in last 3 consecutive sessions")

    avg_sim = sum(similarities) / len(similarities) if similarities else 0

    return {
        "avg_session_similarity":  round(avg_sim, 3),
        "consecutive_similarities": [round(s, 3) for s in similarities],
        "session_dominant_pillars": session_dominant,
        "cycle_detected":           cycle_detected,
        "cycle_length":             cycle_length,
        "pillar_trends":            pillar_trends,
        "alerts":                   alerts,
    }


# ── Behavioural fingerprint ────────────────────────────────────────────────────

def build_fingerprint(trend: dict, dominant_pillars: List[str],
                      session_count: int) -> dict:
    """Build a behavioural fingerprint from trend data."""
    if not trend:
        return {}

    # Find top increasing pillars
    increasing = [p for p, t in trend.get("pillar_trends", {}).items()
                  if t == "increasing" and p not in ("GENERAL", "NEUTRAL", "CHAT")]

    # Find top decreasing pillars
    decreasing = [p for p, t in trend.get("pillar_trends", {}).items()
                  if t == "decreasing" and p not in ("GENERAL", "NEUTRAL", "CHAT")]

    # Dominant pattern
    dominant_pattern = " + ".join(dominant_pillars[:2]) if dominant_pillars else "GENERAL"

    return {
        "dominant_pattern":     dominant_pattern,
        "emerging_interests":   increasing[:3],
        "fading_interests":     decreasing[:3],
        "cycle_detected":       trend.get("cycle_detected", False),
        "cycle_length":         trend.get("cycle_length", 0),
        "session_consistency":  trend.get("avg_session_similarity", 0),
        "alerts":               trend.get("alerts", []),
        "sessions_analyzed":    session_count,
    }


# ── On session end ─────────────────────────────────────────────────────────────

def process_session_end(session_id: str, user_id: str = "default"):
    """
    Called when a session ends:
    1. Summarize session
    2. Compute session centroid
    3. Detect trends
    4. Build fingerprint
    5. Recursive memory update
    """
    print(f"[UserMemory] Processing session end: {session_id}")

    messages = get_session_messages(session_id)
    if not messages or len(messages) < 2:
        print("[UserMemory] Not enough messages to summarize")
        return

    # 1. Summarize session
    session_summary = summarize_session(messages)
    if not session_summary:
        return

    # 2. Compute session centroid from pillar vectors
    centroid = compute_session_centroid(session_id)

    # 3. Save session summary + centroid
    db = get_client()
    db.table("sessions").update({
        "summary":                session_summary,
        "summary_generated_at":   "now()",
        "pillar_centroid":        centroid,
    }).eq("id", session_id).execute()

    # 4. Get existing user memory
    existing         = get_user_memory(user_id)
    existing_summary = existing["summary"]       if existing else None
    existing_count   = existing["session_count"] if existing else 0
    new_count        = existing_count + 1

    # 5. Load existing session centroids and add new one
    existing_centroids = {}
    if existing and existing.get("session_centroids"):
        try:
            existing_centroids = existing["session_centroids"]
            if isinstance(existing_centroids, str):
                existing_centroids = json.loads(existing_centroids)
        except Exception:
            existing_centroids = {}
    existing_centroids[session_id] = centroid

    # 6. Detect trends across all sessions
    trend = detect_trends(existing_centroids)

    # 7. Extract dominant pillars from ALL messages
    dominant_pillars = extract_all_dominant_pillars(user_id)

    # 8. Build behavioural fingerprint
    fingerprint = build_fingerprint(trend, dominant_pillars, new_count)

    # 9. Recursive summarization
    new_summary = recursive_summarize(
        existing_memory=existing_summary,
        new_session_summary=session_summary,
        session_count=new_count,
    )

    # 10. Extract key facts
    key_facts = extract_key_facts(new_summary)

    # 11. Save everything
    save_user_memory(
        user_id=user_id,
        summary=new_summary,
        key_facts=key_facts,
        dominant_pillars=dominant_pillars,
        session_count=new_count,
        pillar_trend=trend,
        behavioural_fingerprint=fingerprint,
        session_centroids=existing_centroids,
    )

    # 12. Store in STM
    if new_summary:
        save_stm_cluster(
            session_id=session_id,
            pillar="USER_MEMORY",
            text=f"[USER PROFILE] {new_summary}",
            strength=1.0,
            pillar_tags=dominant_pillars,
        )

    print(f"[UserMemory] Updated for {user_id} — session {new_count}")
    print(f"[UserMemory] Pillars: {dominant_pillars}")
    print(f"[UserMemory] Alerts: {fingerprint.get('alerts', [])}")


# ── On session start ───────────────────────────────────────────────────────────

def build_memory_prompt(user_id: str = "default") -> Optional[str]:
    memory = get_user_memory(user_id)
    if not memory or not memory.get("summary"):
        return None

    parts = [f"What I know about this person:\n{memory['summary']}"]

    if memory.get("key_facts"):
        facts = "\n".join(f"• {f}" for f in memory["key_facts"])
        parts.append(f"\nKey facts:\n{facts}")

    # Include alerts in memory prompt
    fingerprint = memory.get("behavioural_fingerprint") or {}
    if isinstance(fingerprint, str):
        try:
            fingerprint = json.loads(fingerprint)
        except Exception:
            fingerprint = {}

    alerts = fingerprint.get("alerts", [])
    if alerts:
        alert_text = "\n".join(f"⚠️ {a}" for a in alerts)
        parts.append(f"\nBehavioural alerts:\n{alert_text}")

    count = memory.get("session_count", 0)
    if count > 0:
        parts.append(f"\nThis is conversation #{count + 1} with this person.")

    return "\n".join(parts)


def seed_cache_from_memory(user_id: str = "default", session_id: str = ""):
    from memory.cache.cache_memory import _update_slot
    memory = get_user_memory(user_id)
    if not memory:
        return
    for i, fact in enumerate(memory.get("key_facts", [])[:5]):
        _update_slot(key=f"user_fact_{i}", value=fact,
                     pillar="USER_IDENTITY", session_id=session_id, model="")
    for pillar in memory.get("dominant_pillars", [])[:3]:
        _update_slot(key=f"dominant_{pillar}", value=pillar,
                     pillar="USER_PATTERN", session_id=session_id, model="")
    print(f"[UserMemory] Cache seeded with {len(memory.get('key_facts', []))} facts")

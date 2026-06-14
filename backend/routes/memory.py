from fastapi import APIRouter
from memory.cache.cache_memory import get_active_slots
from memory.decay.decay_memory import system_entropy
from store.pillar_vector_store import get_dominant_pillars, get_correlations
from supabase_store import get_stats, get_stm_clusters, get_ltm_patterns, get_all_sessions
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
def sessions():
    return get_stats()

@router.get("/sessions/list")
def sessions_list():
    return {"sessions": get_all_sessions()}

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

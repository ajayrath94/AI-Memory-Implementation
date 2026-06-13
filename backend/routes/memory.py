from fastapi import APIRouter
from memory.cache.cache_memory import get_active_slots
from memory.decay.decay_memory import system_entropy
from store.pillar_vector_store import get_dominant_pillars, get_correlations
from supabase_store import get_stats, get_stm_clusters, get_ltm_patterns, get_all_sessions

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

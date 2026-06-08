from fastapi import APIRouter
from memory.cache.cache_memory import get_active_slots, get_voided_archive
from memory.recall.recall_memory import get_stm, get_ltm
from memory.decay.decay_memory import system_entropy
from store.pillar_vector_store import get_dominant_pillars, get_correlations
from utils.chat_store import get_stats

router = APIRouter()

@router.get("/cache")
def cache_state():
    return {"slots": get_active_slots(), "voided": get_voided_archive()}

@router.get("/stm")
def stm_state():
    return {"entries": get_stm(), "count": len(get_stm())}

@router.get("/ltm")
def ltm_state():
    return {"entries": get_ltm(), "count": len(get_ltm())}

@router.get("/entropy")
def entropy():
    return system_entropy()

@router.get("/pillars")
def pillars():
    return {"dominant": get_dominant_pillars(), "correlations": get_correlations()}

@router.get("/sessions")
def sessions():
    return get_stats()

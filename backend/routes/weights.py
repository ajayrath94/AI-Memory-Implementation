"""
PILLAR WEIGHTS ROUTES
API for users/caregivers to customize Nancy's attention.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Optional

router = APIRouter()


class WeightUpdate(BaseModel):
    weights: Dict[str, float]  # e.g. {"HEALTH_WELLNESS": 1.8, "ENTERTAINMENT": 0.3}


class SingleWeight(BaseModel):
    pillar: str
    weight: float


@router.get("/{user_id}")
def get_weights(user_id: str):
    """Get all pillar weights for a user (includes defaults)."""
    from memory.pillar_weights import get_pillar_weights, DEFAULT_WEIGHTS
    current  = get_pillar_weights(user_id)
    modified = {p: w for p, w in current.items() if abs(w - 1.0) > 0.05}
    return {
        "user_id":   user_id,
        "weights":   current,
        "modified":  modified,
        "defaults":  DEFAULT_WEIGHTS,
    }


@router.post("/{user_id}")
def update_weights(user_id: str, req: WeightUpdate):
    """Set multiple pillar weights at once."""
    from memory.pillar_weights import set_pillar_weights_bulk
    results = set_pillar_weights_bulk(user_id, req.weights)
    return {"status": "ok", "results": results}


@router.put("/{user_id}/{pillar}")
def set_single_weight(user_id: str, pillar: str, weight: float):
    """Set a single pillar weight."""
    from memory.pillar_weights import set_pillar_weight
    ok = set_pillar_weight(user_id, pillar.upper(), weight)
    return {"status": "ok" if ok else "error", "pillar": pillar, "weight": weight}


@router.delete("/{user_id}")
def reset_weights(user_id: str):
    """Reset all weights to default (1.0)."""
    from memory.pillar_weights import reset_pillar_weights
    ok = reset_pillar_weights(user_id)
    return {"status": "ok" if ok else "error", "message": "All weights reset to 1.0"}


@router.get("/{user_id}/history")
def get_weight_history(user_id: str, limit: int = 50):
    """Get full weight change history for a user."""
    try:
        from supabase_store import get_client
        db     = get_client()
        result = db.table("pillar_weight_history")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("changed_at", desc=True)\
            .limit(limit)\
            .execute()
        return {"history": result.data or []}
    except Exception as e:
        return {"history": [], "error": str(e)}


@router.put("/{user_id}/{pillar}")
def set_single_weight_with_reason(
    user_id: str, pillar: str, weight: float,
    changed_by: str = "user", reason: str = ""
):
    """Set a single pillar weight with audit trail."""
    from memory.pillar_weights import set_pillar_weight
    ok = set_pillar_weight(user_id, pillar.upper(), weight, changed_by, reason)
    return {"status": "ok" if ok else "error", "pillar": pillar, "weight": weight}

"""Alert routes — check, list, and mark alerts."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

@router.post("/check/{user_id}")
def check_alerts(user_id: str):
    """Manually trigger alert check for a user."""
    from memory.alert_engine import run_alert_engine
    return run_alert_engine(user_id)

@router.get("/user/{user_id}")
def get_alerts(user_id: str, limit: int = 20, unread_only: bool = False):
    """Get all alerts for a user."""
    try:
        from supabase_store import get_client
        db = get_client()
        q  = db.table("care_alerts")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("sent_at", desc=True)\
            .limit(limit)
        if unread_only:
            q = q.is_("read_at", "null")
        return {"alerts": q.execute().data or []}
    except Exception as e:
        return {"alerts": [], "error": str(e)}

@router.get("/caregiver/{caregiver_id}")
def get_caregiver_alerts(caregiver_id: str, limit: int = 50):
    """Get all alerts for a caregiver across all their users."""
    try:
        from supabase_store import get_client
        db     = get_client()
        result = db.table("care_alerts")\
            .select("*")\
            .eq("caregiver_id", caregiver_id)\
            .order("sent_at", desc=True)\
            .limit(limit)\
            .execute()
        return {"alerts": result.data or []}
    except Exception as e:
        return {"alerts": [], "error": str(e)}

@router.post("/read/{alert_id}")
def mark_read(alert_id: str):
    """Mark an alert as read."""
    try:
        from supabase_store import get_client
        from datetime import datetime, timezone
        db = get_client()
        db.table("care_alerts").update({
            "read_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", alert_id).execute()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/detected/{user_id}")
def detect_only(user_id: str):
    """Detect alerts without sending — for dashboard preview."""
    from memory.alert_engine import detect_alerts
    alerts = detect_alerts(user_id)
    return {"alerts": alerts, "count": len(alerts)}

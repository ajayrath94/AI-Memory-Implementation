"""
SCHEDULE ROUTES
Endpoints for proactive messaging and schedule management.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class ProactiveRequest(BaseModel):
    user_id:          str
    last_seen_hours:  float = 0.0
    opened_app:       bool  = True
    hour:             Optional[int] = None
    force_slot:       Optional[str] = None


class ScheduleConfig(BaseModel):
    user_id:           str
    morning_call:      bool = True
    evening_call:      bool = True
    night_reminder:    bool = True
    medicine_reminder: bool = True
    morning_hour:      int  = 7
    evening_hour:      int  = 18
    night_hour:        int  = 21


@router.post("/proactive")
def get_proactive_message(req: ProactiveRequest):
    """
    Get Nancy's proactive opening message based on
    time, profile, memory and last seen time.
    """
    from memory.schedule_engine import (
        generate_proactive_script, should_nancy_open
    )

    opens = should_nancy_open(
        req.user_id,
        req.last_seen_hours,
        req.opened_app,
    )

    if not opens:
        return {"should_open": False, "script": "", "priority": "low"}

    result = generate_proactive_script(
        req.user_id,
        hour       = req.hour,
        force_slot = req.force_slot,
    )
    result["should_open"] = True
    return result


@router.get("/proactive/{user_id}")
def check_proactive(user_id: str, last_seen_hours: float = 8.0, hour: int = None):
    """Quick GET to check if Nancy should open proactively."""
    from memory.schedule_engine import generate_proactive_script, should_nancy_open

    opens = should_nancy_open(user_id, last_seen_hours)
    if not opens:
        return {"should_open": False}

    result = generate_proactive_script(user_id, hour=hour)
    result["should_open"] = True
    return result


@router.get("/slots")
def get_time_slots():
    """Return the schedule slot definitions."""
    return {
        "slots": {
            "morning":   {"start": 6,  "end": 10, "focus": "medicine + breakfast"},
            "midday":    {"start": 10, "end": 14, "focus": "activity + interests"},
            "afternoon": {"start": 14, "end": 17, "focus": "rest + conversation"},
            "evening":   {"start": 17, "end": 20, "focus": "cricket/music/news"},
            "night":     {"start": 20, "end": 23, "focus": "medicine + check-in"},
            "late_night":{"start": 23, "end": 6,  "focus": "emergency only"},
        }
    }

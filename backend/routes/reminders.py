"""
REMINDERS — the user-facing reminder tab.

GET  /reminders/{user_id}          list upcoming + past reminders
POST /reminders/{user_id}          create a reminder directly (manual add)
POST /reminders/{reminder_id}/cancel   cancel a pending reminder
POST /reminders/{reminder_id}/update   change the time / text (correction loop)
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

router = APIRouter()


def _fmt_local(iso_utc: str, tz_name: str) -> str:
    """Render a UTC timestamp in the user's local tz for display."""
    if not iso_utc:
        return ""
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        tz = ZoneInfo(tz_name)
        return dt.astimezone(tz).strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return iso_utc


@router.get("/{user_id}")
def list_reminders(user_id: str):
    """All reminders for the tab: upcoming (pending, soonest first) + recent past."""
    from supabase_store import get_client
    from memory.time_context import get_user_timezone
    db = get_client()
    tz_name = get_user_timezone(user_id)
    rows = (db.table("reminders").select("*")
            .eq("user_id", user_id).order("fire_at", desc=False).execute()).data or []

    now = datetime.now(timezone.utc)
    upcoming, past = [], []
    for r in rows:
        try:
            fire = datetime.fromisoformat(r["fire_at"].replace("Z", "+00:00"))
        except Exception:
            fire = None
        item = {
            "id": r["id"],
            "what": r.get("what"),
            "fire_at_local": _fmt_local(r.get("fire_at"), tz_name),
            "fire_at_utc": r.get("fire_at"),
            "status": r.get("status"),
            "source": r.get("source"),
        }
        if r.get("status") == "pending" and fire and fire > now:
            upcoming.append(item)
        else:
            past.append(item)
    past.reverse()  # most recent past first
    return {"upcoming": upcoming, "past": past,
            "counts": {"upcoming": len(upcoming), "past": len(past)}}


class CreateReminder(BaseModel):
    what: str
    fire_at_utc: str            # ISO UTC timestamp
    source: Optional[str] = "user"


@router.post("/{user_id}")
def create_reminder(user_id: str, req: CreateReminder):
    """Manual add from the tab (e.g. a '+' button)."""
    from supabase_store import get_client
    db = get_client()
    row = {"user_id": user_id, "what": req.what, "fire_at": req.fire_at_utc,
           "status": "pending", "source": req.source or "user"}
    res = db.table("reminders").insert(row).execute()
    return (res.data or [{}])[0]


@router.post("/{reminder_id}/cancel")
def cancel_reminder(reminder_id: str):
    """Cancel a pending reminder from the tab."""
    from supabase_store import get_client
    db = get_client()
    db.table("reminders").update({"status": "cancelled"}).eq("id", reminder_id).execute()
    return {"id": reminder_id, "status": "cancelled"}


class UpdateReminder(BaseModel):
    what: Optional[str] = None
    fire_at_utc: Optional[str] = None


@router.post("/{reminder_id}/update")
def update_reminder(reminder_id: str, req: UpdateReminder):
    """Correction loop: change the time or text of a pending reminder."""
    from supabase_store import get_client
    db = get_client()
    upd = {}
    if req.what is not None:
        upd["what"] = req.what
    if req.fire_at_utc is not None:
        upd["fire_at"] = req.fire_at_utc
        upd["status"] = "pending"   # re-arm if it was changed
    if not upd:
        return {"id": reminder_id, "updated": False}
    db.table("reminders").update(upd).eq("id", reminder_id).execute()
    return {"id": reminder_id, "updated": True, **upd}

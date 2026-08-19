"""
CALENDAR — a unified event timeline Nancy owns (no external calendar sync).
Merges three sources into one view:
  calendar_events — general dated events (appointments, festivals, visits)
  reminders       — dated firing reminders (their event_at/fire_at)
  care_schedule   — recurring caregiver-set routines (meds), projected onto the range
Elder adds via chat; caregiver adds via dashboard. reminder_enabled events can
spawn a reminder via the existing engine.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta

router = APIRouter()


def _db():
    from supabase_store import get_client
    return get_client()


class CalendarEvent(BaseModel):
    user_id:          str
    title:            str
    event_at:         str                 # ISO timestamp
    end_at:           Optional[str] = None
    category:         str = "personal"
    notes:            Optional[str] = None
    location:         Optional[str] = None
    recurring:        Optional[str] = None
    created_by:       Optional[str] = None
    reminder_enabled: bool = True


class CalendarUpdate(BaseModel):
    title:            Optional[str] = None
    event_at:         Optional[str] = None
    end_at:           Optional[str] = None
    category:         Optional[str] = None
    notes:            Optional[str] = None
    location:         Optional[str] = None
    recurring:        Optional[str] = None
    reminder_enabled: Optional[bool] = None


@router.get("/{user_id}")
def get_calendar(user_id: str, days: int = 7, start: str = None):
    """Unified timeline: calendar_events + dated reminders + projected recurring
    care_schedule, over [start, start+days]. One view of everything."""
    db = _db()
    now = datetime.now(timezone.utc)
    frm = datetime.fromisoformat(start) if start else now
    to  = frm + timedelta(days=days)
    frm_iso, to_iso = frm.isoformat(), to.isoformat()

    items = []

    # 1. calendar_events in range
    try:
        evs = (db.table("calendar_events").select("*")
               .eq("user_id", user_id)
               .gte("event_at", frm_iso).lte("event_at", to_iso)
               .order("event_at").execute().data or [])
        for e in evs:
            items.append({
                "kind": "event", "id": e["id"], "title": e.get("title"),
                "at": e.get("event_at"), "end_at": e.get("end_at"),
                "category": e.get("category"), "notes": e.get("notes"),
                "location": e.get("location"), "created_by": e.get("created_by"),
            })
    except Exception as e:
        print(f"[Calendar] events query failed: {e}")

    # 2. dated reminders in range
    try:
        rems = (db.table("reminders").select("id,what,event_at,fire_at,status")
                .eq("user_id", user_id).execute().data or [])
        for r in rems:
            when = r.get("event_at") or r.get("fire_at")
            if when and frm_iso <= when <= to_iso:
                items.append({
                    "kind": "reminder", "id": r["id"], "title": r.get("what"),
                    "at": when, "category": "reminder", "status": r.get("status"),
                })
    except Exception as e:
        print(f"[Calendar] reminders query failed: {e}")

    # 3. recurring care_schedule projected onto each day in range
    try:
        sched = (db.table("care_schedule").select("*")
                 .eq("user_id", user_id).eq("active", True).execute().data or [])
        day = frm
        while day <= to:
            weekday = day.strftime("%A").lower()
            for s in sched:
                days_spec = (s.get("days") or "daily").lower()
                fires = ("daily" in days_spec) or (weekday[:3] in days_spec) or (weekday in days_spec)
                if fires:
                    tod = s.get("time_of_day") or "09:00"
                    items.append({
                        "kind": "routine", "id": s["id"],
                        "title": s.get("label"),
                        "at": f"{day.strftime('%Y-%m-%d')}T{tod}:00",
                        "category": s.get("type") or "routine",
                        "dose": s.get("dose"),
                    })
            day += timedelta(days=1)
    except Exception as e:
        print(f"[Calendar] schedule projection failed: {e}")

    items.sort(key=lambda x: x.get("at") or "")
    return {"user_id": user_id, "from": frm_iso, "to": to_iso, "items": items}


@router.post("")
def add_event(ev: CalendarEvent):
    """Add a calendar event. If reminder_enabled, also spawn a reminder."""
    db = _db()
    row = ev.model_dump()
    try:
        res = db.table("calendar_events").insert(row).execute()
        created = res.data[0] if res.data else None
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"insert failed: {str(e)[:100]}")

    # spawn a reminder if enabled
    #
    # Two independent paths can catch one message: detect_and_store_reminder
    # parses "remind me at X", and Nancy's add_calendar_event tool fires on
    # "anything happening at a date/time". "Call home in 5 minutes" is both, so
    # the user gets two identical notifications. Skip the spawn when a pending
    # reminder already exists at this moment — whichever path ran first wins.
    if ev.reminder_enabled and created:
        try:
            dupe = (db.table("reminders").select("id")
                    .eq("user_id", ev.user_id)
                    .eq("fire_at", ev.event_at)
                    .eq("status", "pending")
                    .execute()).data
        except Exception:
            dupe = []
        if dupe:
            print(f"[Calendar] reminder already pending at {ev.event_at} — not spawning")
            return {"status": "created", "event": created}

        try:
            db.table("reminders").insert({
                "user_id": ev.user_id,
                "what": ev.title,
                "event_at": ev.event_at,
                "fire_at": ev.event_at,
                "status": "pending",
                "source": "calendar",
            }).execute()
        except Exception as e:
            print(f"[Calendar] reminder spawn failed: {e}")

    return {"status": "created", "event": created}


@router.put("/{event_id}")
def update_event(event_id: str, upd: CalendarUpdate):
    db = _db()
    patch = {k: v for k, v in upd.model_dump().items() if v is not None}
    if not patch:
        return {"status": "no changes"}
    try:
        res = db.table("calendar_events").update(patch).eq("id", event_id).execute()
        return {"status": "updated", "event": res.data[0] if res.data else None}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:100])


@router.delete("/{event_id}")
def delete_event(event_id: str):
    db = _db()
    try:
        db.table("calendar_events").delete().eq("id", event_id).execute()
        return {"status": "deleted", "id": event_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:100])

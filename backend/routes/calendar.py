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


def _ts(s):
    """A stored timestamp as an aware UTC datetime, or None."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except Exception:
        return None


@router.get("/{user_id}")
def get_calendar(user_id: str, days: int = 7, start: str = None, routine_days: int = 1):
    """Unified timeline: calendar_events + reminders + her daily routine, over
    [start, start+days]. Every "at" is a UTC ISO timestamp.

    What this used to return (seen 16 Oct on her phone):
    - the reminder a calendar event spawns, listed next to the event — so
      "Durga Puja pandal darshan" appeared twice at 1:00 PM;
    - cancelled reminders ("Plan (to be decided)", cancelled that evening);
    - the routine on every one of fifteen days, a hundred cards of Breakfast
      and Lunch, each stamped "<date>T08:00:00:00" — time_of_day already has
      seconds — which the app could not read ("Undefined, NaN Undefined");
      and her local time sent without its offset, so it would have shown
      08:00 as 1:30 PM once it parsed.
    Now: an event says whether a reminder will ring for it; cancelled
    reminders are left out; the routine is projected for `routine_days`
    (today, by default) in her time zone.
    """
    db = _db()
    now = datetime.now(timezone.utc)
    frm = _ts(start) or now
    to = frm + timedelta(days=days)
    frm_iso, to_iso = frm.isoformat(), to.isoformat()
    try:
        from zoneinfo import ZoneInfo
        from memory.time_context import get_user_timezone
        tz = ZoneInfo(get_user_timezone(user_id) or "Asia/Kolkata")
    except Exception:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Kolkata")

    items, events = [], []

    # 1. calendar_events in range
    try:
        evs = (db.table("calendar_events").select("*")
               .eq("user_id", user_id)
               .gte("event_at", frm_iso).lte("event_at", to_iso)
               .order("event_at").execute().data or [])
        for e in evs:
            at = _ts(e.get("event_at"))
            if not at:
                continue
            it = {
                "kind": "event", "id": e["id"], "title": e.get("title"),
                "at": at.isoformat(), "end_at": e.get("end_at"),
                "category": e.get("category"), "notes": e.get("notes"),
                "location": e.get("location"), "created_by": e.get("created_by"),
                "reminder": False,
            }
            items.append(it)
            events.append(it)
    except Exception as e:
        print(f"[Calendar] events query failed: {e}")

    # 2. reminders in range. One spawned by an event is that event's bell,
    #    not a second entry; a cancelled one is not on her calendar.
    try:
        rems = (db.table("reminders").select("id,what,event_at,fire_at,status,source")
                .eq("user_id", user_id).execute().data or [])
        for r in rems:
            if r.get("status") == "cancelled":
                continue
            at = _ts(r.get("event_at")) or _ts(r.get("fire_at"))
            if not at or not (frm <= at <= to):
                continue
            if r.get("source") == "calendar":
                ev = next((x for x in events if _ts(x["at"]) == at), None)
                if ev:
                    ev["reminder"] = ev["reminder"] or r.get("status") == "pending"
                    continue
            items.append({
                "kind": "reminder", "id": r["id"], "title": r.get("what"),
                "at": at.isoformat(), "category": "reminder", "status": r.get("status"),
            })
    except Exception as e:
        print(f"[Calendar] reminders query failed: {e}")

    # 3. her daily routine, in her time zone, for `routine_days` days
    try:
        sched = (db.table("care_schedule").select("*")
                 .eq("user_id", user_id).eq("active", True).execute().data or [])
        first = frm.astimezone(tz).date()
        for i in range(max(0, routine_days)):
            day = first + timedelta(days=i)
            weekday = day.strftime("%A").lower()
            for s in sched:
                days_spec = (s.get("days") or "daily").lower()
                if not (("daily" in days_spec) or (weekday[:3] in days_spec) or (weekday in days_spec)):
                    continue
                tod = str(s.get("time_of_day") or "")[:5]
                try:
                    hh, mm = int(tod[:2]), int(tod[3:5])
                except Exception:
                    continue   # no time: not placeable on a day
                at = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz).astimezone(timezone.utc)
                items.append({
                    "kind": "routine", "id": s["id"],
                    "title": s.get("label"),
                    "at": at.isoformat(),
                    "category": s.get("type") or "routine",
                    "dose": s.get("dose"),
                })
    except Exception as e:
        print(f"[Calendar] schedule projection failed: {e}")

    items.sort(key=lambda x: x.get("at") or "")
    return {"user_id": user_id, "from": frm_iso, "to": to_iso, "items": items}


def _tz(user_id: str):
    from zoneinfo import ZoneInfo
    try:
        from memory.time_context import get_user_timezone
        return ZoneInfo(get_user_timezone(user_id) or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def _local(user_id: str, at) -> str:
    d = _ts(at)
    return d.astimezone(_tz(user_id)).strftime("%A %d %B, %I:%M %p") if d else ""


def _pending_for(db, user_id: str, at) -> list:
    """Pending reminders for the thing at this moment (any spelling of it)."""
    when = _ts(at)
    try:
        rows = (db.table("reminders").select("*").eq("user_id", user_id)
                .eq("status", "pending").execute()).data or []
    except Exception:
        return []
    return [r for r in rows if when and (_ts(r.get("event_at")) or _ts(r.get("fire_at"))) == when]


def _spawn_reminder(db, user_id: str, title: str, at) -> Optional[dict]:
    """The reminder for something on her calendar, with its lead-up: a
    heads-up that morning, one an hour before, one just before
    (reminder_engine.design_nudges). It used to ring once, at the event."""
    when = _ts(at)
    have = _pending_for(db, user_id, when)
    if have:
        print(f"[Calendar] reminder already pending at {when} — not spawning")
        return have[0]
    from memory.reminder_engine import design_nudges
    nudges = design_nudges(user_id, title, when)
    if not nudges:
        return None   # already passed
    try:
        res = db.table("reminders").insert({
            "user_id": user_id, "what": title,
            "event_at": when.isoformat(), "fire_at": nudges[0]["at"],
            "nudges": nudges, "status": "pending", "source": "calendar",
        }).execute()
        return (res.data or [None])[0]
    except Exception as e:
        print(f"[Calendar] reminder spawn failed: {e}")
        return None


def _cancel_reminders(db, user_id: str, at) -> int:
    n = 0
    for r in _pending_for(db, user_id, at):
        if r.get("source") == "calendar":
            db.table("reminders").update({"status": "cancelled"}).eq("id", r["id"]).execute()
            n += 1
    return n


def _same_plan(user_id: str, title: str, at, others: list) -> Optional[dict]:
    """An event already on that day that is this same plan, or None. Asked of
    the model, one pair at a time and cached: "Durga Puja pandal darshan" and
    "pandal jaana" are one plan; a doctor visit and a pandal visit on the same
    day are two."""
    from memory.judge import yes_no
    tz = _tz(user_id)
    for o in others:
        try:
            if yes_no(f'An elderly woman\u2019s calendar for {_ts(at).astimezone(tz).strftime("%A %d %B")}.\n'
                      f'Already there: "{o.get("title")}" at {_ts(o.get("event_at")).astimezone(tz).strftime("%I:%M %p")}.\n'
                      f'Now being added: "{title}" at {_ts(at).astimezone(tz).strftime("%I:%M %p")}.\n'
                      f'Is the new one the SAME plan told again (perhaps in other words, '
                      f'perhaps with a new time), not a second, different thing?',
                      key=f"cal_same:{user_id}:{o.get('id')}:{title.lower()}"):
                return o
        except Exception as e:
            print(f"[Calendar] same-plan check failed: {e}")
    return None


@router.post("")
def add_event(ev: CalendarEvent):
    """Add a calendar event. If reminder_enabled, also make its reminder.

    The same plan told again is the same card. "Kal pandal jaenge" said in a
    second chat used to save a second event — only the reminder was checked
    for duplicates. Now an event that day which is the same plan is kept;
    if the time changed, it moves, and its reminder with it.
    """
    db = _db()
    at = _ts(ev.event_at)
    if not at:
        raise HTTPException(status_code=400, detail="event_at is not a time")
    tz = _tz(ev.user_id)
    day = at.astimezone(tz).date()
    try:
        from datetime import time as _time
        d0 = datetime.combine(day, _time(0, 0), tz).astimezone(timezone.utc)
        others = (db.table("calendar_events").select("*").eq("user_id", ev.user_id)
                  .gte("event_at", d0.isoformat())
                  .lt("event_at", (d0 + timedelta(days=1)).isoformat())
                  .execute()).data or []
    except Exception:
        others = []
    same = _same_plan(ev.user_id, ev.title, at, others) if others else None
    if same:
        old_at = _ts(same.get("event_at"))
        if old_at and abs((old_at - at).total_seconds()) < 300:
            print(f"[Calendar] {ev.title!r} is {same.get('title')!r}, already there — kept one")
            rem = (_pending_for(db, ev.user_id, old_at) or [None])[0]
            return {"status": "already there", "event": same, "reminder": rem}
        db.table("calendar_events").update({"event_at": at.isoformat()}).eq("id", same["id"]).execute()
        _cancel_reminders(db, ev.user_id, old_at)
        same = dict(same, event_at=at.isoformat())
        rem = _spawn_reminder(db, ev.user_id, same.get("title") or ev.title, at) if ev.reminder_enabled else None
        print(f"[Calendar] {same.get('title')!r} moved to {at.isoformat()}")
        return {"status": "moved", "event": same, "reminder": rem,
                "now_at": _local(ev.user_id, at)}

    row = ev.model_dump()
    row["event_at"] = at.isoformat()
    try:
        res = db.table("calendar_events").insert(row).execute()
        created = res.data[0] if res.data else None
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"insert failed: {str(e)[:100]}")

    # Its reminder is returned with it: the chat uses it as the reply's
    # reminder, so the detector does not make a second one from the same
    # sentence (16 Oct: "Durga Puja pandal darshan" at 13:00 here, "Plan (to
    # be decided)" at 12:00 from the detector, six seconds apart).
    rem = _spawn_reminder(db, ev.user_id, ev.title, at) if (ev.reminder_enabled and created) else None
    return {"status": "created", "event": created, "reminder": rem}


def change_event(user_id: str, about: str, action: str, new_event_at: str = "") -> dict:
    """She calls something off or moves it, in the chat: "pandal nahi jaenge",
    "doctor 4 baje ho gaya", "woh reminder hata do". Which thing she means is
    read by the model from her upcoming events and reminders. Its reminder
    goes or moves with it; the app resyncs the phone's alerts after the reply.
    """
    db = _db()
    now = datetime.now(timezone.utc)
    tz = _tz(user_id)
    cands = []
    try:
        for e in (db.table("calendar_events").select("*").eq("user_id", user_id)
                  .gte("event_at", (now - timedelta(hours=2)).isoformat())
                  .lte("event_at", (now + timedelta(days=60)).isoformat())
                  .execute()).data or []:
            cands.append(("event", e, e.get("title"), _ts(e.get("event_at"))))
        for r in (db.table("reminders").select("*").eq("user_id", user_id)
                  .eq("status", "pending").execute()).data or []:
            if r.get("source") == "calendar":
                continue   # goes with its event
            cands.append(("reminder", r, r.get("what"), _ts(r.get("event_at")) or _ts(r.get("fire_at"))))
    except Exception as e:
        return {"status": "failed", "error": str(e)[:100]}
    cands = [c for c in cands if c[3]]
    if not cands:
        return {"status": "nothing on her calendar"}
    cands.sort(key=lambda c: c[3])
    listing = "\n".join(f"{i + 1}. {c[2]} — {c[3].astimezone(tz).strftime('%A %d %B, %I:%M %p')}"
                        for i, c in enumerate(cands))
    try:
        from llm import ask
        ans = (ask(f"""An elderly woman wants to {"call off" if action == "cancel" else "change the time of"} something: "{about}"

Her upcoming plans and reminders:
{listing}

Which one does she mean? Answer with its number, or NONE if it is not clearly one of them.""",
                   max_tokens=10) or "").upper()
        n = int("".join(ch for ch in ans if ch.isdigit()) or 0)
    except Exception as e:
        return {"status": "failed", "error": str(e)[:100]}
    if not 1 <= n <= len(cands):
        return {"status": "not sure which",
                "upcoming": [f"{c[2]} ({c[3].astimezone(tz).strftime('%a %d %b %I:%M %p')})" for c in cands[:8]]}
    kind, row, title, old_at = cands[n - 1]

    if action == "cancel":
        if kind == "event":
            db.table("calendar_events").delete().eq("id", row["id"]).execute()
            _cancel_reminders(db, user_id, old_at)
        else:
            db.table("reminders").update({"status": "cancelled"}).eq("id", row["id"]).execute()
        print(f"[Calendar] cancelled by chat: {title!r}")
        return {"status": "cancelled", "what": title, "was_at": _local(user_id, old_at)}

    new_at = _ts(new_event_at)
    if not new_at:
        return {"status": "need the new time", "what": title}
    if kind == "event":
        db.table("calendar_events").update({"event_at": new_at.isoformat()}).eq("id", row["id"]).execute()
        _cancel_reminders(db, user_id, old_at)
        rem = _spawn_reminder(db, user_id, title, new_at)
    else:
        db.table("reminders").update({"status": "cancelled"}).eq("id", row["id"]).execute()
        from memory.reminder_engine import design_nudges
        nudges = design_nudges(user_id, title, new_at)
        rem = None
        if nudges:
            rem = (db.table("reminders").insert({
                "user_id": user_id, "what": title, "event_at": new_at.isoformat(),
                "fire_at": nudges[0]["at"], "nudges": nudges,
                "status": "pending", "source": "user",
            }).execute().data or [None])[0]
    print(f"[Calendar] moved by chat: {title!r} -> {new_at.isoformat()}")
    return {"status": "moved", "what": title, "was_at": _local(user_id, old_at),
            "now_at": _local(user_id, new_at), "reminder": rem}


@router.put("/{event_id}")
def update_event(event_id: str, upd: CalendarUpdate):
    """Change a plan from the app or the caregiver dashboard. Its reminder
    goes with it: a new time or a new name cancels the old alerts and plans
    new ones (the same helpers as Nancy's change_calendar_event). This used to
    move the event and leave the alerts ringing at the old time."""
    db = _db()
    patch = {k: v for k, v in upd.model_dump().items() if v is not None}
    if not patch:
        return {"status": "no changes"}
    try:
        old = (db.table("calendar_events").select("*").eq("id", event_id)
               .limit(1).execute()).data or []
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:100])
    if not old:
        raise HTTPException(status_code=404, detail="no such event")
    old = old[0]
    if "event_at" in patch:
        at = _ts(patch["event_at"])
        if not at:
            raise HTTPException(status_code=400, detail="event_at is not a time")
        patch["event_at"] = at.isoformat()
    try:
        res = db.table("calendar_events").update(patch).eq("id", event_id).execute()
        ev = res.data[0] if res.data else {**old, **patch}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:100])
    rem = None
    moved = "event_at" in patch and _ts(patch["event_at"]) != _ts(old.get("event_at"))
    renamed = "title" in patch and patch["title"] != old.get("title")
    rings = patch.get("reminder_enabled", old.get("reminder_enabled", True)) is not False
    if moved or renamed or "reminder_enabled" in patch:
        _cancel_reminders(db, old["user_id"], old.get("event_at"))
        if rings:
            rem = _spawn_reminder(db, old["user_id"], ev.get("title") or old.get("title"), ev.get("event_at"))
        print(f"[Calendar] {ev.get('title')!r} changed; its alerts re-planned")
    else:
        rem = (_pending_for(db, old["user_id"], old.get("event_at")) or [None])[0]
    return {"status": "updated", "event": ev, "reminder": rem}


@router.delete("/{event_id}")
def delete_event(event_id: str):
    """Remove a plan, and its alerts with it — they kept ringing for a plan
    that was gone."""
    db = _db()
    try:
        old = (db.table("calendar_events").select("*").eq("id", event_id)
               .limit(1).execute()).data or []
        db.table("calendar_events").delete().eq("id", event_id).execute()
        n = _cancel_reminders(db, old[0]["user_id"], old[0].get("event_at")) if old else 0
        return {"status": "deleted", "id": event_id, "alerts_cancelled": n}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:100])


@router.get("/{user_id}/days")
def days_with_plans(user_id: str, start: str, days: int = 42) -> dict:
    """Which days have something planned, for the month view's dots. Her
    days (her time zone), counted; no routine, no detail. One small read per
    month as she scrolls through the year."""
    db = _db()
    tz = _tz(user_id)
    try:
        from datetime import time as _time
        first = datetime.fromisoformat(start[:10]).date()
    except Exception:
        raise HTTPException(status_code=400, detail="start is YYYY-MM-DD")
    frm = datetime.combine(first, _time(0, 0), tz).astimezone(timezone.utc)
    to = frm + timedelta(days=max(1, min(days, 120)))
    out = {}

    def _count(at):
        if at and frm <= at < to:
            k = at.astimezone(tz).date().isoformat()
            out[k] = out.get(k, 0) + 1
    try:
        for e in (db.table("calendar_events").select("event_at").eq("user_id", user_id)
                  .gte("event_at", frm.isoformat()).lt("event_at", to.isoformat())
                  .execute()).data or []:
            _count(_ts(e.get("event_at")))
        for r in (db.table("reminders").select("event_at,fire_at,status,source")
                  .eq("user_id", user_id).execute()).data or []:
            if r.get("status") == "cancelled" or r.get("source") == "calendar":
                continue   # an event's own reminder is the event, counted above
            _count(_ts(r.get("event_at")) or _ts(r.get("fire_at")))
    except Exception as e:
        print(f"[Calendar] days read failed: {e}")
    return {"user_id": user_id, "start": first.isoformat(), "days": out}

"""
CARE ROUTES
CRUD for a user's declared care records — the authoritative facts a caregiver
maintains, distinct from the proactive-messaging engine in schedule.py.

  care_schedule — time-anchored recurring items (medication, meal, routine).
                  These FIRE reminders; the engine reads them.
  care_facts    — standing rules with no time (dietary, medical, preference).
                  These CONSTRAIN nudges.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


def _db():
    from supabase_store import get_client
    return get_client()


class ScheduleItem(BaseModel):
    user_id:     str
    type:        str
    label:       str
    time_of_day: str
    days:        str = "daily"
    dose:        Optional[str] = None
    notes:       Optional[str] = None
    created_by:  Optional[str] = None


class ScheduleUpdate(BaseModel):
    type:        Optional[str] = None
    label:       Optional[str] = None
    time_of_day: Optional[str] = None
    days:        Optional[str] = None
    dose:        Optional[str] = None
    notes:       Optional[str] = None
    active:      Optional[bool] = None


class FactItem(BaseModel):
    user_id:    str
    type:       str
    fact:       str
    severity:   str = "normal"
    notes:      Optional[str] = None
    created_by: Optional[str] = None


class FactUpdate(BaseModel):
    type:     Optional[str] = None
    fact:     Optional[str] = None
    severity: Optional[str] = None
    notes:    Optional[str] = None
    active:   Optional[bool] = None


@router.get("/schedule/{user_id}")
def list_schedule(user_id: str):
    try:
        rows = (_db().table("care_schedule").select("*")
                .eq("user_id", user_id).eq("active", True)
                .order("time_of_day").execute()).data or []
        return {"user_id": user_id, "items": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(500, f"list_schedule failed: {e}")


@router.post("/schedule")
def add_schedule(item: ScheduleItem):
    if item.type not in ("medication", "meal", "routine"):
        raise HTTPException(400, "type must be medication|meal|routine")
    try:
        row = (_db().table("care_schedule").insert(item.model_dump()).execute()).data
        return {"created": row[0] if row else None}
    except Exception as e:
        raise HTTPException(500, f"add_schedule failed: {e}")


@router.put("/schedule/{item_id}")
def update_schedule(item_id: str, patch: ScheduleUpdate):
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "no fields to update")
    try:
        row = (_db().table("care_schedule").update(fields)
               .eq("id", item_id).execute()).data
        return {"updated": row[0] if row else None}
    except Exception as e:
        raise HTTPException(500, f"update_schedule failed: {e}")


@router.delete("/schedule/{item_id}")
def delete_schedule(item_id: str):
    try:
        (_db().table("care_schedule").update({"active": False})
         .eq("id", item_id).execute())
        return {"deleted": item_id}
    except Exception as e:
        raise HTTPException(500, f"delete_schedule failed: {e}")


@router.get("/facts/{user_id}")
def list_facts(user_id: str):
    try:
        rows = (_db().table("care_facts").select("*")
                .eq("user_id", user_id).eq("active", True)
                .order("severity", desc=True).execute()).data or []
        return {"user_id": user_id, "facts": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(500, f"list_facts failed: {e}")


@router.post("/facts")
def add_fact(item: FactItem):
    if item.type not in ("dietary", "medical", "preference"):
        raise HTTPException(400, "type must be dietary|medical|preference")
    if item.severity not in ("normal", "important", "critical"):
        raise HTTPException(400, "severity must be normal|important|critical")
    try:
        row = (_db().table("care_facts").insert(item.model_dump()).execute()).data
        return {"created": row[0] if row else None}
    except Exception as e:
        raise HTTPException(500, f"add_fact failed: {e}")


@router.put("/facts/{fact_id}")
def update_fact(fact_id: str, patch: FactUpdate):
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "no fields to update")
    try:
        row = (_db().table("care_facts").update(fields)
               .eq("id", fact_id).execute()).data
        return {"updated": row[0] if row else None}
    except Exception as e:
        raise HTTPException(500, f"update_fact failed: {e}")


@router.delete("/facts/{fact_id}")
def delete_fact(fact_id: str):
    try:
        (_db().table("care_facts").update({"active": False})
         .eq("id", fact_id).execute())
        return {"deleted": fact_id}
    except Exception as e:
        raise HTTPException(500, f"delete_fact failed: {e}")


# ── Wellbeing dashboard — one call, everything the caregiver needs ──────────────
# All from data Nancy already captures: narrative summary, session valence
# (LLM-scored, honest signal), engagement, health clusters, reminder adherence.

@router.get("/wellbeing/{user_id}")
def get_wellbeing(user_id: str, days: int = 7):
    from datetime import datetime, timezone, timedelta
    db = _db()
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()

    # 1. Narrative (hero) + profile (name/health)
    mem_rows = db.table("user_memory").select("summary,session_count").eq("user_id", user_id).limit(1).execute().data or []
    mem = mem_rows[0] if mem_rows else {}
    prof_rows = db.table("user_profile").select("name,age_group,location,health").eq("user_id", user_id).limit(1).execute().data or []
    prof = prof_rows[0] if prof_rows else {}

    # 2. Sessions in range (valence trend + engagement + weather)
    sessions = (db.table("sessions")
                .select("created_at,valence,arousal,summary")
                .eq("user_id", user_id).gte("created_at", since)
                .order("created_at", desc=False).execute().data or [])

    # per-day aggregation
    from collections import defaultdict
    day_valences = defaultdict(list)
    day_counts = defaultdict(int)
    for s in sessions:
        day = (s.get("created_at") or "")[:10]
        if not day:
            continue
        day_counts[day] += 1
        v = s.get("valence")
        if v is not None:
            day_valences[day].append(float(v))

    def _tone(v):
        if v is None:      return "unknown"
        if v >= 0.35:      return "warm"
        if v <= -0.35:     return "low"
        return "mixed"

    valence_trend = []
    emotional_weather = []
    for day in sorted(set(list(day_valences.keys()) + list(day_counts.keys()))):
        vs = day_valences.get(day, [])
        avg_v = round(sum(vs) / len(vs), 3) if vs else None
        valence_trend.append({"date": day, "valence": avg_v, "sessions": day_counts.get(day, 0)})
        emotional_weather.append({"date": day, "tone": _tone(avg_v)})

    # composite wellbeing score from recent valence: map −1..+1 → 0..100
    scored = [d["valence"] for d in valence_trend if d["valence"] is not None]
    if scored:
        avg_recent = sum(scored) / len(scored)
        wellbeing_score = round((avg_recent + 1) / 2 * 100)
    else:
        wellbeing_score = None

    # 3. Engagement
    total_sessions = len(sessions)

    # 4. Health flags (HEALTH_WELLNESS clusters)
    health = (db.table("interest_clusters")
              .select("label,strength,event_count")
              .eq("user_id", user_id).eq("pillar", "HEALTH_WELLNESS")
              .order("strength", desc=True).limit(8).execute().data or [])
    health_flags = [{"label": h.get("label"), "strength": h.get("strength"),
                     "mentions": h.get("event_count")} for h in health]

    # 5. Reminders — upcoming + simple adherence from nudge fired-state
    rems = (db.table("reminders").select("what,fire_at,event_at,status,nudges,source")
            .eq("user_id", user_id).order("fire_at", desc=False).execute().data or [])
    upcoming, past = [], []
    for r in rems:
        item = {"what": r.get("what"), "fire_at": r.get("fire_at"),
                "status": r.get("status"), "source": r.get("source")}
        if r.get("status") == "pending":
            upcoming.append(item)
        else:
            past.append(item)
    # adherence: of past reminders, how many actually fired (delivered) vs cancelled
    fired = sum(1 for r in rems if r.get("status") == "fired")
    cancelled = sum(1 for r in rems if r.get("status") == "cancelled")

    # 6. Care schedule (recurring meds/routines the caregiver set)
    schedule = (db.table("care_schedule").select("type,label,time_of_day,days,dose,active")
                .eq("user_id", user_id).eq("active", True).execute().data or [])

    return {
        "user_id":        user_id,
        "name":           prof.get("name"),
        "age_group":      prof.get("age_group"),
        "location":       prof.get("location"),
        "summary":        mem.get("summary"),
        "session_count":  mem.get("session_count"),
        "wellbeing_score": wellbeing_score,
        "valence_trend":  valence_trend,
        "emotional_weather": emotional_weather,
        "engagement":     {"sessions_in_period": total_sessions, "days": days},
        "health_flags":   health_flags,
        "reminders":      {"upcoming": upcoming[:10], "past": past[:10],
                           "adherence": {"fired": fired, "cancelled": cancelled}},
        "care_schedule":  schedule,
        "range_days":     days,
    }

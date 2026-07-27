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

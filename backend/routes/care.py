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
from typing import Optional, Dict, List
from datetime import datetime, timezone

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


# ── Patterns: the anchor a day is measured against ─────────────────────────
# Declared here, observed in memory/patterns.py, never conflated: the
# divergence between what someone says their routine is and what it has
# become is the signal worth having.

class RoutineItem(BaseModel):
    label: str                       # as they typed it, any script
    at:    str                       # "06:45"


class PatternsIn(BaseModel):
    wake:     Optional[str] = None                     # "06:30"
    sleep:    Optional[str] = None
    meals:    Optional[Dict[str, str]] = None          # {"lunch": "13:00"}
    routines: Optional[List[RoutineItem]] = None


def _norm_time(t: Optional[str]) -> Optional[str]:
    """Accept 06:30 or 06:30:00, store the latter."""
    if not t:
        return None
    parts = str(t).strip().split(":")
    if len(parts) < 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return f"{h:02d}:{m:02d}:00"


def _canonicalise(label: str) -> str:
    """A canonical English label for a routine written in any script.

    The extractor already produces this — it returns canonical English
    alongside the surface form — so no separate translation step is needed. It
    expects sentences though, and a bare label sometimes comes back as "self",
    so the label is wrapped in the minimal sentence that gives it the shape it
    is built for.
    """
    text = (label or "").strip()
    if not text:
        return ""
    try:
        from memory.profile_enricher import _extract_propositions
        # Bare, not wrapped in a sentence. Wrapping was meant to give the
        # extractor the shape it expects, and did the opposite: with a full
        # sentence it identifies the SPEAKER as the subject and the routine as
        # the object, so "roz main ਸਵੇਰ ਦੀ ਪੂਜਾ karti hoon" returns "self"
        # while the bare label returns "morning prayer".
        props = _extract_propositions(text, "canon") or []
        for p in props:
            subj = (p.get("subject") or "").strip()
            if subj and subj.lower() not in ("self", "user", ""):
                return subj
            obj = (p.get("object") or "").strip()
            if obj:
                return obj
    except Exception as e:
        print(f"[Patterns] canonicalise failed for {text!r}: {e}")
    return text          # fall back to their own words rather than nothing


def _upsert_declared(user_id: str, kind: str, at: str,
                     label: Optional[str] = None,
                     label_native: Optional[str] = None):
    """Write what they declared, leaving anything observed untouched."""
    db = _db()
    row = {
        "user_id":      user_id,
        "kind":         kind,
        "label":        label,
        "label_native": label_native,
        "declared_at":  at,
        "source":       "declared",
        "updated_at":   datetime.now(timezone.utc).isoformat(),
    }
    try:
        q = (db.table("user_patterns").select("id")
             .eq("user_id", user_id).eq("kind", kind))
        # Match on what they typed, not on the canonical label. Canonicalisation
        # is a model call, so the same input can come back slightly differently
        # between runs — matching on it turns an edit into a duplicate, which is
        # exactly what happened: one routine became two rows, "ਸਵੇਰ ਦੀ ਪੂਜਾ" and
        # "morning prayer", for the same 06:45 puja.
        if label is None:
            q = q.is_("label", "null")
        elif label_native:
            q = q.eq("label_native", label_native)
        else:
            q = q.eq("label", label)
        existing = q.limit(1).execute().data or []

        if existing:
            db.table("user_patterns").update(row).eq("id", existing[0]["id"]).execute()
        else:
            db.table("user_patterns").insert(row).execute()
    except Exception as e:
        print(f"[Patterns] upsert failed ({kind}/{label}): {e}")


@router.get("/patterns/{user_id}")
def get_patterns(user_id: str):
    """Everything known about their day. Both screens read this — the elder's
    view and the caregiver's — because a routine held silently and reported to
    family is a different thing from one shown to the person it describes."""
    try:
        rows = (_db().table("user_patterns").select("*")
                .eq("user_id", user_id).order("kind").execute()).data or []
    except Exception as e:
        raise HTTPException(500, f"read failed: {e}")

    out = {"wake": None, "sleep": None, "meals": [], "routines": [], "drifting": []}
    for r in rows:
        item = {
            "declared_at":  r.get("declared_at"),
            "observed_at":  r.get("observed_at"),
            "label":        r.get("label"),
            "label_native": r.get("label_native"),
            "confidence":   r.get("confidence"),
            "spread_min":   r.get("spread_min"),
        }
        kind = r.get("kind")
        if kind in ("wake", "sleep"):
            out[kind] = item
        elif kind == "meal":
            out["meals"].append(item)
        elif kind == "routine":
            out["routines"].append(item)

        # Surfaced separately so a screen can show it without hunting: this is
        # the actionable part, and the caregiver view is built around it.
        if r.get("drift_min"):
            out["drifting"].append({
                "kind": kind, "label": r.get("label"),
                "drift_min": r.get("drift_min"),
                "since": r.get("drift_since"),
                "note": r.get("drift_note"),
            })
    return out


@router.post("/patterns/{user_id}")
def set_patterns(user_id: str, body: PatternsIn):
    """What the onboarding form submits. Every field optional — a form that
    traps someone on first launch is worse than no form, and anything left
    blank simply gets asked in conversation later."""
    written = 0

    wake = _norm_time(body.wake)
    if wake:
        _upsert_declared(user_id, "wake", wake)
        written += 1

    sleep = _norm_time(body.sleep)
    if sleep:
        _upsert_declared(user_id, "sleep", sleep)
        written += 1

    for name, t in (body.meals or {}).items():
        at = _norm_time(t)
        if at:
            _upsert_declared(user_id, "meal", at, label=name.strip().lower())
            written += 1

    for item in (body.routines or []):
        at = _norm_time(item.at)
        if not at or not item.label.strip():
            continue
        native = item.label.strip()
        _upsert_declared(user_id, "routine", at,
                         label=_canonicalise(native), label_native=native)
        written += 1

    return {"status": "ok", "written": written}


# ── Declared interests ────────────────────────────────────────────────────────
# What someone names on the setup screen, as distinct from what the system
# notices them talking about. Both are real interests; only one was stated, and
# the difference matters — a declared one should not have to accumulate
# mentions before it counts, and should not be swept by the cluster cleaner for
# only appearing once.

class InterestsIn(BaseModel):
    # {"sangeet": ["Lata Mangeshkar", "Kishore Kumar"], "khana": ["dal khichdi"]}
    interests: Dict[str, List[str]]


@router.post("/interests/{user_id}")
def set_interests(user_id: str, body: InterestsIn):
    from memory.categories import CATEGORIES, record_declared_interest

    written, skipped = 0, []
    for category, items in (body.interests or {}).items():
        if category not in CATEGORIES:
            skipped.append(category)
            continue
        for text in (items or []):
            # Each entry is canonicalised separately, so "Lata, Rafi" typed as
            # one line becomes one cluster rather than two. The screen splits on
            # commas before sending.
            if record_declared_interest(user_id, category, text):
                written += 1

    return {"status": "ok", "written": written,
            **({"unknown_categories": skipped} if skipped else {})}


@router.get("/interests/{user_id}")
def get_interests(user_id: str):
    """What they declared, for pre-filling the screen. Deliberately not what was
    learned — that would put words in their mouth on a form asking what they
    like."""
    try:
        from memory.declared import get_declared
        return {"interests": get_declared(user_id).interests}
    except Exception as e:
        raise HTTPException(500, f"read failed: {e}")

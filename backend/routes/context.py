"""
CONTEXT ROUTES
The phone reports its own state — timezone, location, local time — and the
backend stores the latest. The engine and scheduler READ these stored values
(never fetch from the phone, which may be closed when a proactive check runs).

This is the pipe that keeps time_context fresh with real data.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from math import radians, sin, cos, sqrt, atan2

router = APIRouter()


def _db():
    from supabase_store import get_client
    return get_client()


class ContextReport(BaseModel):
    user_id:    str
    timezone:   Optional[str] = None       # IANA, e.g. "Asia/Kolkata"
    latitude:   Optional[float] = None
    longitude:  Optional[float] = None
    local_time: Optional[str] = None       # phone's own clock, for sanity


def _km_between(lat1, lng1, lat2, lng2) -> float:
    """Haversine distance in km. Returns -1 if any coord missing."""
    if None in (lat1, lng1, lat2, lng2):
        return -1.0
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlng/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))


# how far from home counts as "meaningfully new place"
NEW_PLACE_KM = 25.0


@router.post("/report")
def report_context(rpt: ContextReport):
    """Phone reports its context; we upsert the latest and flag if they've moved."""
    from datetime import datetime, timezone
    try:
        existing = (_db().table("user_context").select("*")
                    .eq("user_id", rpt.user_id).limit(1).execute()).data or []
        prev = existing[0] if existing else {}

        # first time we ever see this user's location, treat it as home
        home_lat = prev.get("home_lat")
        home_lng = prev.get("home_lng")
        if home_lat is None and rpt.latitude is not None:
            home_lat, home_lng = rpt.latitude, rpt.longitude

        dist = _km_between(rpt.latitude, rpt.longitude, home_lat, home_lng)
        away_from_home = dist > NEW_PLACE_KM if dist >= 0 else False

        row = {
            "user_id":         rpt.user_id,
            "last_context_at": datetime.now(timezone.utc).isoformat(),
            "updated_at":      datetime.now(timezone.utc).isoformat(),
        }
        if rpt.timezone:      row["timezone"]        = rpt.timezone
        if rpt.latitude is not None:  row["last_lat"] = rpt.latitude
        if rpt.longitude is not None: row["last_lng"] = rpt.longitude
        if rpt.local_time:    row["last_local_time"] = rpt.local_time
        if home_lat is not None:
            row["home_lat"] = home_lat
            row["home_lng"] = home_lng

        _db().table("user_context").upsert(row, on_conflict="user_id").execute()

        return {
            "stored":         True,
            "away_from_home": away_from_home,
            "distance_km":    round(dist, 1) if dist >= 0 else None,
        }
    except Exception as e:
        raise HTTPException(500, f"report_context failed: {e}")


@router.get("/{user_id}")
def get_context(user_id: str):
    """Read a user's stored context (debug / engine use)."""
    try:
        rows = (_db().table("user_context").select("*")
                .eq("user_id", user_id).limit(1).execute()).data or []
        return rows[0] if rows else {"user_id": user_id, "context": None}
    except Exception as e:
        raise HTTPException(500, f"get_context failed: {e}")

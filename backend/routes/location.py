"""
LOCATION — live device location from the mobile app.

  POST /location/gps      — store current GPS coordinates
  GET  /location/{user_id} — what location the backend is currently using
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter()


class GpsUpdate(BaseModel):
    user_id:  str   = "default"
    lat:      float = Field(..., ge=-90,  le=90)
    lng:      float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = None   # metres, from the device


@router.post("/gps")
def update_gps(req: GpsUpdate):
    """Store live coordinates reported by the device."""
    from memory.location_engine import update_location_from_gps
    return update_location_from_gps(req.user_id, req.lat, req.lng)


@router.get("/{user_id}")
def current_location(user_id: str):
    """What location weather/places will actually use for this user."""
    from memory.location_engine import get_active_location
    return get_active_location(user_id)

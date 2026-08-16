"""
PUSH — device token registration for server-initiated notifications.

POST /push/register    store/refresh a device's Expo push token
POST /push/unregister  remove a token (logout / permission revoked)

Local notifications cover reminders known at creation time. Push covers what
the SERVER decides later: caregiver alerts, proactive nudges, recommendations.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

router = APIRouter()


class TokenIn(BaseModel):
    user_id:    str
    expo_token: str
    platform:   Optional[str] = None


@router.post("/register")
def register_token(body: TokenIn):
    """Upsert a device token. Same user+token just refreshes updated_at."""
    from supabase_store import get_client
    if not body.expo_token.startswith("ExponentPushToken"):
        return {"ok": False, "error": "not an Expo push token"}
    db = get_client()
    db.table("push_tokens").upsert({
        "user_id":    body.user_id,
        "expo_token": body.expo_token,
        "platform":   body.platform,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    print(f"[Push] registered {body.platform} token for {body.user_id}")
    return {"ok": True}


@router.post("/unregister")
def unregister_token(body: TokenIn):
    """Drop a token — logout, or permission revoked."""
    from supabase_store import get_client
    db = get_client()
    (db.table("push_tokens").delete()
       .eq("user_id", body.user_id).eq("expo_token", body.expo_token).execute())
    return {"ok": True}

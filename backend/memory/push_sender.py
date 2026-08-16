"""
PUSH SENDER — delivers a message to a user's devices via Expo.

Server-initiated delivery: reminders fired by the heartbeat, caregiver alerts,
proactive nudges, recommendations. Fails soft — a push failure must never break
the scheduler pass.
"""
import httpx

EXPO_URL = "https://exp.host/--/api/v2/push/send"


def get_user_tokens(user_id: str) -> list:
    """All registered device tokens for a user (phone + tablet, iOS + Android)."""
    from supabase_store import get_client
    db = get_client()
    rows = (db.table("push_tokens").select("expo_token")
            .eq("user_id", user_id).execute()).data or []
    return [r["expo_token"] for r in rows if r.get("expo_token")]


def send_push(user_id: str, title: str, body: str, data: dict = None) -> int:
    """
    Push to every device the user has registered. Returns how many were accepted.
    Never raises — callers run inside the heartbeat.
    """
    try:
        tokens = get_user_tokens(user_id)
        if not tokens:
            print(f"[Push] no tokens for {user_id} — skipped")
            return 0

        messages = [{
            "to": t, "title": title, "body": body,
            "sound": "default", "priority": "high",
            "channelId": "reminders",
            "data": data or {},
        } for t in tokens]

        r = httpx.post(EXPO_URL, json=messages, timeout=10.0)
        r.raise_for_status()
        receipts = (r.json() or {}).get("data", [])

        ok = 0
        for tok, rec in zip(tokens, receipts):
            if rec.get("status") == "ok":
                ok += 1
            else:
                err = (rec.get("details") or {}).get("error")
                print(f"[Push] rejected for {user_id}: {rec.get('message')} ({err})")
                if err == "DeviceNotRegistered":
                    _drop_token(tok)
        print(f"[Push] sent {ok}/{len(tokens)} to {user_id}")
        return ok
    except Exception as e:
        print(f"[Push] send failed for {user_id}: {e}")
        return 0


def _drop_token(expo_token: str):
    """Expo says this device is gone — stop pushing to it."""
    try:
        from supabase_store import get_client
        get_client().table("push_tokens").delete().eq("expo_token", expo_token).execute()
        print(f"[Push] dropped dead token")
    except Exception as e:
        print(f"[Push] token cleanup failed: {e}")

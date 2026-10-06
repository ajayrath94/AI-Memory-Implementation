"""
/voice — the route the app calls to hear a message.

Returns audio bytes, so the app plays them directly rather than decoding
base64 for every message. A failure returns 204 and the app shows the text,
which is what it did before voice existed: this is an addition, never a
dependency.
"""
from fastapi import APIRouter, Response
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class SpeakRequest(BaseModel):
    text: str
    user_id: str = "default"
    # Why the message was written — the composer knows, and it decides how it
    # is said. No classifier: inferring this from the text would be guessing
    # at something the writer already had.
    intent: str = ""
    # How her day is going, from the mood read that already ran.
    valence: float = 0.0


@router.post("/speak")
def speak(req: SpeakRequest):
    """One message, spoken."""
    from memory.voice import speak as _speak
    out = _speak(req.user_id, req.text, req.intent, req.valence)
    if not out:
        # No audio. The app shows the text, as always.
        return Response(status_code=204)

    media = "audio/wav" if out["format"] == "wav" else "audio/mpeg"
    return Response(
        content=out["audio"],
        media_type=media,
        headers={
            "X-Voice": str(out.get("voice") or ""),
            "X-Tone": str(out.get("tone") or ""),
            "X-Lang": str(out.get("lang") or ""),
            # Her phone can hold a message's audio; the text does not change.
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.get("/speak")
def speak_get(text: str, user_id: str = "default", intent: str = "",
              valence: float = 0.0):
    """The same thing by GET, because expo-file-system can only download."""
    return speak(SpeakRequest(text=text, user_id=user_id, intent=intent,
                              valence=valence))


@router.get("/preference/{user_id}")
def preference(user_id: str):
    """auto | tap | off, and which voice she would hear."""
    from memory.voice import playback_preference, _voice_for
    speaker, lang = _voice_for(user_id)
    from memory.profile_store import get_user_profile
    _p = (get_user_profile(user_id) or {}).get("preferences") or {}
    return {"playback": playback_preference(user_id),
            "speak_offers": bool(_p.get("voice_speak_offers")),
            "voice": speaker, "language": lang}


class PreferenceRequest(BaseModel):
    user_id: str = "default"
    playback: str = "tap"
    # Whether an offer speaks too, when messages read themselves. Off by
    # default: a tablet reminder she should hear, a song she can choose to.
    speak_offers: bool = False


@router.post("/preference")
def set_preference(req: PreferenceRequest):
    """She chooses: spoken automatically, on a tap, or not at all.

    tap is the default — audio starting on its own in a room she is not alone
    in is the worse mistake.
    """
    if req.playback not in ("auto", "tap", "off"):
        return {"ok": False, "error": "playback must be auto, tap or off"}
    try:
        from supabase_store import get_client
        from memory.profile_store import get_user_profile
        db = get_client()
        p = get_user_profile(req.user_id) or {}
        prefs = p.get("preferences") if isinstance(p.get("preferences"), dict) else {}
        prefs["voice_playback"] = req.playback
        prefs["voice_speak_offers"] = req.speak_offers
        db.table("user_profile").update({"preferences": prefs}) \
          .eq("user_id", req.user_id).execute()
        return {"ok": True, "playback": req.playback}
    except Exception as e:
        print(f"[Voice] preference write failed: {e}")
        return {"ok": False, "error": str(e)[:120]}

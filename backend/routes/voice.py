"""
/voice — hearing her, and her hearing the companion.

    POST /voice/transcribe   her recording -> Groq Whisper -> text, in her script
    POST /voice/speak        a message -> Sarvam (Google fallback) -> audio
    GET  /voice/speak        the same, by GET, for expo-file-system
    GET  /voice/preference   auto | tap | off
    POST /voice/preference

/transcribe was lost on 14 October 2026: the commit that gave the companion
a voice ("Her companion has a voice", 43dbc02) rewrote this file for /speak
and the route the app's mic posts to went with the old one. Every recording
since got a 404 and "Could not transcribe audio". Restored as it was.

/speak:

Returns audio bytes, so the app plays them directly rather than decoding
base64 for every message. A failure returns 204 and the app shows the text,
which is what it did before voice existed: this is an addition, never a
dependency.
"""
import os
import tempfile
from fastapi import APIRouter, Response, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


# ── Hearing her ───────────────────────────────────────────────────────────────

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...),
                           user_id: str = Form("")):
    """
    Receive audio file → Groq Whisper → return transcript.
    Accepts: m4a, mp3, wav, webm, mp4

    The language hint comes from what the person declared. Forcing "en" made
    Whisper render Hinglish as approximate English; removing the hint entirely
    went too far the other way — someone saying "Mohammed Rafi" got محمد رفی,
    which is a defensible guess at the language and useless in a form. Telling
    it which script to expect fixes both.
    """
    # Whisper takes an ISO-639-1 code. The declared preference is a phrase
    # meant for a prompt — "Punjabi, written in Gurmukhi script, with English
    # words where natural" — so it is matched rather than parsed.
    lang = None
    if user_id:
        try:
            from memory.declared import get_declared
            pref = (get_declared(user_id).language.pref or "").lower()
            for needle, code in (("punjab", "pa"), ("gujarat", "gu"),
                                 ("marathi", "mr"), ("bengal", "bn"),
                                 ("tamil", "ta"), ("telugu", "te"),
                                 ("hinglish", "hi"), ("hindi", "hi"),
                                 ("english", "en")):
                if needle in pref:
                    lang = code
                    break
        except Exception as e:
            print(f"[Voice] language lookup failed: {e}")

    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set in .env")

    # Save uploaded file to temp location
    suffix = ".m4a"
    if file.filename:
        ext = file.filename.split(".")[-1]
        suffix = f".{ext}"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from groq import Groq
        client = Groq(api_key=groq_key)

        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                response_format="text",
                **({"language": lang} if lang else {}),
                # No language forced. Pinning it to English made Whisper
                # transcribe Hinglish as approximate English — "mujhe pasand
                # hai" becoming something that merely sounds like it. Detection
                # handles code-switching far better than a wrong hint does.
            )

        transcript = transcription if isinstance(transcription, str) else transcription.text
        print(f"[Voice] Transcribed: {transcript[:100]}")

        # Into the script they read, before it reaches a field. Whisper renders
        # what it hears, so one utterance can come back with names in Devanagari
        # and English words in Latin — which for someone who reads only Gurmukhi
        # is not untidy, it is unreadable.
        display = transcript.strip()
        if user_id:
            try:
                from memory.declared import get_declared
                from memory.script import to_her_script
                # The script she writes in, not one decided by her language.
                display = to_her_script(user_id, display,
                                        get_declared(user_id).language.pref)
            except Exception as e:
                print(f"[Voice] transliteration skipped: {e}")

        return {
            "transcript": display,
            "raw": transcript.strip(),
            "model":      "whisper-large-v3",
        }

    except Exception as e:
        print(f"[Voice] Transcription error: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

    finally:
        import os as _os
        try:
            _os.unlink(tmp_path)
        except Exception:
            pass


# ── Her hearing the companion ─────────────────────────────────────────────────


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

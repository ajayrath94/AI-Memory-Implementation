"""
VOICE ROUTE
Receives audio from mobile app → sends to Groq Whisper → returns transcript.
Groq Whisper is same accuracy as OpenAI Whisper but 10x faster and free tier available.
"""

import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()


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

        return {
            "transcript": transcript.strip(),
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

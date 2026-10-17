"""
HER COMPANION'S VOICE.

She is seventy and reads messages on a phone. Hearing them is easier, and for
anyone whose eyes are going it is the difference between using this and not.

WHICH VOICE
Sarvam's bulbul:v3, because it has character where Google's Hindi is smooth —
and smooth becomes flat when you hear it four times a day for a year. Google
is the fallback for anything Sarvam does not cover.

The speaker follows the relationship she chose at setup: a beta gets a male
voice, a beti a female one. Not a setting she has to find.

HOW IT SPEAKS
Two things, and no model call for either.

    the intent      the composer already knows WHY it is writing. A
                    medication reminder is calm and unhurried; a festival
                    greeting is brighter; a boundary is ordinary.

    her state       the mood read already ran on what she said. A reply on a
                    day she has said her knee hurts is gentle.

A classifier would be the wrong tool: it would read the message to infer
something the thing that WROTE the message already had.

AND RESTRAINT
Three instructions, not a continuous mapping from mood. A companion whose
voice swings about sounds like it is performing, and for someone who will
hear it every day that is worse than flat.
"""
import base64
import os
from typing import Optional

SARVAM_URL = "https://api.sarvam.ai/text-to-speech"
GOOGLE_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

# Sarvam covers these well. Anything else falls through to Google, which has
# more languages and less character — the right trade when the choice is
# between a flat voice and no voice.
SARVAM_LANGS = {"hi-IN", "bn-IN", "ta-IN", "te-IN", "mr-IN", "gu-IN",
                "kn-IN", "ml-IN", "pa-IN", "od-IN", "en-IN"}

# Who she chose at setup, and the voice that follows from it.
_BY_RELATION = {
    "son": "anand", "beta": "anand",
    "daughter": "ritu", "beti": "ritu",
    "friend": "kabir", "dost": "kabir",
    "companion": "roopa", "saathi": "roopa",
    "caretaker": "priya",
}
_DEFAULT_SPEAKER = "ritu"

_GOOGLE_VOICE = {
    "hi-IN": "hi-IN-Neural2-A", "bn-IN": "bn-IN-Wavenet-A",
    "ta-IN": "ta-IN-Wavenet-A", "te-IN": "te-IN-Standard-A",
    "mr-IN": "mr-IN-Wavenet-A", "gu-IN": "gu-IN-Wavenet-A",
    "kn-IN": "kn-IN-Wavenet-A", "ml-IN": "ml-IN-Wavenet-A",
    "pa-IN": "pa-IN-Wavenet-A", "en-IN": "en-IN-Neural2-A",
}

_LANG_FROM_PREF = {
    "hinglish": "hi-IN", "hindi": "hi-IN", "bengali": "bn-IN",
    "tamil": "ta-IN", "telugu": "te-IN", "marathi": "mr-IN",
    "gujarati": "gu-IN", "kannada": "kn-IN", "malayalam": "ml-IN",
    "punjabi": "pa-IN", "english": "en-IN",
}


def tone_for(intent: str = "", valence: float = 0.0) -> Optional[str]:
    """How to say it. None for ordinary messages, which is most of them.

    No model call: the composer knows why it is writing, and the mood read
    already ran on what she said.
    """
    i = (intent or "").lower()

    # Medicine and anything acute, always steady. A hurried voice about a
    # tablet sounds like being chivvied; a calm one sounds like being looked
    # after.
    if i in ("medication", "safety", "emergency"):
        return "say this calmly and steadily, unhurried"

    # A day that has gone badly. Softer, whatever the message is about.
    if valence <= -0.3:
        return "say this gently and slowly, the way you would to someone who is tired"

    if i in ("festival", "greeting") and valence >= 0.5:
        return "say this warmly, with a little brightness"

    return None


def _voice_for(user_id: str) -> tuple:
    """(speaker, language) — from the relationship and language she chose."""
    speaker, lang = _DEFAULT_SPEAKER, "hi-IN"
    try:
        from memory.profile_store import get_user_profile
        p = get_user_profile(user_id) or {}
        pref = str(p.get("language_pref") or "hinglish").lower()
        lang = _LANG_FROM_PREF.get(pref, "hi-IN")

        persona = p.get("persona") or {}
        rel = str(persona.get("relationship")
                  or p.get("companion_relationship") or "").lower()
        if rel in _BY_RELATION:
            speaker = _BY_RELATION[rel]
        elif persona.get("voice_id"):
            # an explicit choice beats the relationship
            v = str(persona["voice_id"]).lower()
            if "male" in v and "female" not in v:
                speaker = "anand"
    except Exception as e:
        print(f"[Voice] profile read failed: {e}")
    return speaker, lang


def _sarvam(text: str, lang: str, speaker: str,
            instruction: Optional[str]) -> Optional[bytes]:
    key = os.getenv("SARVAM_API_KEY")
    if not key or lang not in SARVAM_LANGS:
        return None
    body = {
        "text": text[:1500],
        "target_language_code": lang,
        "speaker": speaker,
        "model": "bulbul:v3",
        "speech_sample_rate": 22050,
        # A shade slower than default. She is seventy, and the difference
        # between following a sentence and re-reading it is mostly pace.
        "pace": 0.95,
    }
    if instruction:
        body["speaker_instruction"] = instruction
    try:
        import requests
        r = requests.post(SARVAM_URL,
                          headers={"api-subscription-key": key},
                          json=body, timeout=20)
        if r.status_code != 200:
            print(f"[Voice] sarvam {r.status_code}: {str(r.text)[:120]}")
            return None
        audios = r.json().get("audios") or []
        return base64.b64decode(audios[0]) if audios else None
    except Exception as e:
        print(f"[Voice] sarvam failed: {e}")
        return None


def _google(text: str, lang: str) -> Optional[bytes]:
    """The fallback. Less character, more languages — and a flat voice beats
    no voice."""
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        return None
    try:
        import requests
        r = requests.post(
            f"{GOOGLE_URL}?key={key}",
            json={"input": {"text": text[:1500]},
                  "voice": {"languageCode": lang,
                            "name": _GOOGLE_VOICE.get(lang,
                                                      "hi-IN-Neural2-A")},
                  "audioConfig": {"audioEncoding": "MP3",
                                  "speakingRate": 0.92}},
            timeout=20)
        if r.status_code != 200:
            print(f"[Voice] google {r.status_code}: {str(r.text)[:120]}")
            return None
        return base64.b64decode(r.json()["audioContent"])
    except Exception as e:
        print(f"[Voice] google failed: {e}")
        return None


def _speakable(text: str, lang: str = "") -> str:
    """The message as it should be heard.

    A map link went to the voice whole — "https colon slash slash www dot
    google dot com" — and so did the heart at the end. Links and pictographs
    are for the eye; the text on screen keeps them.

    But a link taken out silently left her not knowing there was anything to
    tap (17 Oct: a chai place, its map link, and the voice said nothing about
    it). So the voice ends by saying where it is — a map, a video, a link —
    once, in her language.
    """
    import re
    import unicodedata
    t = text or ""
    # [Malnad Chai](https://…) is heard as "Malnad Chai".
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 ", t)
    links = re.findall(r"https?://\S+|www\.\S+", text or "")
    t = re.sub(r"https?://\S+|www\.\S+", " ", t)
    t = re.sub(r"[*_#`>]+", " ", t)          # markdown marks are for the eye
    t = "".join(c for c in t
                if unicodedata.category(c) not in ("So", "Cs", "Co")
                and c not in "\u200d\ufe0f")
    t = re.sub(r"\s+", " ", t).strip()
    if links:
        kind = ("map" if any(("google." in l and "/maps" in l) or "maps.google." in l or "maps.app" in l
                             or "goo.gl/maps" in l for l in links)
                else "video" if any("youtube.com" in l or "youtu.be" in l for l in links)
                else "link")
        english = (lang or "").lower().startswith("en")
        say = {
            ("map", False): "Neeche naksha hai, dabaakar dekh lijiye.",
            ("video", False): "Neeche video hai, dabaakar chala lijiye.",
            ("link", False): "Neeche link hai, dabaakar dekh lijiye.",
            ("map", True): "The map is just below. Tap it to open.",
            ("video", True): "The video is just below. Tap it to play.",
            ("link", True): "The link is just below. Tap it to open.",
        }[(kind, english)]
        t = re.sub(r"\s*[:\-\u2013\u2014]+\s*$", ".", t)   # "…pee sakti hain:" ends the sentence
        if t and t[-1] not in ".!?\u0964":
            t += "."
        t = f"{t} {say}".strip()
    return t


def speak(user_id: str, text: str, intent: str = "",
          valence: float = 0.0) -> Optional[dict]:
    """Audio for one message, or None.

    Returns {audio: bytes, format: wav|mp3, voice: ..., tone: ...}. None when
    both providers fail, and the caller shows the text as it always did —
    voice is an addition, never a dependency.
    """
    speaker, lang = _voice_for(user_id)
    text = _speakable(text, lang)
    if len(text) < 2:
        return None

    instruction = tone_for(intent, valence)

    audio = _sarvam(text, lang, speaker, instruction)
    if audio:
        print(f"[Voice] {user_id}: sarvam/{speaker} {lang} {len(audio)} bytes")
        return {"audio": audio, "format": "wav", "voice": speaker,
                "lang": lang, "tone": instruction or "plain"}

    audio = _google(text, lang)
    if audio:
        print(f"[Voice] {user_id}: google {lang} {len(audio)} bytes (sarvam failed)")
        return {"audio": audio, "format": "mp3", "voice": "google",
                "lang": lang, "tone": "plain"}

    print(f"[Voice] {user_id}: no audio — both providers failed")
    return None


def playback_preference(user_id: str) -> str:
    """auto | tap | off.

    tap by default: audio starting on its own in a room she is not alone in
    is the worse mistake. She can change it, and saying so in conversation
    changes it too — see memory/anchors.
    """
    try:
        from memory.profile_store import get_user_profile
        p = get_user_profile(user_id) or {}
        v = str((p.get("preferences") or {}).get("voice_playback")
                or p.get("voice_playback") or "tap").lower()
        return v if v in ("auto", "tap", "off") else "tap"
    except Exception:
        return "tap"

"""
SCRIPT — putting displayed text into the script the person actually reads.

For someone who reads only Gurmukhi, Latin text is not merely inconsistent, it
is unreadable. And transcription produces mixed scripts within a single
sentence: Whisper renders what it hears, so "Mohammed Rafi aur Chinese food"
comes back with the names in Devanagari and the English words in Latin. On a
form that reads as broken even when the stored data is correct.

The rule this enforces is the one already implicit in label / label_native:
English is the system's language, theirs is the interface's. Cluster labels,
category keys, pillar names and reaction types stay English because they are
matched and joined — Devanagari cluster labels would fragment the resolver in
exactly the way that took days to fix. Anything a person reads goes through
here.

Applied at the display boundary rather than sprinkled through the UI: one call
in the transcribe route, and what comes back is already right.
"""
import os
import json
import urllib.request
from typing import Optional

# Sarvam wants a locale, and the declared preference is a phrase written for a
# prompt — "Punjabi, written in Gurmukhi script, with English words where
# natural" — so it is matched rather than parsed.
_LOCALE = (
    ("punjab",   "pa-IN"),
    ("gujarat",  "gu-IN"),
    ("marathi",  "mr-IN"),
    ("bengal",   "bn-IN"),
    ("tamil",    "ta-IN"),
    ("telugu",   "te-IN"),
    ("kannada",  "kn-IN"),
    ("malayalam", "ml-IN"),
    ("odia",     "od-IN"),
    ("hinglish", "hi-IN"),
    ("hindi",    "hi-IN"),
    ("english",  "en-IN"),
)

# Ranges that tell us text is already in an Indic script, so there is nothing
# to convert and no reason to spend a call.
_INDIC = (
    (0x0900, 0x097F),   # Devanagari — Hindi, Marathi
    (0x0A00, 0x0A7F),   # Gurmukhi
    (0x0A80, 0x0AFF),   # Gujarati
    (0x0980, 0x09FF),   # Bengali
    (0x0B00, 0x0B7F),   # Odia
    (0x0B80, 0x0BFF),   # Tamil
    (0x0C00, 0x0C7F),   # Telugu
    (0x0C80, 0x0CFF),   # Kannada
    (0x0D00, 0x0D7F),   # Malayalam
)


def locale_for(pref: Optional[str]) -> Optional[str]:
    p = (pref or "").lower()
    for needle, code in _LOCALE:
        if needle in p:
            return code
    return None


def _script_share(text: str) -> float:
    """How much of this is already in an Indic script."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 1.0
    indic = sum(1 for c in letters
                if any(lo <= ord(c) <= hi for lo, hi in _INDIC))
    return indic / len(letters)


def to_script(text: str, pref: Optional[str], threshold: float = 0.8) -> str:
    """
    Render text in the script this person reads.

    Returns the input unchanged when there is nothing to do: no preference, an
    English preference, empty text, or text already mostly in an Indic script.
    That last check matters — transliterating Devanagari to Devanagari is a
    wasted round-trip on every transcription, and this runs while someone waits.

    Never raises. Text in the wrong script is a bad experience; no text at all
    is a broken one.
    """
    text = (text or "").strip()
    if not text:
        return text

    target = locale_for(pref)
    if not target or target == "en-IN":
        return text

    if _script_share(text) >= threshold:
        return text

    key = os.getenv("SARVAM_API_KEY")
    if not key:
        return text

    try:
        body = json.dumps({
            "input": text,
            "source_language_code": "en-IN",
            "target_language_code": target,
            "speaker_gender": "Female",
        }).encode()
        req = urllib.request.Request(
            "https://api.sarvam.ai/transliterate", data=body,
            headers={"api-subscription-key": key,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.loads(r.read()).get("transliterated_text")
        return out or text
    except Exception as e:
        print(f"[Script] transliterate failed ({target}): {e}")
        return text

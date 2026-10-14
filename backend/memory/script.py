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


# ── Her own script ────────────────────────────────────────────────────────────
#
# The language she chose does not say how she WRITES it. A Hinglish speaker
# types Roman letters; a Punjabi speaker may type Gurmukhi, or Roman, or both;
# a Tamil speaker often types Tanglish. Whisper writes whatever it hears in
# whatever script it guesses, so spoken and typed messages came out in two
# scripts — "Abhi sardi theek hai" typed, "बस अभी निकल रही हूँ" spoken — and
# anything that compared words ("ककड़ी" against "kakdi" on her list) missed.
#
# A rule per language would be wrong for half of every language. So the script
# follows her: whatever most of her own typed messages are written in, spoken
# ones are put into too. Nothing reads the words — only which alphabet the
# letters come from.

_BLOCKS = (
    ("devanagari", 0x0900, 0x097F, "hi-IN"),
    ("bengali",    0x0980, 0x09FF, "bn-IN"),
    ("gurmukhi",   0x0A00, 0x0A7F, "pa-IN"),
    ("gujarati",   0x0A80, 0x0AFF, "gu-IN"),
    ("odia",       0x0B00, 0x0B7F, "od-IN"),
    ("tamil",      0x0B80, 0x0BFF, "ta-IN"),
    ("telugu",     0x0C00, 0x0C7F, "te-IN"),
    ("kannada",    0x0C80, 0x0CFF, "kn-IN"),
    ("malayalam",  0x0D00, 0x0D7F, "ml-IN"),
)
_LOCALE_OF = {name: loc for name, _, _, loc in _BLOCKS}
_LOCALE_OF["latin"] = "en-IN"
_WRITES_IN_CACHE = {}


def script_of(text: str) -> str:
    """Which alphabet most of the letters are in: latin, devanagari, ... or ''."""
    counts = {}
    for c in text or "":
        if not c.isalpha():
            continue
        o = ord(c)
        if o < 0x250:
            name = "latin"
        else:
            name = next((n for n, lo, hi, _ in _BLOCKS if lo <= o <= hi), "other")
        counts[name] = counts.get(name, 0) + 1
    return max(counts, key=counts.get) if counts else ""


def writes_in(user_id: str) -> str:
    """The script of most of her recent messages. '' when there are too few
    to tell. Remembered for an hour."""
    import time
    hit = _WRITES_IN_CACHE.get(user_id)
    if hit and time.time() - hit[1] < 3600:
        return hit[0]
    found = ""
    try:
        from supabase_store import get_client
        db = get_client()
        sess = [r["id"] for r in (db.table("sessions").select("id")
                .eq("user_id", user_id).order("updated_at", desc=True)
                .limit(10).execute()).data or []]
        rows = (db.table("messages").select("content")
                .in_("session_id", sess).eq("role", "user")
                .order("timestamp", desc=True).limit(40)
                .execute()).data or [] if sess else []
        tally = {}
        for r in rows:
            s = script_of(str(r.get("content") or ""))
            if s and s != "other":
                tally[s] = tally.get(s, 0) + 1
        if sum(tally.values()) >= 3:
            found = max(tally, key=tally.get)
    except Exception as e:
        print(f"[Script] writes-in read failed: {e}")
    _WRITES_IN_CACHE[user_id] = (found, time.time())
    return found


def _transliterate(text: str, source: str, target: str) -> str:
    key = os.getenv("SARVAM_API_KEY")
    if not key or source == target:
        return text
    try:
        body = json.dumps({"input": text, "source_language_code": source,
                           "target_language_code": target}).encode()
        req = urllib.request.Request(
            "https://api.sarvam.ai/transliterate", data=body,
            headers={"api-subscription-key": key,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.loads(r.read()).get("transliterated_text")
        return (out or text).strip()
    except Exception as e:
        print(f"[Script] transliterate {source}->{target} failed: {e}")
        return text


def to_her_script(user_id: str, text: str, pref: Optional[str] = None) -> str:
    """A transcript, written the way she writes. Unchanged when it already is,
    when she has written too little to tell and her language says nothing,
    or when conversion fails."""
    text = (text or "").strip()
    src = script_of(text)
    if not text or not src or src == "other":
        return text

    target = writes_in(user_id)
    if not target:
        # Too few messages of her own yet: her chosen language decides.
        p = (pref or "").lower()
        if "hinglish" in p or "english" in p:
            target = "latin"
        else:
            loc = locale_for(pref)
            target = next((n for n, _, _, l in _BLOCKS if l == loc), "")
    if not target or target == src:
        return text

    # Devanagari is Hindi or Marathi; her language says which.
    pref_loc = locale_for(pref) or ""
    def loc(name):
        if name == "devanagari" and pref_loc == "mr-IN":
            return "mr-IN"
        return _LOCALE_OF.get(name, "")
    s_loc, t_loc = loc(src), loc(target)
    if not s_loc or not t_loc:
        return text
    out = _transliterate(text, s_loc, t_loc)
    if out != text:
        print(f"[Script] {src}->{target}: {text[:40]!r} -> {out[:40]!r}")
    return out

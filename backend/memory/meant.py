"""
MEANT — what she meant to write, for understanding only.

She types Hinglish on a keyboard that "corrects" it into English, or speaks
and a transcriber guesses: "tarbuz" arrived as "carbon", "phool" as "pool",
"Haan dhyan hai" as "Haan Dhyanesh hai". Everything downstream read those
words as written — a list with carbon on it, a new person called Dhyanesh,
an offer credited with a yes meant for a phone call.

So each message is read once by the model, with what the companion last
said and what is on her open lists, and returned as she meant it: the same
language, the same words, only the garbled ones put right. Her original is
what is saved and shown; this is what is understood.

Never raises. When the model cannot be reached, or changes more than a
correction would, the original is used — misreading a word is better than
putting words in her mouth.
"""
from typing import Tuple


def _last_said(user_id: str) -> str:
    try:
        from supabase_store import get_client
        db = get_client()
        sess = (db.table("sessions").select("id").eq("user_id", user_id)
                .order("updated_at", desc=True).limit(1).execute()).data or []
        if not sess:
            return ""
        rows = (db.table("messages").select("content")
                .eq("session_id", sess[0]["id"]).eq("role", "assistant")
                .order("timestamp", desc=True).limit(1).execute()).data or []
        return str(rows[0].get("content") or "")[:400] if rows else ""
    except Exception as e:
        print(f"[Meant] last-said read failed: {e}")
        return ""


def _on_lists(user_id: str) -> str:
    try:
        from memory.lists import _active, _items_of, _what
        out = []
        for l in _active(user_id)[:3]:
            ws = [_what(r) for r in _items_of(l["id"], include_done=False)][:12]
            if ws:
                out.append(f"{l.get('name')}: {', '.join(ws)}")
        return "; ".join(out)
    except Exception:
        return ""


def what_she_meant(user_id: str, text: str) -> Tuple[str, bool]:
    """(the message as she meant it, whether anything was changed)."""
    t = (text or "").strip()
    if not t:
        return text, False
    said = _last_said(user_id)
    lists = _on_lists(user_id)
    try:
        from llm import ask
        got = (ask(f"""An elderly person typed or spoke this message to their companion.
Phone keyboards "correct" their words into wrong English ones, and voice
transcription mishears them, so a word may not be what they meant.

The companion had just said: "{said or '(nothing yet)'}"
{('Their open lists: ' + lists) if lists else ''}

Their message: "{t}"

Write the message exactly as they MEANT it: same language, same script,
same words, same order — fix only words that are clearly misspelt, wrongly
autocorrected or misheard, using what the companion said as the guide.
Do not translate, rephrase, add, remove or answer anything. If nothing is
wrong, write it back unchanged.

Write only the message.""", max_tokens=200) or "").strip().strip('"').strip()
    except Exception as e:
        print(f"[Meant] model failed: {e}")
        return text, False

    if not got or got == t:
        return text, False
    # A correction changes a few words, not the message. Anything that grew
    # or shrank a lot is a rewrite, and a rewrite is not hers.
    a, b = t.split(), got.split()
    if abs(len(a) - len(b)) > max(2, len(a) // 3):
        print(f"[Meant] rejected rewrite: {t[:60]!r} -> {got[:60]!r}")
        return text, False
    print(f"[Meant] {t[:60]!r} -> {got[:60]!r}")
    return got, True

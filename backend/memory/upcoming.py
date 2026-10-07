"""
WHAT SHE IS ABOUT TO DO.

Her puja is at 06:30. A bhajan at 06:25 is useful; Kishore Kumar at 06:25 is
not. Lunch at 13:00 means a recipe at 12:40 lands and at 14:00 does not. Her
walk at 17:30 takes music well and her BP tablet takes nothing at all.

The offer has been drawn from a weighted list of her interests, which is how
she came to be offered the same singer three mornings running. Her day already
knows better.

WHY NOT A TABLE
bhakti → before puja works for her and fails for someone whose routine is
Quran reading after Fajr, or a gurudwara on Sunday, or physiotherapy on
Tuesdays. The label is in her own words and the model reads it; a mapping
written here would only ever fit the person it was written for.

The kind's one job is excluding medication. Everything else is the label.

THREE STATES, AND ONLY ONE OF THEM OFFERS
    she has not mentioned it        offer something that goes with it
    she has said what she is doing  nothing — she has handled it
    she has said she is not         nothing, and certainly not a suggestion
                                    for the thing she just declined

The third is the one that stings. "Aaj walk nahi karungi, ghutna dukh raha
hai" is recorded as denied by note_from_message, and until now nothing read
it: an hour later she was offered music for the walk.

BEFORE, NOT AFTER
An offer is useful ahead of the thing. Afterwards is a boundary's job —
"sair kaisi rahi?" — and that already exists.
"""
from datetime import date
from typing import Dict, Optional

# How far ahead to look. Long enough to be useful, short enough that it is
# about the next thing rather than the rest of the day.
AHEAD_MIN = 25

# A tablet takes no offer. Everything else is decided by its label.
NEVER = ("medication",)

# What has already been generated for an event, so the same lunch is not
# asked about twice in one day.
_FOR_EVENT: dict = {}


def _db():
    from supabase_store import get_client
    return get_client()


def next_event(user_id: str) -> Optional[Dict]:
    """The next thing on her day worth offering something for, or None.

    None is the common answer: most of the day is not within half an hour of
    anything.
    """
    try:
        from memory.day import events, _mins, _mins_now
        now = _mins_now(user_id)
    except Exception as e:
        print(f"[Upcoming] clock failed: {e}")
        return None

    best = None
    for e in events(user_id) or []:
        if (e.get("kind") or "") in NEVER:
            continue
        # She has said what she is doing, or that she is not. Either way it
        # is handled, and a suggestion now is either redundant or tin-eared.
        if e.get("status") in ("confirmed", "denied"):
            continue
        due = _mins(e.get("due_at"))
        if due < 0:
            continue
        ahead = due - now
        if 0 <= ahead <= AHEAD_MIN:
            if best is None or ahead < best[0]:
                best = (ahead, e)
    if not best:
        return None

    ahead, e = best
    return {
        "id": e.get("id"),
        "label": e.get("label") or e.get("kind") or "",
        "kind": e.get("kind") or "",
        "due_at": str(e.get("due_at") or "")[:5],
        "minutes": ahead,
    }


def goes_with(user_id: str, label: str, likes: list) -> str:
    """Something she likes that belongs with this, or "".

    Empty is a perfectly good answer. Her crossword and her morning puja have
    no connection, and inventing one is worse than saying nothing.
    """
    if not label or not likes:
        return ""

    listing = "\n".join(f"- {l}" for l in likes[:20])
    prompt = f"""An elderly woman in India is about to do this, in a few
minutes:

  {label}

These are things she enjoys:
{listing}

Which ONE of them belongs with what she is about to do? Reply with that line
exactly as written above, or the single word NONE.

Belongs means a person would naturally put them together. Bhajan with puja.
A song with a walk. A dish with a meal she has not decided on yet.

NONE is the usual answer, and the right one whenever the pairing would only
be a pretext. A crossword does not go with morning puja. A film does not go
with taking a tablet. Most things do not go with most things.

Do not stretch. One line, nothing else."""

    try:
        from llm import ask
        got = (ask(prompt, max_tokens=40) or "").strip().strip('"').lstrip("- ")
    except Exception as e:
        print(f"[Upcoming] pairing failed: {e}")
        return ""

    if not got or got.upper().startswith("NONE"):
        return ""
    for l in likes:
        if l.lower() == got.lower():
            return l
    return ""


def hint(user_id: str) -> str:
    """One line for the composer, or "".

    Returns "" most of the time, which is correct: she is near something
    offerable for perhaps an hour of her day, and only some of those things
    pair with anything.
    """
    ev = next_event(user_id)
    if not ev:
        return ""

    key = (user_id, date.today().isoformat(), str(ev.get("id")))
    if key in _FOR_EVENT:
        return ""

    try:
        from memory.interests_view import computed_interests
        cats = computed_interests(user_id) or {}
        likes = []
        for _c, items in cats.items():
            likes += [str(i) for i in (items if isinstance(items, list)
                                       else [items]) if i]
    except Exception as e:
        print(f"[Upcoming] interests failed: {e}")
        return ""

    thing = goes_with(user_id, ev["label"], likes)
    _FOR_EVENT[key] = thing
    if not thing:
        return ""

    print(f"[Upcoming] {user_id}: {ev['label']} at {ev['due_at']} -> {thing}")
    return (f"\n\nIn about {ev['minutes']} minutes: {ev['label']}. "
            f"{thing} would go with it — offer that, lightly, as something "
            f"to have alongside. Not as a reason to do the thing: she knows "
            f"her own day. One line.")

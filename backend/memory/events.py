"""
EVENTS — what happened, and when.

Interests answer "what does she like". Events answer "kab aaya tha Arjun", and
nothing in the system could answer that until now.

TWO DATES, AND THEY DIFFER
"Kal beta aaya tha" said on the 12th means the visit was the 11th. Queries want
the day it happened; provenance wants the day she said it. Both are kept, and
conflating them is how a system ends up believing her son visited today.

WHAT IS AN EVENT
Something that happened at a point in time. A visit, a festival, an
appointment, a fall, a birthday that has just passed. Not "she likes Kishore
Kumar" — that has no date and belongs in interests.

The distinction is the date. If you cannot say when, it is not an event.

WHY A SEPARATE STORE
Interests decay: a taste she has not mentioned in a year is probably gone.
Events do not. A grandson's birth is as true a decade later, and forgetting it
is the failure this product exists to prevent.
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict


def _db():
    from supabase_store import get_client
    return get_client()


# Relative days, in the languages she might use. The model resolves the rest;
# these are the ones common enough to be worth catching without a call.
_RELATIVE = {
    "kal": -1, "yesterday": -1, "kaal": -1, "ਕੱਲ੍ਹ": -1, "काल": -1,
    "parso": -2, "parsoon": -2, "परसों": -2,
    "aaj": 0, "today": 0, "आज": 0,
}


def _resolve_when(text: str, said_on: datetime) -> Optional[str]:
    """The day it happened, from the way she referred to it.

    "Kal" is the trap: in Hindi it means both yesterday and tomorrow, and only
    the verb tense separates them. A past-tense sentence with "kal" is
    yesterday; this returns None for anything it cannot settle, and the model
    handles those.
    """
    low = (text or "").lower()
    for word, delta in _RELATIVE.items():
        if re.search(rf"\b{re.escape(word)}\b", low):
            # Future tense with "kal" means tomorrow, which is not an event
            # yet. Crude, and the model call is the safety net.
            if delta < 0 and re.search(r"\b(jaungi|jaunga|karungi|karunga|"
                                       r"will|going to)\b", low):
                return None
            return (said_on + timedelta(days=delta)).date().isoformat()
    return None


# Judged once per label and remembered. "Lunch" comes up every day and is
# the same answer every time.
_WORTH: dict = {}

# Not a list of what to skip — a list would hold the words someone thought
# of. These are only the ones seen so often that a model call for them is
# waste.
_NEVER = {"lunch", "dinner", "breakfast", "nashta", "khana", "meal",
          "light meal", "snack", "chai", "tea"}


def worth_keeping(what: str, text: str = "") -> bool:
    """Would anyone recall this next week?

    The day chain records an event every time she confirms a meal, so
    "lunch acha raha" became a cluster called Lunch, and six of the eight
    clusters made in two days were Lunch, Light Meal, breakfast and Aloo
    parathe twice. None of them is a thing that happened; they are the
    ordinary furniture of a day.

    The gate is here rather than in the caller because the caller is not
    the only caller, and the next one will not know to check.
    """
    label = (what or "").strip()
    if not label:
        return False

    low = label.lower()
    # "ate Lunch acha raha" — the day chain prefixes what she said.
    for lead in ("ate ", "had ", "khaya ", "kha liya "):
        if low.startswith(lead):
            low = low[len(lead):].strip()
            break

    if low in _NEVER:
        print(f"[Events] not keeping {label!r} — a meal is not an event")
        return False

    if low in _WORTH:
        return _WORTH[low]

    prompt = f"""An elderly woman in India said this:

"{(text or label)[:300]}"

Which was recorded as: "{label[:80]}"

Would anyone recall it NEXT WEEK? Answer yes or no, one word.

yes — it has a tomorrow. A trip out, a visitor, a doctor, something that
      went wrong, something she did for the first time, a festival
      preparation. Things she would tell someone about.

no  — the ordinary furniture of a day. She ate lunch; that is what lunch
      is. She drank tea. She rested. Answering "lunch kaisa raha?" with
      "acha raha" is a reply to a question, not an event.

The test is not whether it was pleasant or whether it mattered to her
then. It is whether, on Friday, it is a thing that happened.

One word."""

    try:
        from llm import ask
        a = (ask(prompt, max_tokens=6) or "").strip().lower()
        keep = a.startswith("y")
    except Exception as e:
        # A failed read keeps it. Losing something that happened is worse
        # than a cluster nobody reads.
        print(f"[Events] worth-keeping read failed for {label!r}: {e}")
        return True

    _WORTH[low] = keep
    if not keep:
        print(f"[Events] not keeping {label!r} — finished when it happened")
    return keep


def record_event(user_id: str, what: str, said_on: datetime = None,
                 text: str = "", kind: str = "", people: List[str] = None,
                 feeling: str = "", happened_on: str = None) -> Optional[str]:
    """Store something that happened. Returns the row id.

    happened_on is resolved from the phrasing when not given — "kal beta aaya
    tha" on the 12th records the 11th.
    """
    said_on = said_on or datetime.now(timezone.utc)

    # Here, not in the caller — the caller is not the only caller, and the
    # next one will not know to check.
    if not worth_keeping(what, text):
        return None

    when = happened_on or _resolve_when(text or what, said_on) \
        or said_on.date().isoformat()

    row = {
        "user_id":     user_id,
        # Short. "Cooked chicken curry and rice at home" is a sentence, and
        # the sentence already lives in the day's note — an event is a thing
        # with a date on it, for finding later.
        "label":       (what or "").strip()[:60],
        "kind":        "event",
        "happened_on": when,
        "pillar":      "GENERAL",
        "strength":    1.0,
        "status":      "active",
        "attributes":  {
            "said_on": said_on.date().isoformat(),
            "event_kind": kind or "",
            "people": people or [],
            "feeling": feeling or "",
            "said": (text or "")[:300],
        },
    }
    try:
        from classifier.pillar_classifier import embed_text
        v = embed_text(what)
        if v:
            row["centroid"] = v
    except Exception as e:
        print(f"[Events] embed failed: {e}")

    try:
        r = _db().table("interest_clusters").insert(row).execute()
        rid = (r.data or [{}])[0].get("id")
        print(f"[Events] {user_id}: {row['label']!r} on {when}")
        return rid
    except Exception as e:
        print(f"[Events] write failed: {e}")
        return None


def find_events(user_id: str, query: str, limit: int = 5) -> List[Dict]:
    """Events matching a question, most recent first.

    Searches by meaning rather than keyword, so "kab aaya tha Arjun" finds a
    visit recorded as "beta Arjun aaya tha" without sharing a word order.
    """
    try:
        rows = (_db().table("interest_clusters").select("*")
                .eq("user_id", user_id).eq("kind", "event")
                .order("happened_on", desc=True).limit(80).execute()).data or []
    except Exception as e:
        print(f"[Events] read failed: {e}")
        return []
    if not rows:
        return []

    try:
        from classifier.pillar_classifier import embed_text, cosine_similarity
        qv = embed_text(query)
    except Exception:
        qv = None

    if not qv:
        # No embedding: fall back to substring, which is better than nothing.
        low = (query or "").lower()
        return [r for r in rows
                if any(w in str(r.get("label", "")).lower()
                       for w in low.split() if len(w) > 3)][:limit]

    scored = []
    for r in rows:
        cen = r.get("centroid")
        if isinstance(cen, str):
            try:
                cen = json.loads(cen)
            except Exception:
                cen = None
        if not cen:
            continue
        s = cosine_similarity(qv, cen)
        if s >= 0.55:
            scored.append((s, r))

    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:limit]]


def extract_events(user_id: str, messages: List[dict],
                   said_on: datetime = None) -> List[str]:
    """Find what happened in a conversation. Returns the ids written.

    Deliberately strict. A plan is not an event, someone else's day is not her
    event, and a thing she does every week is a routine rather than a moment.
    The same three conditions the day-chain confirmation needed, for the same
    reason: mentioning something is not the same as it having happened.
    """
    said_on = said_on or datetime.now(timezone.utc)
    hers = "\n".join(m.get("content", "")[:300] for m in messages
                     if m.get("role") == "user")
    if len(hers.strip()) < 15:
        return []

    today = said_on.date().isoformat()
    prompt = f"""Today is {today}. Someone wrote:

{hers}

Did anything HAPPEN? Return JSON only:
{{"events": [{{"what": "...", "happened_on": "YYYY-MM-DD",
               "kind": "visit|festival|medical|milestone|loss|outing",
               "people": ["..."], "feeling": "..."}}]}}

An event is a moment with a date. A visit, a festival they observed, an
appointment they went to, a fall, news that arrived.

"what" is SHORT — three or four words, the thing itself. "Chicken curry", not
"cooked chicken curry and rice at home"; "Delhi trip", not "went to Delhi for
a few days with Shubham". The sentence already lives in the day's note; this
is a label with a date on it, for finding later.

Use the same words for the same thing. "Delhi trip" twice, not "Delhi trip"
and "Delhi Trip" and "trip to Delhi" — they become separate entries and the
same journey is recorded three times.

NOT an event:
- a plan. "Shaam ko mandir jaungi" has not happened.
- something someone else did. "Padosan gir gayi" is the neighbour's day.
- a standing fact. "Mera beta Delhi mein hai" is true every day and belongs
  elsewhere.
- a habit. "Roz sair karti hoon" is a routine, not a moment.

Dates: work them out from today. "Kal" in a past-tense sentence is yesterday;
in a future one it is tomorrow and therefore not an event. "Pichle hafte" is
about seven days back — give your best date rather than refusing.

Empty list if nothing happened. That is the common answer."""

    try:
        from llm import ask
        raw = ask(prompt, max_tokens=600).replace("```json", "").replace("```", "")
        found = json.loads(raw.strip()).get("events") or []
    except Exception as e:
        print(f"[Events] extraction failed: {e}")
        return []

    ids = []
    for e in found:
        what = (e.get("what") or "").strip()
        if not what:
            continue
        rid = record_event(
            user_id, what, said_on=said_on, text=hers,
            kind=e.get("kind") or "", people=e.get("people") or [],
            feeling=e.get("feeling") or "",
            happened_on=e.get("happened_on") or None)
        if rid:
            ids.append(rid)
    return ids

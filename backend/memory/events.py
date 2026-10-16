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


def _their_time(user_id: str, said_on: datetime = None) -> datetime:
    """When they said it, on THEIR clock.

    The date of an event is the date in their life. Defaulting to UTC put
    anything said in India between midnight and half past five on the
    previous day: "Nashta kar liya" at 00:30 on the 11th was filed on the
    10th. A UTC time passed in is converted; a naive one is left alone,
    since there is no way to know what clock it was read from.
    """
    try:
        from zoneinfo import ZoneInfo
        from memory.time_context import get_user_timezone
        tz = ZoneInfo(get_user_timezone(user_id))
    except Exception as e:
        print(f"[Events] timezone read failed, using UTC: {e}")
        tz = timezone.utc
    if said_on is None:
        return datetime.now(tz)
    if said_on.tzinfo is not None:
        return said_on.astimezone(tz)
    return said_on


# Which day something happened is the model's to work out (extract_events
# gives it "today" and asks for the date). There was a table of "kal",
# "parso", "aaj" here, with a regex for future tense — a word list that knew
# three languages and guessed at tense. A caller with no date is filed on
# the day it was said.


# Judged once per label and remembered. "Lunch" comes up every day and is
# the same answer every time.
_WORTH: dict = {}

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


_ABOUT_KIND = {"person": "person", "place": "place", "activity": "interest",
               "health": "concern"}


def _parent_for(user_id: str, about: str, about_kind: str) -> Optional[str]:
    """The concept this event hangs under — the person, place or activity it
    happened to or at — made if she has none. Found with the one same-thing
    check (concepts.same_as), so "Zoo", "chidiyaghar" and "the zoo" are one
    parent and five visits are five children of it."""
    about = (about or "").strip()
    if not about:
        return None
    k = _ABOUT_KIND.get((about_kind or "").strip().lower(), "")
    if k == "concern":
        return None              # health goes to episodes, not events
    try:
        from memory.concepts import same_as, remember, english
        hit = same_as(user_id, about, kind=k)
        if hit:
            return hit["id"]
        label = about[:1].upper() + about[1:]
        row = {"user_id": user_id, "label": label[:80], "kind": k or "place",
               "pillar": "FAMILY" if k == "person" else "GENERAL",
               "status": "active", "strength": 0.5, "event_count": 0,
               "attributes": {"kind": k or "place", "source": "event",
                              "english": english(label, k or "place")}}
        try:
            v = __import__("classifier.pillar_classifier", fromlist=["embed_text"]).embed_text(label)
            if v:
                row["centroid"] = v
        except Exception:
            pass
        try:
            cid = _db().table("interest_clusters").insert(row).execute().data[0]["id"]
        except Exception:
            got = (_db().table("interest_clusters").select("id")
                   .eq("user_id", user_id).eq("label", row["label"])
                   .limit(1).execute()).data
            cid = got[0]["id"] if got else None
        if cid:
            remember(user_id, about, cid)
            print(f"[Events] new concept {label!r} ({row['kind']}) for what happened")
        return cid
    except Exception as e:
        print(f"[Events] parent lookup failed: {e}")
        return None


def _again(user_id: str, r: Dict, said_on: datetime) -> str:
    """The same event told again: one more telling on the row it already has."""
    a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
    said = list(a.get("said_on_all") or [])
    if not said and a.get("said_on"):
        said = [a["said_on"]]
    if said_on.date().isoformat() not in said:
        said.append(said_on.date().isoformat())
    a["said_on_all"] = said
    try:
        _db().table("interest_clusters").update({
            "event_count": (r.get("event_count") or 0) + 1,
            "attributes": a}).eq("id", r["id"]).execute()
    except Exception as e:
        print(f"[Events] same-event update failed: {e}")
    return r["id"]


def _same_occurrence(user_id: str, r: Dict, label: str, when: str, heard: str = "") -> bool:
    """Is this telling the occasion already recorded in r, or a new one?

    The rule was "the same place within three days is the same visit". It
    kept a visit told twice as one — and folded real visits together: the
    mandir on Monday, Wednesday and Friday was one visit, and for somewhere
    she goes every other day it stayed one visit for good, each new one
    being within three days of the last.

    Now: the same day is the same occasion; more than three days apart is a
    new one; between, the model reads both tellings — a visit told again
    ("parso jo zoo gaye the") or one trip over several days (the Delhi trip's
    sightseeing) is the same occasion, a second trip to the mandir is not.
    If it cannot be asked, the old answer (same) stands: a missed visit costs
    less than one counted twice.
    """
    g = _gap(r.get("happened_on"), when)
    if g is None or g > 3:
        return False
    if g == 0:
        return True
    a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
    before = str(a.get("said") or r.get("label") or "")[:200]
    try:
        from memory.judge import yes_no
        return yes_no(
            f"An elderly woman told her companion about things that happened.\n"
            f'Earlier: "{before}" — recorded as "{r.get("label")}", on {str(r.get("happened_on"))[:10]}.\n'
            f'Now: "{(heard or label)[:200]}" — "{label}", on {when}.\n'
            f"Is the new one the SAME occasion as the earlier one — the same visit "
            f"told again, or one trip lasting several days — rather than a "
            f"separate, new time she went or it happened?",
            key=f"ev_same:{r.get('id')}:{when}:{label.lower()}")
    except Exception as e:
        print(f"[Events] same-occasion check failed, kept as one: {e}")
        return True


def _gap(a, when: str) -> Optional[int]:
    try:
        return abs((datetime.fromisoformat(str(a)[:10]).date()
                    - datetime.fromisoformat(when).date()).days)
    except Exception:
        return None


def record_event(user_id: str, what: str, said_on: datetime = None,
                 text: str = "", kind: str = "", people: List[str] = None,
                 feeling: str = "", happened_on: str = None,
                 about: str = "", about_kind: str = "",
                 heard: str = "") -> Optional[str]:
    """Store something that happened. Returns the row id.

    happened_on is resolved from the phrasing when not given — "kal beta aaya
    tha" on the 12th records the 11th.
    """
    said_on = _their_time(user_id, said_on)

    # Here, not in the caller — the caller is not the only caller, and the
    # next one will not know to check.
    if not worth_keeping(what, text):
        return None

    when = happened_on or said_on.date().isoformat()

    label = (what or "").strip()[:60]

    # What it happened to or at: the parent concept (lineage). Five zoo
    # visits are five children of "Zoo"; Arjun's visits hang under Arjun.
    parent = _parent_for(user_id, about, about_kind)

    # The same event told again is the same event: same parent, within three
    # days. Matched by concept, not by name — "zoo gaye the" and "Zoo trip"
    # are one visit.
    if parent:
        try:
            sibs = (_db().table("interest_clusters")
                    .select("id,label,happened_on,event_count,status,attributes")
                    .eq("user_id", user_id).eq("parent_id", parent)
                    .eq("kind", "event").execute()).data or []
        except Exception as e:
            print(f"[Events] sibling read failed: {e}")
            sibs = []
        for r in sibs:
            if (r.get("status") or "active") in ("merged", "archived", "dropped"):
                continue
            if _same_occurrence(user_id, r, label, when, heard):
                print(f"[Events] {label!r} on {when} is {r.get('label')!r} again")
                return _again(user_id, r, said_on)

    # The table allows one row per name. Without a parent, the same name
    # within three days is the same event; otherwise a later one gets its
    # date in the name — and if THAT name is taken, it is that event again
    # (a second mention of "Delhi trip · 01-Nov-26" used to fail on the key
    # and be lost).
    try:
        named = (_db().table("interest_clusters")
                 .select("id,label,happened_on,event_count,status,attributes,parent_id")
                 .eq("user_id", user_id).ilike("label", label.replace("%", "").replace("_", "\\_"))
                 .limit(5).execute()).data or []
    except Exception as e:
        print(f"[Events] lookup failed: {e}")
        named = []
    if not parent:
        for r in named:
            if (r.get("status") or "active") == "merged":
                try:
                    from memory.concepts import follow
                    r = follow(r) or r
                except Exception:
                    continue
            if _same_occurrence(user_id, r, label, when, heard):
                print(f"[Events] {label!r} on {when} is {r.get('label')!r} again")
                return _again(user_id, r, said_on)
    if named:
        dated = f"{label[:44]} · {datetime.fromisoformat(when).strftime('%d-%b-%y')}"
        try:
            taken = (_db().table("interest_clusters")
                     .select("id,label,happened_on,event_count,status,attributes")
                     .eq("user_id", user_id).eq("label", dated).limit(1).execute()).data
        except Exception:
            taken = None
        if taken:
            return _again(user_id, taken[0], said_on)
        label = dated

    row = {
        "user_id":     user_id,
        # Short. "Cooked chicken curry and rice at home" is a sentence, and
        # the sentence already lives in the day's note — an event is a thing
        # with a date on it, for finding later.
        "label":       label,
        "kind":        "event",
        "event_count": 1,
        "happened_on": when,
        "pillar":      "GENERAL",
        "strength":    1.0,
        "status":      "active",
        **({"parent_id": parent} if parent else {}),
        "attributes":  {
            "about": about or "",
            "said_on": said_on.date().isoformat(),
            "event_kind": kind or "",
            "people": people or [],
            "feeling": feeling or "",
            # Her words, so a later telling can be compared with this one.
            "said": (heard or text or "")[:300],
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
                # Not merged or archived ones: a merged "Delhi trip" is the
                # same trip as "Delhi Trip" and was recalled twice.
                .or_("status.is.null,status.eq.active")
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
    said_on = _their_time(user_id, said_on)
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
               "about": "...", "about_kind": "person|place|activity|health",
               "people": ["..."], "feeling": "..."}}]}}

"about" is the ONE thing it happened to or at, by its short plain name —
what she would later ask "kab ... tha?" about: the person who visited
("Arjun"), the place she went ("Zoo", "Delhi"), the activity ("Carrom").
A trip's sightseeing and outings are about the trip's place.

An event is a moment with a date. A visit, a festival they observed, an
appointment they went to, a fall, news that arrived.

"what" is SHORT — three or four words, the thing itself. "Arjun's visit", not
"Arjun came over with the children on Sunday"; "Delhi trip", not "went to Delhi for
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
- the ordinary run of a day: what she cooked or ate, her puja, a nap, a
  walk, the chores. Those live in the day's note. A meal is an event only
  when the meal is the occasion — a birthday dinner, a feast for guests.

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
            # Judged on itself. Given the whole conversation, "Chicken curry"
            # was worth keeping because the same chat held a trip to Delhi.
            user_id, what, said_on=said_on, text=what,
            kind=e.get("kind") or "", people=e.get("people") or [],
            feeling=e.get("feeling") or "",
            happened_on=e.get("happened_on") or None,
            about=str(e.get("about") or "").strip()[:60],
            about_kind=str(e.get("about_kind") or ""),
            heard=hers[:300])
        if rid:
            ids.append(rid)
    return ids

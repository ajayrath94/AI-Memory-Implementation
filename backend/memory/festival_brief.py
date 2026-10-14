"""
WHAT A FESTIVAL ACTUALLY INVOLVES — worked out once, kept forever.

The calendar holds start dates and a fasting flag. "First Day of Sharad
Navratri" on the 11th, then nothing until Dussehra on the 20th — so on the
second day of a nine-day festival the system believed there was no festival
at all, and a woman fasting all nine would be offered chicken on eight of
them.

And on the first day it said more than it knew: she was told aloo parathe
were "ekdum sahi choice" for Navratri. Wheat. To someone who has kept the
fast for fifty years.

So: one call per festival, asking everything that turns out to matter, cached
in a table because Navratri will not change.

    days         nine, not one
    fasts        and what the fast actually avoids
    eaten        what is eaten INSTEAD — so an offer during it is right
                 rather than absent. Kuttu, sabudana, fruit.
    observance   a gathering or a quiet thing
    kept_by      which communities, so it is not assumed of everyone
    asked        the one question worth putting to her

WHY A MODEL CALL AND NOT A TABLE
A table holds the festivals someone thought of. This has to work for Chhath,
Paryushan, Pongal, Onam, Bihu, Losar, Eid al-Adha and whatever a user keeps
that nobody here has heard of. The model knows them; a dict of nine would be
wrong for the tenth person.

WHAT IT IS FOR
Everything downstream reads one row. The diet filter knows what to avoid and
what to suggest instead. The greeting knows whether to wish her or ask after
her fast. The carry knows nine days are coming.
"""
import json
from typing import Dict, Optional


def _db():
    from supabase_store import get_client
    return get_client()


_CACHE: dict = {}


def brief(name: str) -> Dict:
    """Everything worth knowing about one festival. Cached in the table.

    Returns a dict with sensible defaults if anything fails — a festival we
    know nothing about is a one-day festival nobody fasts for, which is the
    safe assumption.
    """
    key = (name or "").strip()
    if not key:
        return _blank(key)
    if key.lower() in _CACHE:
        return _CACHE[key.lower()]

    try:
        rows = (_db().table("festival_brief").select("*")
                .eq("name", key).limit(1).execute()).data or []
        if rows:
            _CACHE[key.lower()] = rows[0]
            return rows[0]
    except Exception as e:
        print(f"[Brief] read failed: {e}")

    got = _ask(key)
    if not got:
        return _blank(key)

    try:
        _db().table("festival_brief").upsert(got, on_conflict="name").execute()
        print(f"[Brief] {key}: {got['days']} day(s), "
              f"fasts={got['fasts']}, avoids={str(got.get('avoids'))[:40]}")
    except Exception as e:
        print(f"[Brief] write failed: {e}")
    _CACHE[key.lower()] = got
    return got


def _blank(name: str) -> Dict:
    return {"name": name, "days": 1, "fasts": False, "avoids": "",
            "eaten": "", "observance": "", "kept_by": "", "asked": ""}


def _ask(name: str) -> Optional[Dict]:
    prompt = f"""The festival "{name}" is coming up, for someone elderly in
India.

Everything a companion would need to know, as JSON and nothing else:

{{"days": 9,
  "fasts": true,
  "avoids": "meat, grain, onion and garlic",
  "eaten": "kuttu atta, sabudana, fruit, sendha namak",
  "observance": "nine evenings of puja at home, garba in some communities",
  "kept_by": "Hindus, most observantly in the north and west",
  "asked": "Aap Navratri mein vrat rakhti hain?"}}

  days        how many days it runs as observed, not as defined. A name
              beginning "First Day of" is a clue that it is more than one.
  fasts       whether fasting is usual — not whether it is required
  avoids      what the fast avoids, in plain words. "" if nobody fasts.
  eaten       what people eat INSTEAD, by name. This is what makes a food
              suggestion during the festival right rather than absent, so
              be specific: dishes and ingredients, not "special food".
  observance  what people actually do, in one line
  kept_by     which communities keep it, so it is not assumed of everyone
  asked       ONE question worth asking her, in her language, to learn what the
              calendar cannot know — usually whether she keeps it and how.
              Short, the way a person would ask. "" if there is nothing
              worth asking.

Be accurate about the fast. Telling someone their wheat parathas are a good
choice during a grain fast is the kind of mistake that matters."""

    try:
        from llm import ask
        raw = (ask(prompt, max_tokens=400) or "").replace("```json", "").replace("```", "")
        d = json.loads(raw.strip())
    except Exception as e:
        print(f"[Brief] ask failed for {name!r}: {e}")
        return None

    try:
        return {
            "name": name,
            "days": max(1, min(40, int(d.get("days") or 1))),
            "fasts": bool(d.get("fasts")),
            "avoids": str(d.get("avoids") or "")[:200],
            "eaten": str(d.get("eaten") or "")[:300],
            "observance": str(d.get("observance") or "")[:300],
            "kept_by": str(d.get("kept_by") or "")[:200],
            "asked": str(d.get("asked") or "")[:200],
        }
    except Exception as e:
        print(f"[Brief] parse failed for {name!r}: {e}")
        return None


def running_today(when=None) -> Optional[Dict]:
    """A festival happening TODAY, including its later days.

    festivals.today() matches the start date only, which is why the second
    day of Navratri looked like an ordinary Tuesday.
    """
    from datetime import date, timedelta
    from memory.festivals import upcoming, today as _festival_today

    d = when or date.today()

    t = _festival_today(d)
    if t:
        b = brief(t["name"])
        return {**t, **b, "day_of": 1}

    # Anything that started in the last few weeks and is still running.
    try:
        recent = upcoming(12, d - timedelta(days=40)) or []
    except Exception:
        return None

    for f in recent:
        try:
            started = date.fromisoformat(str(f.get("date"))[:10])
        except Exception:
            continue
        if started > d:
            continue
        b = brief(f["name"])
        n = int(b.get("days") or 1)
        if n <= 1:
            continue
        gone = (d - started).days
        if 0 < gone < n:
            return {**f, **b, "day_of": gone + 1}
    return None


def _she_keeps(user_id: str, r: Dict) -> Optional[bool]:
    """True when she has said she keeps this fast. None when unknown."""
    try:
        from memory.anchors import current
        a = current(user_id, "avoids_meat_on")
        if a and str(r["name"]).split()[-1].lower() in str(a.get("value")).lower():
            return True
    except Exception:
        pass
    return None


def _ate_between(user_id: str, start, days: int) -> list:
    """What she talked about in those days. Mostly food, during a festival:
    "sabudana khichdi banayi", "kuttu ke pakode". Subjects, as she said them."""
    from datetime import timedelta
    try:
        rows = (_db().table("subject_mentions").select("subject,happened_on")
                .eq("user_id", user_id)
                .gte("happened_on", start.isoformat())
                .lte("happened_on", (start + timedelta(days=max(1, days) - 1)).isoformat())
                .limit(200).execute()).data or []
    except Exception as e:
        print(f"[Brief] mentions read failed: {e}")
        return []
    # Not what Nancy offered and she only discussed: "idli sambar" came back
    # as something she had during Navratri because she said "try karna
    # padega" about the offer. And not the words that carry no thing at all:
    # a weekday, "home", "sab".
    offered = set()
    try:
        for o in (_db().table("suggestions").select("label").eq("user_id", user_id)
                  .gte("created_at", start.isoformat()).limit(50).execute()).data or []:
            offered.add(str(o.get("label") or "").split(" by ")[0].strip().lower())
    except Exception:
        pass
    seen, out = set(), []
    for r in rows:
        s = str(r.get("subject") or "").strip()
        low = s.lower()
        if len(low) < 3 or low in seen:
            continue
        if any(low == o or (len(low) > 4 and low in o) for o in offered if o):
            continue
        seen.add(low)
        out.append(s)
    return out[:15]


def for_user(user_id: str, when=None) -> Optional[Dict]:
    """The festival running today, if it is one SHE keeps. Or None.

    For whoever decides what to suggest: which day of how many, whether it
    fasts and what the fast avoids and allows, whether she has said she
    keeps it, and what she talked about during it — so far this time, and
    the last time it came round. That last part is how a festival habit is
    learned: nothing is assumed, the dates of what she says are already
    kept, and the festival's dates say which of them belong to it.
    """
    from datetime import date
    r = running_today(when)
    if not r:
        return None
    try:
        from memory.festivals import _observes, _relevant
        if not _relevant(r["name"], _observes(user_id)):
            return None
    except Exception as e:
        print(f"[Brief] relevance check failed, keeping it: {e}")

    d = when or date.today()
    days = int(r.get("days") or 1)
    day_of = int(r.get("day_of") or 1)
    nm = str(r["name"])
    for prefix in ("First Day of ", "Last Day of ", "Start of "):
        if nm.startswith(prefix):
            nm = nm[len(prefix):]
            break

    out = {"name": nm, "day_of": day_of, "days": days,
           "fasting": bool(r.get("fasts")), "she_keeps_it": _she_keeps(user_id, r)}
    if r.get("fasts"):
        out["fast_avoids"] = r.get("avoids") or ""
        out["eaten_instead"] = r.get("eaten") or ""

    from datetime import timedelta
    so_far = _ate_between(user_id, d - timedelta(days=day_of - 1), day_of)
    if so_far:
        out["she_talked_about_this_time"] = so_far
    try:
        from memory.festivals import last_time
        prev = last_time(r["name"], d)
        if prev:
            before = _ate_between(user_id, prev, days)
            if before:
                out["she_talked_about_last_time"] = before
    except Exception as e:
        print(f"[Brief] last-time read failed: {e}")
    return out


def hint(user_id: str) -> str:
    """What a festival means for today's message, or "".

    Facts and their boundaries. It never says how to observe: she has kept
    this her whole life and the system has read a calendar.
    """
    r = running_today()
    if not r:
        return ""
    # Hers, not everyone's. hint_for() in festivals.py checked this and the
    # brief, which is used first, did not: a Navratri brief would have gone
    # to a woman who keeps Ramzan.
    try:
        from memory.festivals import _observes, _relevant
        if not _relevant(r["name"], _observes(user_id)):
            return ""
    except Exception:
        pass

    day_of, days = r.get("day_of", 1), int(r.get("days") or 1)
    # The calendar names the start — "First Day of Sharad Navratri" — which
    # reads as nonsense on day four.
    nm = str(r["name"])
    for prefix in ("First Day of ", "Last Day of ", "Start of "):
        if nm.startswith(prefix):
            nm = nm[len(prefix):]
            break
    where = (f" — day {day_of} of {days}" if days > 1 else "")
    line = f"\n\nToday is {nm}{where}."

    if r.get("fasts"):
        # What she does about it, if she has ever said.
        keeps = None
        try:
            from memory.anchors import current
            a = current(user_id, "avoids_meat_on")
            if a and str(r["name"]).split()[-1].lower() in str(a.get("value")).lower():
                keeps = True
        except Exception:
            pass

        if keeps:
            line += (f" She keeps this one. It avoids {r.get('avoids')}. "
                     f"Suggest nothing outside that — what people eat "
                     f"instead is {r.get('eaten')}.")
        else:
            line += (f" Many people fast on it, avoiding "
                     f"{r.get('avoids') or 'certain foods'}, and you do not "
                     f"know whether she does. Do not suggest food, and do "
                     f"not tell her what is or is not allowed.")
    else:
        line += " Wish her, briefly, the way anyone would. Not a lecture."

    return line

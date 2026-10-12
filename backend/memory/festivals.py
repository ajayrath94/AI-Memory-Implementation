"""
FESTIVALS — what day it is, in the country she lives in.

Google's public Indian holiday calendar, which needs no key and no account:
fifty-eight entries for 2026, and it carries observances rather than only
gazetted holidays — Pongal, Ugadi, Gudi Padwa, Vasant Panchami, Maha
Shivaratri.

WHY NOT A FILE
A file would let us tag regions, which the feed does not: Gudi Padwa and Ugadi
fall on the same day and are Maharashtrian and Telugu respectively, and the
feed lists both without saying which is whose. But a file has to be rewritten
every October, and most Indian festivals are lunar so the dates move. The
annual edit is the thing most likely to be forgotten.

For a greeting the missing region is harmless. "Aaj Gudi Padwa hai" to a
Gujarati woman is slightly off, not wrong.

FETCHED ONCE A YEAR
The dates for 2026 do not change during 2026. One call at startup, cached on
disk, and nothing at request time.

WHAT IT IS FOR
Two things. A greeting on the day — "aaj Janmashtami hai, vrat rakhengi?" —
which pairs with a boundary afterwards asking how it went. And something to
plan around: a festival is the one date an elderly woman reliably has plans
for.
"""
import json
import os
import re
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional

ICS_URL = ("https://calendar.google.com/calendar/ical/"
           "en.indian%23holiday%40group.v.calendar.google.com/public/basic.ics")

CACHE = "/tmp/festivals_in.json"

# The ones worth a message. The feed carries fifty-eight entries a year and
# most are not things anyone marks — "Maharishi Dayanand Saraswati Jayanti"
# is a holiday for some offices and not a day she would mention.
#
# Matched loosely, so "Diwali/Deepavali" catches either spelling.
MAJOR = (
    "diwali", "deepavali", "holi", "janmashtami", "ganesh", "navratri",
    "dussehra", "dasara", "vijaya dashami", "durga puja", "raksha bandhan",
    "karva chauth", "eid", "ramzan", "bakrid", "christmas", "guru nanak",
    "makar sankranti", "pongal", "ugadi", "gudi padwa", "vishu", "baisakhi",
    "vaisakhi", "onam", "bihu", "lohri", "maha shivaratri", "ram navami",
    "rama navami", "independence day", "republic day", "gandhi jayanti",
)

# Days people fast. Worth knowing, because a fasting day changes what a
# companion should say about food — and offering lunch to someone keeping
# a vrat is the kind of mistake that shows it is not listening.
FASTING = ("navratri", "karva chauth", "janmashtami", "maha shivaratri",
           "ekadashi", "ramzan", "ramadan")


def _fetch() -> List[Dict]:
    """The year's festivals, from cache or from Google."""
    try:
        if os.path.exists(CACHE):
            with open(CACHE) as f:
                d = json.load(f)
            if d.get("year") == date.today().year and d.get("span") == 3:
                return d.get("items") or []
    except Exception:
        pass

    try:
        import urllib.request
        with urllib.request.urlopen(ICS_URL, timeout=15) as r:
            raw = r.read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"[Festivals] fetch failed: {e}")
        return []

    year = date.today().year
    items = []
    # Last year's dates too: "what did she eat during Navratri last year" needs
    # when last year's Navratri was. The feed carries the year either side.
    years = "|".join(str(y) for y in (year - 1, year, year + 1))
    for ev in raw.split("BEGIN:VEVENT")[1:]:
        d = re.search(rf"DTSTART;VALUE=DATE:((?:{years})\d{{4}})", ev)
        s = re.search(r"SUMMARY:(.+)", ev)
        if not (d and s):
            continue
        raw_date = d.group(1)
        name = s.group(1).strip()
        items.append({
            "date": f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}",
            "name": name,
            "major": any(m in name.lower() for m in MAJOR),
            "fasting": any(f in name.lower() for f in FASTING),
        })

    items.sort(key=lambda x: x["date"])
    try:
        with open(CACHE, "w") as f:
            json.dump({"year": year, "span": 3, "items": items}, f)
    except Exception:
        pass
    print(f"[Festivals] {len(items)} for {year}")
    return items


def today(when: date = None) -> Optional[Dict]:
    """What today is, if it is anything. Usually nothing."""
    d = (when or date.today()).isoformat()
    for f in _fetch():
        if f["date"] == d and f["major"]:
            return f
    return None


def soon(days: int = 2, when: date = None) -> Optional[Dict]:
    """The next major festival within a few days, if there is one.

    Two days is the useful window: far enough to plan, near enough to be
    worth mentioning. A fortnight's notice about Diwali is a calendar, not a
    conversation.
    """
    start = when or date.today()
    for i in range(1, days + 1):
        d = (start + timedelta(days=i)).isoformat()
        for f in _fetch():
            if f["date"] == d and f["major"]:
                return {**f, "in_days": i}
    return None


def hint(when: date = None) -> str:
    """A line for the composer, or nothing.

    Facts, not instructions — the same rule as the weather. It is told what
    day it is; what to say about it is its own judgement.
    """
    t = today(when)
    if t:
        line = f"\n\nToday is {t['name']}."
        if t["fasting"]:
            line += (" Many people fast on this day — ask rather than assume, "
                     "and do not suggest food until you know.")
        else:
            line += (" Mention it warmly if it fits, the way anyone would on "
                     "the day. Not a lecture about the festival.")
        return line

    s = soon(when=when)
    if s:
        when_word = "tomorrow" if s["in_days"] == 1 else f"in {s['in_days']} days"
        return (f"\n\n{s['name']} is {when_word}. If it fits, ask what they are "
                f"planning — a festival is one of the few dates they reliably "
                f"have plans for.")
    return ""


def upcoming(n: int = 5, when: date = None) -> List[Dict]:
    """The next few, for a planner rather than a greeting."""
    start = (when or date.today()).isoformat()
    out = [f for f in _fetch() if f["date"] >= start and f["major"]]
    return out[:n]


# Everyone in the country gets these, whatever they keep.
_NATIONAL = ("independence day", "republic day", "gandhi jayanti",
             "new year", "mahatma gandhi")

# What a festival belongs to, and what in her life would suggest she keeps it.
# Matched against her routine, her interests, and what she has said — never
# against her name or a stored label.
_TRADITION = {
    "hindu": {
        "festivals": ("diwali", "deepavali", "holi", "janmashtami", "ganesh",
                      "navratri", "dussehra", "dasara", "durga puja",
                      "raksha bandhan", "karva chauth", "maha shivaratri",
                      "ram navami", "rama navami", "makar sankranti", "pongal",
                      "ugadi", "gudi padwa", "vishu", "onam", "lohri",
                      "vasant panchami", "sharad navratri"),
        "signs": ("puja", "pooja", "mandir", "temple", "aarti", "bhajan",
                  "vrat", "prasad", "krishna", "ram", "shiv", "ganesh",
                  "durga", "hanuman", "gita", "satsang"),
    },
    "muslim": {
        "festivals": ("eid", "ramzan", "ramadan", "bakrid", "muharram",
                      "milad", "shab-e-barat"),
        "signs": ("roza", "namaz", "masjid", "mosque", "iftar", "sehri",
                  "quran", "dua", "eid"),
    },
    "sikh": {
        "festivals": ("guru nanak", "baisakhi", "vaisakhi", "gurpurab",
                      "guru gobind"),
        "signs": ("gurudwara", "gurdwara", "langar", "path", "waheguru",
                  "granth", "ardas"),
    },
    "christian": {
        "festivals": ("christmas", "good friday", "easter"),
        "signs": ("church", "mass", "prayer meeting", "bible", "jesus",
                  "sunday service"),
    },
    "jain": {
        "festivals": ("mahavir jayanti", "paryushan"),
        "signs": ("derasar", "jain", "paryushan", "mahavir"),
    },
}


def _observes(user_id: str) -> set:
    """Which traditions she has shown signs of keeping.

    Read from what is already there — her routine, her interests, her profile.
    Nothing is asked and nothing is stored.
    """
    found = set()
    haystack = []

    try:
        from memory.declared import get_declared
        d = get_declared(user_id)
        for r in (d.rhythm.routines or []):
            haystack.append(str(r.get("label") or ""))
            haystack.append(str(r.get("label_native") or ""))
        for cat, items in (d.interests or {}).items():
            haystack += [str(x) for x in (items or [])]
    except Exception:
        pass

    try:
        from supabase_store import get_client
        rows = (get_client().table("interest_clusters").select("label,attributes")
                .eq("user_id", user_id).eq("status", "active")
                .limit(60).execute()).data or []
        haystack += [str(r.get("label") or "") for r in rows]
    except Exception:
        pass

    try:
        from memory.profile_store import get_user_profile
        import json as _j
        p = get_user_profile(user_id) or {}
        for k in ("personality", "life_context", "cultural_context"):
            if p.get(k):
                haystack.append(_j.dumps(p[k], ensure_ascii=False))
    except Exception:
        pass

    blob = " ".join(haystack).lower()
    for tradition, spec in _TRADITION.items():
        if any(s in blob for s in spec["signs"]):
            found.add(tradition)
    return found


def _relevant(name: str, observes: set) -> bool:
    """Should this festival be mentioned to her at all?"""
    low = (name or "").lower()

    if any(n in low for n in _NATIONAL):
        return True

    for tradition, spec in _TRADITION.items():
        if any(f in low for f in spec["festivals"]):
            return tradition in observes

    # Not in any list — a jayanti or an observance nobody marks. Quiet.
    return False


def hint_for(user_id: str, when=None) -> str:
    """A line for the composer, or nothing — hers, not everyone's.

    Three days ahead is for planning, the day itself is for wishing. A
    fortnight's notice about Diwali is a calendar, not a conversation.
    """
    observes = _observes(user_id)

    t = today(when)
    if t and _relevant(t["name"], observes):
        line = f"\n\nToday is {t['name']}."
        if t["fasting"]:
            line += (" Many people fast on this day — ask rather than assume, "
                     "and do not suggest food until you know.")
        else:
            line += (" Wish them, the way anyone would on the day. Briefly, "
                     "and not a lecture about the festival.")
        return line

    s = soon(days=3, when=when)
    if s and _relevant(s["name"], observes):
        w = "tomorrow" if s["in_days"] == 1 else f"in {s['in_days']} days"
        line = (f"\n\n{s['name']} is {w}. It has not started. If they "
                f"speak as though it has, they are mistaken — do not agree, "
                f"and do not correct them either: ask what they are "
                f"planning, which is true to the date and makes the "
                f"difference clear.\n"
                f"A festival is one of the few dates they reliably have "
                f"plans for, and it is something to look forward to "
                f"together.")
        if s.get("fasting"):
            line += ("\nMany people fast on this one and you do not know "
                     "whether they do. Say nothing about what they should "
                     "eat, or how to keep it — they have observed this "
                     "festival their whole life and you have read a "
                     "calendar.")
        return line
    return ""


def _base(name: str) -> str:
    """The festival itself, without the calendar's framing."""
    n = (name or "").strip()
    for prefix in ("First Day of ", "Last Day of ", "Start of ", "Day of "):
        if n.startswith(prefix):
            n = n[len(prefix):]
    return n.strip().lower()


def last_time(name: str, before: date = None) -> Optional[date]:
    """When this festival last began, before this occurrence. None if the
    calendar does not reach back that far."""
    before = before or date.today()
    want = _base(name)
    best = None
    for f in _fetch():
        try:
            d = date.fromisoformat(f["date"])
        except Exception:
            continue
        if _base(f["name"]) == want and d < before - timedelta(days=60):
            best = d if (best is None or d > best) else best
    return best

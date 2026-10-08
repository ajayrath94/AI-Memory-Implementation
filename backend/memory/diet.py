"""
CAN SHE EAT MEAT TODAY?

Not "is she vegetarian". That question has no good answer for most of India.

Shravan is a month without meat in a great many Hindu households, and then it
resumes. Navratri, twice a year. Tuesdays for Hanuman, Saturdays for Shani,
ekadashi twice a month. And for others — Shobha among them — Sunday is the
meat day and the rest of the week is not.

A boolean cannot hold any of that. Someone who eats chicken every Sunday and
nothing on Tuesdays is neither vegetarian nor not.

SO THE ANCHOR IS A DIFFERENT SHAPE

    eats_meat        yes / no / never established
    avoids_meat_on   tuesdays, shravan, navratri, ekadashi, ...

and the question anything actually asks is can_eat_meat_today(user_id), which
reads both plus the calendar.

WHAT IS LEARNED RATHER THAN ASKED
She never has to answer a question about her diet. subject_mentions already
holds every food she has named and the day it came up, so chicken on four
Sundays and never on a Tuesday is her pattern, found the same way the weekday
rhythms were. What she says outright is stronger and overrides it.

THE ASYMMETRY, AGAIN
Offering dal to someone who eats meat costs nothing. Offering mutton during
Navratri, or to someone who gave it up after a heart scare, is the kind of
mistake that ends trust in one message. So the default is no, and yes has to
be earned.
"""
from datetime import date, timedelta
from typing import Dict, List, Optional

# Days people commonly keep without meat. Not a rule applied to anyone — only
# read when SHE has said one of them applies to her, or when her own record
# shows she keeps it.
_WEEKDAY = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
            "somvar": 0, "mangalvar": 1, "budhvar": 2, "guruvar": 3,
            "shukravar": 4, "shanivar": 5, "ravivar": 6}

# Stretches of the year, resolved against the festival calendar rather than
# hard dates — Shravan and Navratri move every year.
_SEASONS = ("shravan", "sawan", "navratri", "navaratri", "paryushan",
            "ramadan", "ramzan", "lent")


def _db():
    from supabase_store import get_client
    return get_client()


def _anchor(user_id: str, field: str):
    try:
        from memory.anchors import current
        a = current(user_id, field)
        return a.get("value") if a else None
    except Exception:
        return None


def observed_meat_days(user_id: str, weeks: int = 8) -> Dict:
    """Which days she has actually eaten meat on, from what she has said.

    Never asked. subject_mentions holds every food she has named with the day
    it came up, and that is enough to see a Sunday.
    """
    since = (date.today() - timedelta(weeks=weeks)).isoformat()
    try:
        rows = (_db().table("subject_mentions").select("subject,happened_on")
                .eq("user_id", user_id).gte("happened_on", since)
                .limit(500).execute()).data or []
    except Exception as e:
        print(f"[Diet] read failed: {e}")
        return {"days": [], "weekdays": [], "any": False}

    meat = ("chicken", "mutton", "fish", "machli", "murgh", "keema", "egg",
            "anda", "prawn", "jhinga", "meat", "gosht", "kebab", "biryani")
    days = sorted({r["happened_on"] for r in rows
                   if any(m in str(r.get("subject", "")).lower() for m in meat)})
    wds = sorted({date.fromisoformat(d).weekday() for d in days})
    return {"days": days, "weekdays": wds, "any": bool(days)}


def _running_festival() -> dict:
    """A festival happening today, including its later days.

    festivals.today() matches the start date only, so day four of a nine-day
    fast looked like an ordinary Tuesday.
    """
    try:
        from memory.festival_brief import running_today
        return running_today() or {}
    except Exception as e:
        print(f"[Diet] festival read failed: {e}")
        return {}


def _season_today() -> str:
    """A stretch of the year she may keep, or ''. From the real calendar."""
    try:
        from memory.festivals import upcoming
        soon = upcoming(days=0) or []
        for f in soon:
            name = str(f.get("name") or "").lower()
            for s in _SEASONS:
                if s in name:
                    return s
    except Exception:
        pass
    return ""


def can_eat_meat_today(user_id: str, on: date = None) -> Dict:
    """The only question worth asking. {ok, why}.

    Defaults to no. Offering dal to someone who eats meat costs nothing;
    offering mutton during Navratri does not.
    """
    on = on or date.today()

    # Her own calendar first: four weekdays, a festival span, a one-off.
    # It knows what she keeps and the brief knows how long a festival runs,
    # so day four of Navratri is not an ordinary Tuesday.
    try:
        from memory.observances import for_day
        d = for_day(user_id, on)
        if "meat" in (d.get("avoids") or "").lower():
            return {"ok": False, "why": d.get("because") or "a day she keeps"}
    except Exception as e:
        print(f"[Diet] observances read failed: {e}")

    # What she has said outright, which beats anything observed.
    said = _anchor(user_id, "eats_meat")
    if str(said).lower() in ("no", "false", "never"):
        return {"ok": False, "why": "she has said she does not eat meat"}

    avoids = str(_anchor(user_id, "avoids_meat_on") or "").lower()

    # A day of the week she keeps.
    for name, wd in _WEEKDAY.items():
        if name in avoids and on.weekday() == wd:
            return {"ok": False, "why": f"she keeps {name}s"}

    # A stretch of the year — hers if she has named it, whatever the reason.
    season = _season_today()
    if season and season in avoids:
        return {"ok": False, "why": f"it is {season}"}

    # A festival she keeps, on any of its days. The brief knows how long it
    # runs and what the fast avoids; the anchor knows whether she keeps it.
    f = _running_festival()
    if f.get("fasts"):
        nm = str(f.get("name") or "").split()[-1].lower()
        if nm and nm in avoids:
            return {"ok": False,
                    "why": f"{f.get('name')} — day {f.get('day_of', 1)} of "
                           f"{f.get('days', 1)}, and she keeps it"}

    # A fasting day from the calendar. Not everyone keeps every one, so this
    # only holds when she has given some sign that she keeps fasts at all.
    try:
        from memory.festivals import today as _ft
        f = _ft()
        if f and f.get("fasting"):
            keeps = ("vrat" in avoids or "fast" in avoids
                     or bool(_anchor(user_id, "keeps_fasts")))
            if keeps:
                return {"ok": False, "why": f"today is {f.get('name')}"}
    except Exception:
        pass

    if str(said).lower() in ("yes", "true"):
        return {"ok": True, "why": "she has said she eats meat"}

    # Nothing said. What has she actually eaten?
    seen = observed_meat_days(user_id)
    if not seen["any"]:
        return {"ok": False,
                "why": "nothing she has said suggests she eats meat"}

    # She eats it, but only on certain days — three or more mentions all on
    # one weekday is a pattern, and today is not that day.
    names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday")
    if len(seen["days"]) >= 3 and len(seen["weekdays"]) == 1:
        wd = seen["weekdays"][0]
        if on.weekday() != wd:
            return {"ok": False,
                    "why": f"she eats meat on {names[wd]}s, and today is not"}
        return {"ok": True, "why": f"{names[wd]} is her day for it"}

    return {"ok": True, "why": f"she has eaten meat on {len(seen['days'])} day(s)"}


def line(user_id: str, on: date = None) -> str:
    """One line for whatever is generating food suggestions.

    A constraint on what is GENERATED, never a thing to say to her. "Aapke
    vrat ke liye" would be presumptuous; simply not suggesting the mutton is
    right.
    """
    v = can_eat_meat_today(user_id, on)
    return ("she eats meat" if v["ok"]
            else "nothing with meat, and do not say why")

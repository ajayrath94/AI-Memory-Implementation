"""
RHYTHMS — what she does on a particular day.

Promotion counts distinct days, and that misses the thing a companion would
notice most. Chicken on four Sundays and khichdi on four scattered days both
come back as "4 days" — but only the first lets you say, on a Sunday morning,
"aaj Sunday hai, chicken banayengi?"

And it gets one case backwards. Three mentions in a single week and nothing
since reads as a habit, when it is the opposite: something she was doing and
stopped.

WHAT THIS READS
subject_mentions, which holds every subject with the day it came up and
survives the thread being compressed away. The weekday was always there; nothing
looked at it.

THE DAY GOES IN THE WORDS
Naming it is the warmer choice — it shows she has been noticed rather than
merely predicted. "Aaj Sunday hai" is what someone who knows her would say.
"""
from datetime import date, timedelta
from typing import Dict, List, Optional

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday")

# A rhythm: at least this many mentions, and this share on one weekday.
# Three of four Sundays is 75% and clears. Two of three is 67% and does not,
# because two is not a pattern.
MIN_MENTIONS = 3
MIN_SHARE = 0.70

# A spell: everything inside a week, and nothing for a week since. That is
# something she was doing and stopped — not a habit, and not worth offering
# back to her as if it were.
SPELL_SPAN = 7
SPELL_QUIET = 7

# How far back to look. Long enough that four Sundays fit, short enough that a
# habit from last spring does not still decide this week.
WINDOW = 60


def _db():
    from supabase_store import get_client
    return get_client()


def _dates(values) -> List[date]:
    out = []
    for v in values:
        try:
            out.append(date.fromisoformat(str(v)[:10]))
        except Exception:
            continue
    return sorted(set(out))


def weekday_pattern(dates: List[date]) -> Optional[Dict]:
    """The weekday this falls on, if it falls on one. Or None.

    Only distinct days count — saying "chicken" four times on one Sunday is one
    Sunday.
    """
    ds = _dates(dates)
    if len(ds) < MIN_MENTIONS:
        return None
    counts: Dict[int, int] = {}
    for d in ds:
        counts[d.weekday()] = counts.get(d.weekday(), 0) + 1
    wd, n = max(counts.items(), key=lambda kv: kv[1])
    share = n / len(ds)
    if share < MIN_SHARE:
        return None
    return {"weekday": WEEKDAYS[wd], "weekday_n": wd,
            "on_that_day": n, "of": len(ds), "share": round(share, 2)}


def is_spell(dates: List[date], today: date = None) -> bool:
    """Clustered close together, then nothing. Something she stopped.

    Three mentions in one week and silence for a month currently promotes as a
    habit — the opposite of what it is.
    """
    ds = _dates(dates)
    if len(ds) < MIN_MENTIONS:
        return False
    today = today or date.today()
    span = (ds[-1] - ds[0]).days
    quiet = (today - ds[-1]).days
    return span <= SPELL_SPAN and quiet >= SPELL_QUIET


def rhythms_for(user_id: str, today: date = None) -> List[Dict]:
    """Every subject she ties to a day of the week."""
    today = today or date.today()
    since = (today - timedelta(days=WINDOW)).isoformat()
    try:
        rows = (_db().table("subject_mentions")
                .select("subject,cluster_id,happened_on,pillar,sentiment")
                .eq("user_id", user_id).gte("happened_on", since)
                .limit(1000).execute()).data or []
    except Exception as e:
        print(f"[Rhythm] read failed: {e}")
        return []

    by: Dict[str, dict] = {}
    for r in rows:
        key = str(r.get("subject") or "").strip().lower()
        if len(key) < 3:
            continue
        e = by.setdefault(key, {"subject": r["subject"], "dates": [],
                                "cluster_id": r.get("cluster_id"),
                                "pillar": r.get("pillar"), "feel": []})
        e["dates"].append(r["happened_on"])
        if r.get("cluster_id"):
            e["cluster_id"] = r["cluster_id"]
        if r.get("sentiment") is not None:
            e["feel"].append(float(r["sentiment"]))

    out = []
    for e in by.values():
        if is_spell(e["dates"], today):
            continue
        p = weekday_pattern(e["dates"])
        if not p:
            continue
        out.append({
            "subject": e["subject"],
            "cluster_id": e["cluster_id"],
            "pillar": e["pillar"],
            "feeling": round(sum(e["feel"]) / len(e["feel"]), 2) if e["feel"] else 0.0,
            "last": str(_dates(e["dates"])[-1]),
            **p,
        })
    out.sort(key=lambda x: (-x["share"], -x["of"]))
    return out


def due_today(user_id: str, today: date = None) -> List[Dict]:
    """The rhythms whose day is today. Usually none.

    Something she soured on is not offered back to her, however regular — a
    rhythm is a reason to offer, and a bad feeling outranks a reason.
    """
    today = today or date.today()
    return [r for r in rhythms_for(user_id, today)
            if r["weekday_n"] == today.weekday() and r["feeling"] > -0.2]


def hint(r: Dict) -> str:
    """A line for the composer. The day goes in the words."""
    return (f"\n\nToday is {r['weekday']}, and on {r['weekday']}s they "
            f"usually have or do: {r['subject']}. You may name the day — "
            f"\"aaj {r['weekday']} hai\" — because noticing it is the warm "
            f"thing. Offer it once, lightly. If they have already said what "
            f"they are doing today, do not.")

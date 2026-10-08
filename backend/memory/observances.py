"""
HER DAYS — what she keeps, and what she does instead.

A woman who does not eat meat on Mondays, Tuesdays, Thursdays and Saturdays
eats it on three days of the week. That is not a restriction to work around;
it is four days of her week with a shape to them, and the shape is usually a
fast kept for someone — Shiva on Monday, Hanuman on Tuesday, Shani on
Saturday.

WHAT WAS WRONG WITH THE OLD SHAPE
avoids_meat_on was a text field holding something like "['Navratri']", parsed
loosely on every read. It could not hold four weekdays, a nine-day festival
and a one-off vrat at the same time, and it had nowhere to put what she DOES
on those days.

THREE KINDS OF DAY, ONE TABLE

    weekday    every Tuesday, forever
    festival   Navratri's nine days, which move each year — the span comes
               from festival_brief, so this holds the name and not the dates
    date       one Thursday, for a particular reason

AND WHAT SHE DOES, NOT ONLY WHAT SHE AVOIDS
A Tuesday is not an absence of meat. It is a fast, and there is usually
something she eats instead and somewhere she goes. Both are offerable: a
companion that knows Tuesday is her mandir day has something to say on a
Tuesday.

WHY THIS MATTERS FOR PATTERNS
The rhythm detector has been inferring "chicken on Sundays" from mentions.
If the calendar says four weekdays are meatless, Sunday chicken is not a
discovery — it is what is left. The calendar explains the pattern instead of
the pattern being guessed at, and a mention that contradicts the calendar is
the contradiction check rather than noise.
"""
from datetime import date
from typing import Dict, List, Optional

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday")

# How she might name them. Not a translation table — the model reads her
# words — but these are common enough to resolve without a call.
_ALSO = {
    "somvar": "monday", "som": "monday",
    "mangalvar": "tuesday", "mangal": "tuesday",
    "budhvar": "wednesday", "budh": "wednesday",
    "guruvar": "thursday", "brihaspativar": "thursday", "guru": "thursday",
    "shukravar": "friday", "shukra": "friday",
    "shanivar": "saturday", "shani": "saturday",
    "ravivar": "sunday", "itvar": "sunday", "ravi": "sunday",
}


def _db():
    from supabase_store import get_client
    return get_client()


def _weekday_name(s: str) -> str:
    low = (s or "").strip().lower()
    if low in _WEEKDAYS:
        return low
    return _ALSO.get(low, "")


def add(user_id: str, rule_type: str, value: str, avoids: str = "",
        observes: str = "", source: str = "said", quote: str = "") -> bool:
    """Record one of her days.

    rule_type is weekday | festival | date.
    """
    if rule_type not in ("weekday", "festival", "date"):
        return False
    v = (value or "").strip()
    if rule_type == "weekday":
        v = _weekday_name(v)
    if not v:
        return False

    try:
        _db().table("observances").upsert({
            "user_id": user_id,
            "rule_type": rule_type,
            "value": v.lower() if rule_type == "weekday" else v,
            "avoids": (avoids or "").strip()[:200],
            "observes": (observes or "").strip()[:200],
            "source": source,
            "quote": (quote or "")[:200],
        }, on_conflict="user_id,rule_type,value").execute()
        print(f"[Observances] {user_id}: {rule_type} {v}"
              + (f" avoids {avoids}" if avoids else "")
              + (f", {observes}" if observes else ""))
        return True
    except Exception as e:
        print(f"[Observances] write failed: {e}")
        return False


def drop(user_id: str, rule_type: str, value: str) -> bool:
    """She has stopped keeping it."""
    try:
        _db().table("observances").delete() \
            .eq("user_id", user_id).eq("rule_type", rule_type) \
            .eq("value", (value or "").strip().lower()).execute()
        print(f"[Observances] {user_id}: dropped {rule_type} {value}")
        return True
    except Exception as e:
        print(f"[Observances] drop failed: {e}")
        return False


def all_for(user_id: str) -> List[Dict]:
    try:
        return (_db().table("observances").select("*")
                .eq("user_id", user_id).execute()).data or []
    except Exception as e:
        print(f"[Observances] read failed: {e}")
        return []


def for_day(user_id: str, on: date = None) -> Dict:
    """What today is, for her. {avoids, observes, because}.

    Empty on most days, which is the common answer. A Tuesday for someone who
    keeps Tuesdays is not.
    """
    on = on or date.today()
    weekday = _WEEKDAYS[on.weekday()]
    avoids, observes, because = [], [], []

    rows = all_for(user_id)

    for r in rows:
        kind, val = r.get("rule_type"), str(r.get("value") or "").lower()
        hit = False

        if kind == "weekday" and val == weekday:
            hit = True
            because.append(f"she keeps {weekday.title()}s")
        elif kind == "date" and val == on.isoformat():
            hit = True
            because.append("today in particular")
        elif kind == "festival":
            # The span comes from the brief, so this holds the name only and
            # a nine-day festival is nine days.
            try:
                from memory.festival_brief import running_today
                f = running_today(on) or {}
                nm = str(f.get("name") or "").lower()
                if nm and (val in nm or nm.endswith(val)):
                    hit = True
                    because.append(f"{f.get('name')}, day "
                                   f"{f.get('day_of', 1)} of {f.get('days', 1)}")
            except Exception:
                pass

        if hit:
            if r.get("avoids"):
                avoids.append(str(r["avoids"]))
            if r.get("observes"):
                observes.append(str(r["observes"]))

    # And a festival she has not told us about, whose fast is widely kept.
    # Not applied — only noted, because most people do not keep most fasts.
    return {
        "avoids": ", ".join(dict.fromkeys(avoids)),
        "observes": ", ".join(dict.fromkeys(observes)),
        "because": "; ".join(dict.fromkeys(because)),
        "weekday": weekday,
    }


def avoids_today(user_id: str, what: str = "meat", on: date = None) -> bool:
    """Does she avoid this today? The question the diet filter asks."""
    d = for_day(user_id, on)
    return (what or "").lower() in (d.get("avoids") or "").lower()


def hint(user_id: str, on: date = None) -> str:
    """One line for the composer, or "".

    What she avoids never reaches her — it shapes what is offered, the same
    as her conditions. What she DOES is worth knowing: a companion that
    knows Tuesday is her mandir day has something to say on a Tuesday.
    """
    d = for_day(user_id, on)
    if not d.get("avoids") and not d.get("observes"):
        return ""

    line = f"\n\nToday — {d['because']}."
    if d.get("observes"):
        line += f" She {d['observes']} on days like this."
    if d.get("avoids"):
        line += (f" Suggest nothing with {d['avoids']} today, and do not say "
                 f"why — she knows her own observances and being told them "
                 f"is not company.")
    return line


# ── learning them from what she says ────────────────────────────────────────

def read(user_id: str, text: str) -> List[Dict]:
    """Did she just describe one of her days? Usually not."""
    said = (text or "").strip()
    if len(said) < 8:
        return []

    prompt = f"""Someone elderly in India said this:

"{said[:400]}"

Does it say what she keeps on particular DAYS? JSON only:

{{"found": [{{"rule_type": "weekday|festival|date",
              "value": "tuesday|Navratri|2026-10-15",
              "avoids": "meat",
              "observes": "vrat, mandir"}}]}}

  weekday   a day of the week she keeps, every week. "Mangalvar ko vrat
            rakhti hoon" — tuesday. Give the English name.
  festival  by name. Navratri, Shravan, Paryushan, Ramadan.
  date      a specific day, as YYYY-MM-DD, for a one-off.

  avoids    what she does not have. Usually meat; sometimes grain, onion
            and garlic, or everything until moonrise.
  observes  what she DOES — vrat, mandir, puja. A Tuesday is not an absence
            of meat, it is a fast kept for someone.

  If she says she keeps a vrat and does not say what it avoids, avoids is
  "meat" — that is what a vrat means unless she says otherwise. Recording
  the fast without what it avoids leaves the food suggestions unchanged,
  which is the whole reason this is written down.

Only what she says about HERSELF, and only when she says she keeps it.
"Mangalvar ko log vrat rakhte hain" is what people do. "Kal mandir gayi
thi" is one visit, not a standing day.

An empty list is the usual answer. No prose."""

    try:
        from llm import ask
        import json as _j
        raw = (ask(prompt, max_tokens=250) or "").replace("```json", "").replace("```", "")
        found = _j.loads(raw.strip()).get("found") or []
    except Exception as e:
        print(f"[Observances] read failed: {e}")
        return []

    out = []
    for f in found:
        kind = str(f.get("rule_type") or "").strip().lower()
        val = str(f.get("value") or "").strip()
        if kind not in ("weekday", "festival", "date") or not val:
            continue
        out.append({"rule_type": kind, "value": val,
                    "avoids": str(f.get("avoids") or "")[:200],
                    "observes": str(f.get("observes") or "")[:200]})
    return out


def hear(user_id: str, text: str) -> int:
    """Read what she said and record it. Returns how many days were learned."""
    n = 0
    for d in read(user_id, text):
        if add(user_id, d["rule_type"], d["value"], d.get("avoids", ""),
               d.get("observes", ""), "said", text):
            n += 1
    return n

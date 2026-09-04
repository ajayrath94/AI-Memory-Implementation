"""
TONE — the shape of the moment, so the same thing can be said differently.

Everything else in this system decides WHAT to say. This decides nothing; it
describes the situation the saying happens in, and lets the composer find the
register itself.

The distinction matters. A companion does not withhold a song from someone who
seems low — it offers the same song more gently. Treating emotional context as
a filter gets that backwards. It belongs in the voice, not the choice.

NO LABELS
This never concludes that someone is lonely, low or struggling. It reports the
configuration — her daughter is abroad, it is Sunday evening, she has not
mentioned her in two weeks, she has been quiet since Thursday — and stops there.
Two reasons, and the second is the real one:

  A label is a claim. Deciding someone is lonely and behaving accordingly, when
  they have never said so, is the same overreach as inferring their religion
  from "namaste". Being wrong about it is worse than saying nothing.

  And a label is less useful. "She is lonely" gives a model one adjective;
  the facts give it a situation, and models write better from situations. This
  is the same reason fusion.py hands over "it is 12°C and their knees hurt in
  the cold" rather than "ask about their knees".

WHAT IT READS
  family      who is where, and how long since they came up
  situation   alone or not, mobility — from life_context
  rhythm      the day, the hour, whether this hour usually means something
  silence     how long since she wrote, against her own pattern
  mood        recent session valence, if there is any

Most of the time it returns nothing, which is correct. An ordinary Tuesday
afternoon has no shape worth remarking on.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List


def _profile(user_id: str) -> dict:
    try:
        from memory.profile_store import get_user_profile
        return get_user_profile(user_id) or {}
    except Exception:
        return {}


def _family_notes(user_id: str) -> List[str]:
    """Who is where, and how long since they were mentioned.

    FAMILY is excluded from interests deliberately — people are not things to
    offer. But it was excluded from everything, which is why a companion that
    knows her daughter is abroad has never once acted like it.
    """
    notes: List[str] = []
    try:
        from supabase_store import get_client
        rows = (get_client().table("interest_clusters")
                .select("label,attributes,last_event,event_count")
                .eq("user_id", user_id).eq("pillar", "FAMILY")
                .eq("status", "active").execute()).data or []
    except Exception as e:
        print(f"[Tone] family read failed: {e}")
        return notes

    for r in rows[:4]:
        attrs = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        rel   = attrs.get("relationship") or ""
        where = attrs.get("location") or ""
        label = r.get("label") or ""
        if not label:
            continue

        bit = label
        if rel:
            bit += f" ({rel})"
        if where:
            bit += f", who is in {where}"

        days = None
        if r.get("last_event"):
            try:
                dt = datetime.fromisoformat(str(r["last_event"]).replace("Z", "+00:00"))
                days = (datetime.now(timezone.utc) - dt).days
            except Exception:
                pass
        # A fortnight without mentioning a child who lives far away is worth
        # noting. A fortnight without mentioning one who lives downstairs is
        # not, which is why distance is part of the sentence.
        if days is not None and days >= 14 and where:
            bit += f" — not mentioned for {days} days"
        notes.append(bit)
    return notes


def _situation(user_id: str) -> List[str]:
    """Alone or not, and anything about mobility. These change what a suggestion
    means more than any preference does: proposing a walk to someone who
    struggles to walk is worse than proposing the wrong song."""
    out: List[str] = []
    p = _profile(user_id)

    life = p.get("life_context")
    if isinstance(life, str) and life.strip():
        out.append(life.strip()[:200])
    elif isinstance(life, dict):
        living = life.get("living_situation") or life.get("living")
        if living:
            out.append(str(living)[:200])

    health = p.get("health") or {}
    if isinstance(health, dict):
        conds = [str(c) for c in (health.get("conditions") or [])][:3]
        if conds:
            out.append("Living with " + ", ".join(conds) + ".")
    return out


def _quiet_for(user_id: str) -> Optional[str]:
    try:
        from memory.time_context import time_context
        tc = time_context(user_id)
        mins = tc.get("minutes_since_last")
        if mins is None:
            return None
        days = mins / 1440.0
        if days >= 2:
            # Stated as something to be gentle ABOUT, never something to
            # remark on. Every composed message was opening with "kitne din ho
            # gaye" — a reproach dressed as warmth, and the first thing someone
            # reads after a hard few days should not be a complaint about
            # their absence.
            return (f"It has been about {int(days)} days since they wrote. Do "
                    f"NOT mention this — no 'kitne din ho gaye', no 'kahan "
                    f"gayab ho gaye'. Simply pick up as though you spoke "
                    f"yesterday.")
        if tc.get("unusual_silence"):
            return ("They have been quieter today than usual. Do not remark on "
                "it.")
    except Exception as e:
        print(f"[Tone] silence read failed: {e}")
    return None


def _recent_mood(user_id: str) -> Optional[str]:
    """Recent session valence, as a direction rather than a verdict."""
    try:
        from supabase_store import get_client
        since = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        rows = (get_client().table("sessions").select("valence,soft_flags")
                .eq("user_id", user_id).not_.is_("valence", "null")
                .gte("created_at", since)
                .order("created_at", desc=True).limit(5).execute()).data or []
    except Exception as e:
        print(f"[Tone] mood read failed: {e}")
        return None

    vals = [float(r["valence"]) for r in rows if r.get("valence") is not None]
    if len(vals) < 3:
        return None

    avg = sum(vals) / len(vals)
    # Flags carry a severity now. Sessions written before that change hold
    # plain strings, so both shapes have to be read — and this is a live break
    # the moment a new session lands, not a future one.
    flags = set()
    for r in rows:
        for f in (r.get("soft_flags") or []):
            if isinstance(f, str):
                flags.add(f)
            elif isinstance(f, dict) and f.get("flag"):
                flags.add(f["flag"])

    # Deliberately not "she is sad". The last few conversations have had a
    # certain weight to them; what that means is the composer's business, and
    # more often than not it means nothing.
    if avg <= -0.25:
        line = "The last few conversations have been heavier than usual."
        if flags:
            line += f" What came up: {', '.join(sorted(flags)[:3])}."
        return line
    if avg >= 0.5:
        return "They have been in good spirits lately."
    return None


def _day_shape(user_id: str) -> Optional[str]:
    """Some days mean something. Sunday is when children call; Tuesday and
    Saturday carry weight for many of the people this is built for.

    Stated as what the day IS, never as an instruction — "it is Sunday evening"
    lets the model do what a person would with that, which is usually nothing.
    """
    try:
        from memory.time_context import time_context
        from zoneinfo import ZoneInfo
        from memory.declared import get_declared
        tz = ZoneInfo(get_declared(user_id).place.timezone)
        now = datetime.now(tz)
        slot = time_context(user_id).get("slot") or ""
    except Exception:
        return None

    weekday = now.strftime("%A")
    if weekday == "Sunday" and slot in ("afternoon", "evening"):
        return "It is Sunday evening."
    if weekday in ("Tuesday", "Saturday") and slot == "morning":
        return f"It is {weekday} morning."
    return None


def tone_context(user_id: str, slot: str = "", intent: str = "") -> str:
    """
    The shape of the moment, or nothing.

    Nothing is the common answer. An ordinary Tuesday afternoon for someone who
    wrote an hour ago has no shape worth remarking on, and saying so anyway
    would make every message sound like it was reacting to something.
    """
    parts: List[str] = []

    fam = _family_notes(user_id)
    if fam:
        parts.append("Their people: " + "; ".join(fam) + ".")

    parts.extend(_situation(user_id))

    for fn in (_day_shape, _quiet_for, _recent_mood):
        try:
            line = fn(user_id)
        except Exception as e:
            print(f"[Tone] {fn.__name__} raised: {e}")
            continue
        if line:
            parts.append(line)

    # Family and situation alone are just biography — true every day, and not a
    # reason to change how anything is said. Something about TODAY has to be
    # present before this is worth including.
    has_today = len(parts) > len(fam and [1] or []) + len(_situation(user_id))
    if not parts or not has_today:
        return ""

    return (
        "The shape of this moment:\n"
        + "\n".join(f"  {p}" for p in parts)
        + "\nThis is context for HOW you say things, not what you say. Do not "
          "name any of it, do not ask about it directly, and do not become "
          "sombre — a person who noticed all this would simply be a little "
          "warmer, and would leave more room for them to talk if they wanted "
          "to."
    )

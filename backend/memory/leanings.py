"""
WHAT THIS DAY LEANS TOWARDS, AND WHAT HAS GONE QUIET.

Two things sat between what the system knows and what it offers.

A RHYTHM IS ALL OR NOTHING
Three mentions and seventy per cent on one weekday makes a rhythm, and a
rhythm overrides the draw entirely — "aaj Sunday hai, chicken banayengi?".
Below that bar a pattern has no voice at all. She has had chicken on two
Sundays out of the last three; that is not certain enough to override
anything and it is certainly enough to make chicken likelier on a Sunday
than khichdi.

Most patterns live in between, and they were silent.

AND ABSENCE IS NEVER NOTICED
days_ago is computed and used only to change the WORDING of an offer —
"bahut din se" rather than "try kijiye". But a thing she did daily and has
not done for three weeks is more interesting than anything she might be
offered. "Bahut din se sair nahi ki" is a better sentence than another song.

So: a lift for what this day favours, and a flag for what has gone quiet.
Both read subject_mentions, which already holds every subject with its date.

WHAT THIS IS NOT
A rule about Sundays, or about food. The weekday is whatever hers turn out to
be, and the subject is whatever she talks about — a walk, a temple, a serial,
a friend she rings.
"""
from datetime import date, timedelta
from typing import Dict, List

# How much a weekday leaning lifts a subject's weight. Deliberately modest:
# this is "likelier", not "certain" — a rhythm is what certain looks like, and
# it overrides the draw instead.
LEAN_MAX = 0.8

# Mentioned on this weekday at least this often to count as leaning at all.
LEAN_MIN = 2

# Gone quiet: she used to mention it regularly and has not for a while.
QUIET_AFTER = 14          # days of silence
WAS_REGULAR = 3           # mentions before that, or it was never a habit
LOOK_BACK = 60


def _db():
    from supabase_store import get_client
    return get_client()


def _history(user_id: str, days: int = LOOK_BACK) -> Dict[str, List[date]]:
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        rows = (_db().table("subject_mentions")
                .select("subject,cluster_id,happened_on")
                .eq("user_id", user_id).gte("happened_on", since)
                .limit(800).execute()).data or []
    except Exception as e:
        print(f"[Leaning] read failed: {e}")
        return {}

    out: Dict[str, List[date]] = {}
    for r in rows:
        s = str(r.get("subject") or "").strip().lower()
        if len(s) < 3:
            continue
        try:
            out.setdefault(s, []).append(
                date.fromisoformat(str(r["happened_on"])[:10]))
        except Exception:
            continue
    return {k: sorted(set(v)) for k, v in out.items()}


def leanings(user_id: str, on: date = None) -> Dict[str, float]:
    """What this day of the week favours. {subject: lift}, usually small.

    Not a rhythm — a rhythm is three mentions and seventy per cent on one
    day, and it decides the offer by itself. This is the shoulder of that:
    two Sundays out of three is a lean, and a lean only makes something
    likelier.
    """
    on = on or date.today()
    wd = on.weekday()
    out = {}

    for subject, days in _history(user_id).items():
        if len(days) < LEAN_MIN:
            continue
        here = [d for d in days if d.weekday() == wd]
        if len(here) < LEAN_MIN:
            continue
        share = len(here) / len(days)
        # Two of two is a stronger lean than two of six.
        out[subject] = round(min(LEAN_MAX, share * len(here) * 0.3), 2)

    return out


def gone_quiet(user_id: str, on: date = None) -> List[Dict]:
    """Things she used to mention and has not for a while.

    More interesting than anything she might be offered. A woman who walked
    every evening and has not mentioned it in three weeks has either stopped
    or something is wrong, and either way it is worth asking about rather
    than suggesting a song.
    """
    on = on or date.today()
    out = []

    for subject, days in _history(user_id).items():
        if len(days) < WAS_REGULAR:
            continue
        silent = (on - days[-1]).days
        if silent < QUIET_AFTER:
            continue
        # How often it used to come up, before the silence.
        span = max(1, (days[-1] - days[0]).days)
        every = span / len(days)
        # Silent for several times longer than its usual gap.
        if silent < every * 2.5:
            continue
        out.append({
            "subject": subject,
            "silent_days": silent,
            "used_to": f"about every {round(every)} day(s)",
            "times": len(days),
            "last": days[-1].isoformat(),
        })

    out.sort(key=lambda x: -x["silent_days"])
    return out


def hint(user_id: str, on: date = None) -> str:
    """One line for the composer about something that has gone quiet.

    Returns "" almost always. When it does not, it is usually better than an
    offer — asking after a thing she has stopped doing is company, where
    another suggestion is a catalogue.
    """
    quiet = gone_quiet(user_id, on)
    if not quiet:
        return ""
    q = quiet[0]
    return (f"\n\nShe used to mention {q['subject']} {q['used_to']} and has "
            f"not for {q['silent_days']} days. Ask after it — lightly, once, "
            f"the way you would notice a friend had stopped doing something. "
            f"Not an offer, and not a worry: she may simply have moved on.")

"""
WHEN SHE ACTUALLY ANSWERS.

Recommendations were decided six times over three days and never once sent.
The reason was ordinary: the cadence gate wants ninety minutes since the last
message, and the scheduler was deciding an offer fifteen to forty-five minutes
after a boundary. They were permanently in the shadow of one.

Giving offers their own hour fixes it. But a fixed hour is a guess about a
person, and the data to do better is already there — every proactive message
has a timestamp, and whether she replied within the hour is recoverable from
her own messages.

SO IT LEARNS
Each hour carries how often a message sent then got a reply. The best hour
wins, the rest do not. Early on this will overfit wildly — two replies at four
in the afternoon and it will believe four o'clock is her hour. That is fine.
It smooths out as weeks accumulate, and a wrong guess costs one message at a
slightly wrong time.

UNTIL THERE IS ANYTHING TO LEARN FROM
Mid-afternoon, between lunch and her walk. Not a neutral default — it is the
gap between two boundaries, which is the one time of day an offer is not
competing with something else.

WHAT THIS IS NOT
A model call. "Which hour does she reply at" is counting, and counting is what
arithmetic is for.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

# Between lunch and the evening walk. Chosen because nothing else fires then,
# not because afternoons are special.
DEFAULT_HOUR = 15      # only when her day is unknown


def open_hours(user_id: str) -> tuple:
    """The gaps in HER day, read fresh each time.

    One hour is brittle — a day she is out at three has no offer at all. And
    a fixed list is worse: 15:00 is a gap in THIS woman's day, which runs
    06:30 to 21:00 with meals at 8:30, 13:00 and 19:30. Someone who eats at
    11:30 would be interrupted mid-meal.

    So: her waking hours, minus everything already happening, minus an hour
    either side of it. day.events is rebuilt on every proactive check, so a
    routine she changes at noon is respected that afternoon.
    """
    busy, wake, sleep = set(), 9, 21
    try:
        from memory.day import events as _ev
        for e in _ev(user_id):
            at = str(e.get("due_at") or "")[:2]
            if at.isdigit():
                h = int(at)
                busy |= {h - 1, h, h + 1}
    except Exception as e:
        print(f"[Timing] day read failed: {e}")

    try:
        from memory.declared import get_declared
        r = get_declared(user_id).rhythm
        if getattr(r, "wake", None) and str(r.wake)[:2].isdigit():
            wake = max(9, int(str(r.wake)[:2]) + 2)    # not as she wakes
        if getattr(r, "sleep", None) and str(r.sleep)[:2].isdigit():
            sleep = min(21, int(str(r.sleep)[:2]) - 1)  # nor as she settles
    except Exception:
        pass

    free = tuple(h for h in range(wake, sleep + 1) if h not in busy)
    return free or (DEFAULT_HOUR,)

# Hours nobody should be offered anything, whatever the numbers say.
TOO_EARLY, TOO_LATE = 9, 20

# Below this many observations an hour's rate means nothing, and the default
# holds. Deliberately low: overfitting early is acceptable, and the whole
# thing settles as weeks accumulate.
ENOUGH = 3


def _db():
    from supabase_store import get_client
    return get_client()


def _ist(ts) -> datetime:
    """Her clock, not the server's."""
    from datetime import datetime as _dt
    t = _dt.fromisoformat(str(ts).replace("Z", "+00:00"))
    return t + timedelta(hours=5, minutes=30)


def replies_by_hour(user_id: str, weeks: int = 8) -> Dict[int, Dict]:
    """For each hour: messages sent then, and how many she answered.

    A reply is anything she says within an hour of a proactive message. Not
    perfect — she may have been writing anyway — but it is the signal that
    exists, and the alternative is guessing.
    """
    since = (datetime.now(timezone.utc) - timedelta(weeks=weeks)).isoformat()
    try:
        sent = (_db().table("proactive_events")
                .select("created_at,delivered_at,action")
                .eq("user_id", user_id).gte("created_at", since)
                .not_.is_("delivered_at", "null")
                .limit(500).execute()).data or []
        sess = (_db().table("sessions").select("id")
                .eq("user_id", user_id).gte("updated_at", since)
                .limit(200).execute()).data or []
        said = []
        for s in sess:
            said += (_db().table("messages").select("timestamp")
                     .eq("session_id", s["id"]).eq("role", "user")
                     .gte("timestamp", since).limit(300).execute()).data or []
    except Exception as e:
        print(f"[Timing] read failed: {e}")
        return {}

    hers = sorted(_ist(m["timestamp"]) for m in said if m.get("timestamp"))

    out: Dict[int, Dict] = {}
    for p in sent:
        when = _ist(p.get("delivered_at") or p["created_at"])
        h = when.hour
        row = out.setdefault(h, {"sent": 0, "answered": 0})
        row["sent"] += 1
        # Did she say anything in the hour after it?
        if any(when <= t <= when + timedelta(hours=1) for t in hers):
            row["answered"] += 1

    for h, row in out.items():
        row["rate"] = row["answered"] / row["sent"] if row["sent"] else 0.0
    return out


_CACHE = {}


def best_hour(user_id: str) -> Dict:
    """The hour to offer her something. {hour, why, confidence}.

    Overfits early and is meant to. Two replies at four o'clock will make it
    believe in four o'clock, and a month of data will correct it.
    """
    # Cached for the day. This scans eight weeks of messages, and
    # good_moment calls it on every proactive check, for every user.
    from datetime import date as _d
    key = (user_id, _d.today().isoformat())
    if key in _CACHE:
        return _CACHE[key]

    by = replies_by_hour(user_id)
    # Not an hour a boundary already owns. Her answer rates at 9, 13 and 18
    # are nearly identical — 35, 33, 31 per cent — because those are the
    # boundary hours, and a question invites a reply where a reminder does
    # not. Choosing one of them puts the offer straight back into the shadow
    # it was built to escape.
    busy = set()
    try:
        from memory.day import events as _day_events
        for e in _day_events(user_id):
            at = str(e.get("due_at") or "")[:2]
            if at.isdigit():
                busy |= {int(at) - 1, int(at), int(at) + 1}
    except Exception:
        pass

    usable = {h: r for h, r in by.items()
              if r["sent"] >= ENOUGH and TOO_EARLY <= h <= TOO_LATE
              and h not in busy}

    if not usable:
        seen = sum(r["sent"] for r in by.values())
        _CACHE[key] = {"hour": DEFAULT_HOUR, "confidence": 0.0,
                       "why": f"nothing learned yet ({seen} message(s))"}
        return _CACHE[key]

    h, row = max(usable.items(), key=lambda kv: (kv[1]["rate"], kv[1]["sent"]))
    if row["rate"] <= 0:
        _CACHE[key] = {"hour": DEFAULT_HOUR, "confidence": 0.0,
                       "why": "she has not answered at any hour yet"}
        return _CACHE[key]

    _CACHE[key] = {"hour": h, "confidence": min(1.0, row["sent"] / 10.0),
                   "why": f"she answered {row['answered']} of {row['sent']} "
                          f"at {h}:00"}
    return _CACHE[key]


def good_moment(user_id: str, now_min: int = None, window: int = 45) -> bool:
    """Is now within reach of her hour?

    A window rather than an instant, because the scheduler runs every fifteen
    minutes and an offer that needs 15:00 exactly would mostly never fire.
    """
    if now_min is None:
        try:
            from memory.suggestions import _moment
            now_min = _moment(user_id)["now_min"]
        except Exception:
            now_min = datetime.now(timezone.utc).hour * 60 + 330

    # Her learned hour first, then the other gaps in her day. The cadence
    # gate still caps this at one offer a day, so several candidates are not
    # several offers — they are several chances for one to land.
    b = best_hour(user_id)
    hours = [b["hour"]] + [h for h in open_hours(user_id) if h != b["hour"]]
    return any(abs(now_min - h * 60) <= window for h in hours)


def note(user_id: str) -> str:
    """One line, for the logs and the dashboard."""
    b = best_hour(user_id)
    return f"offers at {b['hour']}:00 — {b['why']}"

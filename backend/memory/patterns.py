"""
ROUTINE OBSERVATION — what their day actually looks like.

Everything the companion notices is currently about what someone SAYS. Sleeping
later, going quiet at a time they are normally chatty, drifting off a routine —
none of that reaches anything, because there is no baseline to deviate from.
This builds the baseline.

Two sources, kept separate rather than merged:

  declared  — what they told us at onboarding. Authoritative until they change
              it. Someone saying "I wake at 6:30" is better evidence than a
              fortnight of inference.
  observed  — what the timestamps show. Never overwrites declared; when the two
              diverge the difference is recorded, and the companion asks about
              it rather than deciding on their behalf.

The divergence is the valuable part. "She says 6:30 but has been talking at 8
for a week" is either a routine change or a decline, and only she knows which.

SPREAD MATTERS AS MUCH AS THE CENTRE. Someone up between 6:00 and 6:30 has a
routine; someone between 5:00 and 11:00 does not, and a "deviation" from the
second means nothing. Confidence is built from both.
"""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from statistics import median
from typing import Optional
from zoneinfo import ZoneInfo

# Below this many days with data, a pattern is a guess rather than a routine.
MIN_DAYS = 4

# How far back to look. Long enough to be stable, short enough to follow a real
# change in their life. Counted per place: a place's last 21 days with her
# messages, not the last 21 calendar days.
WINDOW_DAYS = 21

# How far back to read at all. A place she left a month ago still has its
# routine; when she goes back, that is the starting point.
LOOKBACK_DAYS = 90

# A drift smaller than someone's own variability is not a drift.
MIN_DRIFT_MIN = 45

# Below this, the observation is not solid enough to raise with anyone. Four
# scattered days can produce a centre; it cannot produce a claim about someone's
# life.
MIN_DRIFT_CONFIDENCE = 0.5


def _tz(user_id: str) -> ZoneInfo:
    try:
        from memory.time_context import get_user_timezone
        return ZoneInfo(get_user_timezone(user_id))
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def _user_messages(user_id: str, days: int = WINDOW_DAYS) -> list:
    """Their own messages, with timestamps, over the window.

    User turns only: the companion's proactive messages would otherwise make it
    look as though someone was awake at 8am when it was the system talking.
    """
    try:
        from supabase_store import get_client
        db = get_client()
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        sess = (db.table("sessions").select("id")
                .eq("user_id", user_id).gte("updated_at", since)
                .execute()).data or []
        ids = [s["id"] for s in sess]
        if not ids:
            return []
        rows = (db.table("messages").select("timestamp,role")
                .in_("session_id", ids).eq("role", "user")
                .gte("timestamp", since).execute()).data or []
        return [r["timestamp"] for r in rows if r.get("timestamp")]
    except Exception as e:
        print(f"[Patterns] message read failed: {e}")
        return []


# A person's day does not end at midnight. Someone who messages at 00:20 has
# not started a new day — they are still up from the previous one. Grouping on
# the calendar date put that message at the START of Tuesday, so for a user who
# woke at 07:00 and went to bed around midnight the derived values came out as
# wake 03:40 and sleep 15:15: both nonsense, from data that was perfectly
# regular. The day boundary is therefore early morning, when almost nobody is
# awake.
DAY_BOUNDARY_HOUR = 4


def _by_local_day(stamps: list, tz: ZoneInfo) -> dict:
    """Group timestamps into local days that run 04:00 to 04:00.

    Minutes are measured from the boundary, not from midnight, so late-night
    times sort after evening ones instead of before morning ones. Callers get
    values back in 0..1439 via _to_clock.
    """
    days = defaultdict(list)
    for s in stamps:
        try:
            dt = datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(tz)
        except Exception:
            continue
        mins = dt.hour * 60 + dt.minute
        if dt.hour < DAY_BOUNDARY_HOUR:
            # belongs to yesterday, and sorts after yesterday's evening
            key  = dt.date() - timedelta(days=1)
            mins += 24 * 60
        else:
            key = dt.date()
        days[key].append(mins)
    return days


def _to_clock(mins: int) -> int:
    """Back to a real clock time after the boundary shift."""
    return int(mins) % (24 * 60)


def _centre_and_spread(values: list) -> tuple:
    """Median rather than mean: one 3am insomnia night should not move a wake
    time by an hour. Spread is the interquartile-ish range, in minutes."""
    if not values:
        return None, 0
    vals = sorted(values)
    centre = int(median(vals))
    if len(vals) < 3:
        return centre, abs(vals[-1] - vals[0])
    lo = vals[len(vals) // 4]
    hi = vals[(3 * len(vals)) // 4]
    return centre, int(hi - lo)


def _confidence(n_days: int, spread_min: int) -> float:
    """More days is better; a tighter routine is better. A fortnight of
    consistent mornings is near-certain; four scattered days is not."""
    if n_days < MIN_DAYS:
        return 0.0
    day_part    = min(n_days / 14.0, 1.0)
    spread_part = max(0.0, 1.0 - (spread_min / 180.0))    # 3h spread -> 0
    return round(min(day_part * 0.6 + spread_part * 0.4, 1.0), 2)


def _mins_to_time(m: Optional[int]) -> Optional[str]:
    if m is None:
        return None
    m = max(0, min(int(m), 24 * 60 - 1))
    return f"{m // 60:02d}:{m % 60:02d}:00"


def _time_to_mins(t) -> Optional[int]:
    if not t:
        return None
    try:
        parts = str(t).split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return None


# ── where she was, day by day ────────────────────────────────────────────────
#
# A routine belongs to a place. Her mornings in Surat and at her son's in
# Bengaluru are two routines, and mixing them gave one that was true of
# neither; the old answer to that was to stop judging change while she was
# away, which on 16 Oct had been the case for five weeks. Now each day is
# labelled with where she was, each place learns its own routine, and change
# is only ever judged against the same place.
#
# The profile holds only the stay in progress (current_location, arrived_at),
# so stays are kept in life_context.stays as they are seen, and closed when
# she is home again. Days before the first recorded stay count as home.


def _day(s) -> Optional[str]:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return None


def _stays(user_id: str):
    """(home, current place or None, [stays]) — and the stays log brought up
    to date with what the profile says now."""
    try:
        from supabase_store import get_client
        db = get_client()
        rows = (db.table("user_profile")
                .select("home_location,location,current_location,arrived_at,life_context")
                .eq("user_id", user_id).limit(1).execute()).data or []
    except Exception as e:
        print(f"[Patterns] stays read failed: {e}")
        return None, None, []
    if not rows:
        return None, None, []
    p = rows[0]
    home = p.get("home_location") or p.get("location")
    cur = p.get("current_location")
    away = bool(cur and cur != home)
    lc = p.get("life_context") if isinstance(p.get("life_context"), dict) else {}
    stays = [s for s in (lc.get("stays") or []) if isinstance(s, dict) and s.get("place")]
    today = datetime.now(timezone.utc).date().isoformat()
    changed = False

    open_ = [s for s in stays if not s.get("to")]
    if away:
        start = _day(p.get("arrived_at")) or today
        if not any(s["place"] == cur and s.get("from") == start for s in stays):
            for s in open_:                      # a new place closes the last
                s["to"] = start
            stays.append({"place": cur, "from": start, "to": None})
            changed = True
    else:
        for s in open_:                          # home again
            s["to"] = today
            changed = True
    if changed:
        lc["stays"] = stays[-20:]
        try:
            db.table("user_profile").update({"life_context": lc}) \
                .eq("user_id", user_id).execute()
            print(f"[Patterns] {user_id}: stays now {lc['stays']}")
        except Exception as e:
            print(f"[Patterns] stays write failed: {e}")
    return home, (cur if away else None), stays


def _place_on(day, home, stays) -> str:
    d = day.isoformat() if hasattr(day, "isoformat") else str(day)
    for s in stays:
        if s.get("from") and d >= s["from"] and (not s.get("to") or d < s["to"]):
            return s["place"]
    return home or "home"


def _derive(days: dict) -> list:
    """Wake, sleep and active window from one set of days."""
    firsts = [min(v) for v in days.values() if v]

    # A day's last message is only a sleep signal if it is plausibly evening.
    # On a quiet day where someone messaged once at 8am, that 8am is when they
    # stopped talking, not when they went to bed — counting it drags the centre
    # into the afternoon and inflates the spread past any usable threshold.
    EVENING_FROM = 18 * 60
    lasts = [max(v) for v in days.values() if v and max(v) >= EVENING_FROM]

    derived = []
    if len(days) < MIN_DAYS:
        return derived
    for kind, values in (("wake", firsts), ("sleep", lasts)):
        centre, spread = _centre_and_spread(values)
        if centre is None:
            continue
        derived.append({
            "kind":         kind,
            "label":        None,
            "observed_at":  _mins_to_time(_to_clock(centre)),
            "spread_min":   spread,
            "observations": len(values),
            "confidence":   _confidence(len(days), spread),
        })

    # How much of the day they are actually around for — the span between the
    # two, useful for knowing when NOT to reach out.
    if firsts and lasts:
        derived.append({
            "kind":         "active_window",
            "label":        None,
            "observed_at":  _mins_to_time(_to_clock(int(median(firsts)))),
            "spread_min":   int(median(lasts) - median(firsts)),
            "observations": len(days),
            "confidence":   _confidence(len(days), 0),
        })
    return derived


def observe(user_id: str) -> list:
    """Derive wake, sleep and active-window patterns, per place. The main row
    of each kind holds the routine of where she is now (or home's, while the
    place she is in has too few days); every place's own is kept beside it in
    by_place. Returns what it wrote."""
    tz     = _tz(user_id)
    stamps = _user_messages(user_id, days=LOOKBACK_DAYS)
    days   = _by_local_day(stamps, tz)
    home, now_place, stays = _stays(user_id)
    home = home or "home"

    by_place: dict = defaultdict(dict)
    for d, v in days.items():
        by_place[_place_on(d, home, stays)][d] = v
    # Each place's own recent days, not the calendar's last three weeks.
    by_place = {pl: dict(sorted(ds.items())[-WINDOW_DAYS:]) for pl, ds in by_place.items()}

    derived_by_place = {pl: {r["kind"]: r for r in _derive(ds)} for pl, ds in by_place.items()}
    print(f"[Patterns] {user_id}: days by place "
          + ", ".join(f"{pl}: {len(ds)}" for pl, ds in by_place.items())
          + f"; now in {now_place or home}")

    here = now_place or home
    use = derived_by_place.get(here) or {}
    if not use and here != home:
        use = derived_by_place.get(home) or {}     # too few days there yet
    if not use:
        n = len(by_place.get(here, {}))
        print(f"[Patterns] {user_id}: only {n} day(s) of data in {here}, need {MIN_DAYS}")
        return []

    out = []
    for kind, d in use.items():
        places = {pl: {k: v for k, v in dv[kind].items() if k in
                       ("observed_at", "spread_min", "observations", "confidence")}
                  for pl, dv in derived_by_place.items() if kind in dv}
        out.append(_upsert(user_id, d, here=here, home=home, places=places,
                           here_has_own=(here in derived_by_place)))
    return out


def _upsert(user_id: str, d: dict, here: str = "", home: str = "",
            places: Optional[dict] = None, here_has_own: bool = True) -> dict:
    """Write the observation WITHOUT touching what they declared.

    declared_at and observed_at are separate columns on purpose: recording what
    someone does must never erase what they said, or the divergence — the
    interesting part — is lost.
    """
    from supabase_store import get_client
    db = get_client()

    try:
        existing = (db.table("user_patterns").select("*")
                    .eq("user_id", user_id).eq("kind", d["kind"])
                    .is_("label", "null" if d["label"] is None else d["label"])
                    .limit(1).execute()).data or []
    except Exception:
        existing = []

    row = {
        "user_id":      user_id,
        "kind":         d["kind"],
        "label":        d["label"],
        "observed_at":  d["observed_at"],
        "spread_min":   d["spread_min"],
        "observations": d["observations"],
        "confidence":   d["confidence"],
        "last_seen":    datetime.now(timezone.utc).isoformat(),
        "updated_at":   datetime.now(timezone.utc).isoformat(),
    }

    prev = existing[0] if existing else None
    observed = _time_to_mins(d["observed_at"])
    at_home = (here == home) or not here

    # Each place keeps its own observation, and its own baseline: the first
    # confident routine seen there. Change away from home is judged against
    # that, never against home's declared times.
    old_places = (prev or {}).get("by_place") if isinstance((prev or {}).get("by_place"), dict) else {}
    new_places = {}
    for pl, obs in (places or {}).items():
        base = (old_places.get(pl) or {}).get("baseline_at")
        if not base and obs.get("confidence", 0) >= MIN_DRIFT_CONFIDENCE:
            base = obs.get("observed_at")
        new_places[pl] = {**obs, "baseline_at": base, "home": pl == home}
    for pl, obs in old_places.items():
        new_places.setdefault(pl, obs)            # a place not seen lately keeps its routine
    row["by_place"] = new_places
    row["place"] = here or home

    if at_home:
        declared = _time_to_mins(prev.get("declared_at")) if prev else None
    else:
        declared = (_time_to_mins((new_places.get(here) or {}).get("baseline_at"))
                    if here_has_own else None)

    if declared is not None and observed is not None:
        drift = observed - declared
        # Only a drift larger than their own variability counts. Someone whose
        # mornings range over two hours has not "drifted" by forty minutes.
        # Confidence gates this, not just spread. They measure different
        # things: spread is how variable someone is, confidence also accounts
        # for how few days it is based on. Four consistent days give spread 0
        # and confidence 0.26 — enough for the spread test to pass and not
        # nearly enough to tell someone their routine has changed.
        confident = d["confidence"] >= MIN_DRIFT_CONFIDENCE

        # Within the same place only. Her puja does not happen at 6:30 at
        # her son's house, and judging a visit against home would have told
        # a caregiver she was deteriorating while she was having a nice time.
        # Away, the comparison is with her own routine THERE (its baseline);
        # until that place has one, existing drift is left standing.
        if confident and abs(drift) >= max(MIN_DRIFT_MIN, d["spread_min"]):
            row["drift_min"] = drift
            if not (prev and prev.get("drift_since")):
                row["drift_since"] = datetime.now(timezone.utc).isoformat()
        else:
            row["drift_min"]   = None
            row["drift_since"] = None

    elif not at_home and not here_has_own:
        # Away, and too few days there for a routine of its own: nothing to
        # judge change against yet. Not frozen — it starts as soon as there is.
        row["drift_min"] = None
        row["drift_since"] = None

    def _write(r):
        if prev:
            # Never downgrade a declared or corrected row to "observed".
            if (prev.get("source") or "declared") == "observed":
                r["source"] = "observed"
            db.table("user_patterns").update(r).eq("id", prev["id"]).execute()
            r["id"] = prev["id"]
        else:
            r["source"] = "observed"
            created = db.table("user_patterns").insert(r).execute().data
            r["id"] = created[0]["id"] if created else None

    try:
        _write(row)
    except Exception as e:
        if "by_place" in str(e) or "place" in str(e):
            # Before the columns exist (patterns_by_place.sql): the main row
            # still updates.
            print(f"[Patterns] place columns missing, writing without: {str(e)[:80]}")
            row.pop("by_place", None)
            row.pop("place", None)
            _write(row)
        else:
            raise
    return row


def observe_all(min_days: int = MIN_DAYS) -> int:
    """Run for everyone with enough history. Cheap — no model calls."""
    try:
        from supabase_store import get_client
        rows = (get_client().table("user_memory").select("user_id")
                .execute()).data or []
    except Exception as e:
        print(f"[Patterns] user list failed: {e}")
        return 0
    n = 0
    for r in rows:
        try:
            if observe(r["user_id"]):
                n += 1
        except Exception as e:
            print(f"[Patterns] observe failed for {r.get('user_id')}: {e}")
    return n


def get_patterns(user_id: str) -> list:
    """Everything known about their day, declared and observed."""
    try:
        from supabase_store import get_client
        return (get_client().table("user_patterns").select("*")
                .eq("user_id", user_id).order("kind").execute()).data or []
    except Exception as e:
        print(f"[Patterns] read failed: {e}")
        return []

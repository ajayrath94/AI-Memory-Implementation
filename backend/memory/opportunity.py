"""
OPPORTUNITY — is this a moment worth speaking into, and how sure are we?

Three weeks of work on offers produced fifteen gates, every one of them a
reason to say NO: a cluster, a category, a settled check, a cooldown, a
weighted draw, a rhythm override, a declining filter, a weekday leaning,
good_moment, free hours, a learned hour, an idempotency key, a ninety-minute
gap, a daily budget, one-of-each-kind.

Not one message got through.

This asks the opposite question. Not "is there a reason to refuse" but "is
there an opportunity here, and how good is it". A number between 0 and 1,
with the parts visible, so a bad offer can be traced to the signal that
produced it.

WHAT IT READS, AND WHAT IT CANNOT
Most of the inputs already exist, scattered across the files that grew around
them — reply rates by hour, idle gaps, mood per session, the day's events,
recent topics, habit strength, festivals and observances, and what she did
with the last twenty offers.

Some do not exist at all. Session duration is not measured. Nor is
interruption frequency, nor the channel she is on, nor — for any offer — how
long it would take her or what it would cost her to act on it.

So every component returns a value AND a confidence, and None where nothing
measures it. A missing signal is reported as missing rather than defaulted to
a half, because a 0.5 invented in four places would dominate the three
numbers that are real.

    score 0.72, from 4 signals — 3 unmeasured

is an honest sentence. "0.61" alone is not.

NOTHING HERE DECIDES
It scores. The caller decides, and the budget and the spacing still have the
last word — someone who has not replied in a week should be hearing less
whatever the opportunity looks like.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

# Below this, say nothing. Not a threshold on quality so much as on
# confidence: a 0.5 drawn from one weak signal is a guess wearing a number.
WORTH_SAYING = 0.45

# How many signals before the score means anything at all.
ENOUGH_SIGNALS = 3


@dataclass
class Signal:
    """One input, its reading, and how much to trust it.

    value      0..1, or None when nothing measures this
    confidence 0..1 — how much evidence is behind the value
    why        a line a person can read
    """
    name: str
    value: Optional[float]
    confidence: float = 0.0
    why: str = ""

    @property
    def known(self) -> bool:
        return self.value is not None


@dataclass
class Opportunity:
    score: float = 0.0
    signals: List[Signal] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    subject: str = ""
    because: str = ""

    def explain(self) -> str:
        parts = [f"{s.name}={s.value:.2f}@{s.confidence:.0%}"
                 for s in self.signals if s.known]
        line = f"{self.score:.2f} from {len(parts)} signal(s)"
        if self.missing:
            line += f", {len(self.missing)} unmeasured"
        return line + (": " + ", ".join(parts) if parts else "")


def _db():
    from supabase_store import get_client
    return get_client()


# ── 1. availability ─────────────────────────────────────────────────────────

def _availability(user_id: str) -> List[Signal]:
    """Is she free, and is this an hour she is usually about?

    Two different things. The first is her day: a dose due, a meal, a walk.
    The second is history: whether she has ever answered at this hour.
    """
    out = []

    # Her day right now. This is the strongest signal there is, and it is
    # exact rather than inferred.
    try:
        from memory.day import events, _mins, _mins_now
        now = _mins_now(user_id)
        near = []
        for e in events(user_id) or []:
            due = _mins(e.get("due_at"))
            if due < 0:
                continue
            gap = abs(due - now)
            if gap <= 30:
                near.append((gap, e))
        if near:
            near.sort()
            gap, e = near[0]
            label = e.get("label") or e.get("kind") or "something"
            if (e.get("kind") or "") == "medication":
                # A tablet is not an opportunity and never becomes one.
                out.append(Signal("free_now", 0.0, 1.0,
                                  f"{label} is due in {gap} minutes"))
            else:
                # Near something is not busy — it is the moment an offer
                # belongs to. A bhajan before puja is better than a bhajan
                # at random.
                out.append(Signal("free_now", 0.7, 0.9,
                                  f"{label} in {gap} minutes"))
        else:
            # Absence of a reason to stay quiet is not a reason to
            # speak. Three absences — nothing on her day, nothing
            # hanging, nothing sent today — summed to 0.90, which read
            # as a strong opportunity built on no evidence at all.
            out.append(Signal("free_now", 0.5, 0.3,
                              "nothing on her day for half an hour"))
    except Exception as e:
        print(f"[Opportunity] day read failed: {e}")

    # Has she ever answered at this hour? Weak until there are weeks of it,
    # and honest about that.
    try:
        from memory.timing import replies_by_hour
        from zoneinfo import ZoneInfo
        from memory.declared import get_declared
        tz = ZoneInfo(get_declared(user_id).place.timezone)
        hour = datetime.now(tz).hour
        by = replies_by_hour(user_id) or {}
        r = by.get(hour)
        if r and r.get("sent", 0) >= 3:
            out.append(Signal("hour_history", round(r["rate"], 2),
                              min(1.0, r["sent"] / 12.0),
                              f"answered {r['answered']} of {r['sent']} "
                              f"at {hour}:00"))
        else:
            out.append(Signal("hour_history", None, 0.0,
                              f"nothing yet for {hour}:00"))
    except Exception as e:
        print(f"[Opportunity] hour history failed: {e}")

    # And how long since anything was said, either way.
    try:
        from memory.cadence import todays_ledger
        led = todays_ledger(user_id)
        mins = led.get("minutes_since")
        if mins is None:
            out.append(Signal("quiet_for", 0.7, 0.5, "nothing sent today"))
        else:
            # An hour is comfortable; ten minutes is not.
            v = max(0.0, min(1.0, mins / 120.0))
            out.append(Signal("quiet_for", round(v, 2), 0.9,
                              f"{mins} min since the last message"))
    except Exception as e:
        print(f"[Opportunity] ledger failed: {e}")

    return out


# ── 2. her state ────────────────────────────────────────────────────────────

def _state(user_id: str) -> List[Signal]:
    """How she is, as far as anything knows.

    The mood read runs at session end, so this is yesterday's reading on a
    day she has not finished talking. Confidence says so.
    """
    out = []

    try:
        rows = (_db().table("sessions")
                .select("valence,arousal,updated_at")
                .eq("user_id", user_id)
                .not_.is_("valence", "null")
                .order("updated_at", desc=True).limit(3).execute()).data or []
    except Exception as e:
        print(f"[Opportunity] mood read failed: {e}")
        rows = []

    if rows:
        v = float(rows[0].get("valence") or 0)
        try:
            when = datetime.fromisoformat(
                str(rows[0]["updated_at"]).replace("Z", "+00:00"))
            hours = (datetime.now(timezone.utc) - when).total_seconds() / 3600
        except Exception:
            hours = 24.0
        # A reading from this morning is worth something; one from Tuesday
        # is not.
        conf = max(0.1, min(0.9, 1.0 - hours / 24.0))
        # Low mood is not a reason to say nothing — it is a reason to say
        # something gentler. So this moves the score a little, not a lot.
        out.append(Signal("mood", round(0.5 + v / 3.0, 2), round(conf, 2),
                          f"valence {v:+.1f}, {hours:.0f}h ago"))
    else:
        out.append(Signal("mood", None, 0.0, "no reading"))

    # Is she mid-conversation? Then an unprompted message is absurd — she is
    # already here, and the reply should carry whatever this was.
    try:
        since = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        sess = (_db().table("sessions").select("id")
                .eq("user_id", user_id).gte("updated_at", since)
                .limit(3).execute()).data or []
        live = False
        for s in sess:
            got = (_db().table("messages").select("id")
                   .eq("session_id", s["id"]).eq("role", "user")
                   .gte("timestamp", since).limit(1).execute()).data or []
            if got:
                live = True
                break
        # A veto when she is here, and nothing at all when she is not —
        # it was contributing 1.0 at full confidence on every quiet hour
        # and dominating a thin score.
        if live:
            out.append(Signal("not_mid_chat", 0.0, 1.0, "she is writing now"))
        else:
            out.append(Signal("not_mid_chat", None, 0.0, "not mid-chat"))
    except Exception as e:
        print(f"[Opportunity] live check failed: {e}")

    return out


# ── 3. what is already open ─────────────────────────────────────────────────

def _open_threads(user_id: str) -> List[Signal]:
    """Something unfinished beats something new.

    A cold she mentioned yesterday, a plan she made, a question she asked
    and never got an answer to. If one of those is open, an offer about a
    song is the wrong thing to say.
    """
    out = []
    try:
        from memory.carry import yesterdays
        y = yesterdays(user_id)
        if y and y.get("carry") and y.get("status") not in ("confirmed",
                                                            "denied"):
            out.append(Signal("nothing_open", 0.2, 0.9,
                              f"unfinished: {y['carry'][:40]}"))
        else:
            # Neutral, not positive: nothing unfinished is the normal
            # state of a day, not a reason to speak into it.
            out.append(Signal("nothing_open", 0.5, 0.3, "nothing hanging"))
    except Exception as e:
        print(f"[Opportunity] carry read failed: {e}")
    return out


# ── 4. what she does, and when ──────────────────────────────────────────────

def _patterns(user_id: str, subject: str = "") -> List[Signal]:
    """Habit, recency, and whether today is a day for this.

    'Morning puja -> bhajan' is a stronger thing to know than 'she likes
    bhajans', and it is the difference between a suggestion and a moment.
    """
    out = []

    # Is today a day she keeps? Her observances know.
    try:
        from memory.observances import for_day
        d = for_day(user_id)
        if d.get("observes"):
            out.append(Signal("day_shape", 0.8, 0.9,
                              f"{d['because']} — {d['observes']}"))
        elif d.get("avoids"):
            out.append(Signal("day_shape", 0.6, 0.9, d["because"]))
    except Exception as e:
        print(f"[Opportunity] observances failed: {e}")

    # A rhythm due today is the strongest reason there is.
    try:
        from memory.rhythms import due_today
        due = due_today(user_id) or []
        if due:
            out.append(Signal("rhythm_today", 1.0, 0.9,
                              f"{due[0]['subject']} on {due[0]['weekday']}s"))
    except Exception as e:
        print(f"[Opportunity] rhythm failed: {e}")

    if subject:
        # How long since this one came up. Recent is worse, not better.
        try:
            rows = (_db().table("subject_mentions")
                    .select("happened_on")
                    .eq("user_id", user_id).ilike("subject", subject)
                    .order("happened_on", desc=True)
                    .limit(1).execute()).data or []
            if rows:
                last = date.fromisoformat(str(rows[0]["happened_on"])[:10])
                days = (date.today() - last).days
                v = 0.1 if days <= 2 else min(1.0, days / 21.0)
                out.append(Signal("recency", round(v, 2), 0.8,
                                  f"{subject} last came up {days}d ago"))
        except Exception as e:
            print(f"[Opportunity] recency failed: {e}")

    return out


# ── 5. how she has taken offers ─────────────────────────────────────────────

def _appetite(user_id: str) -> List[Signal]:
    """What she did with the last twenty, and whether she is tired of them.

    Not clicked-or-not. Ignored, declined, accepted — and how many have
    gone out lately, because the fourth offer in a week lands differently
    from the first.
    """
    out = []
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
        rows = (_db().table("suggestions")
                .select("reaction,created_at")
                .eq("user_id", user_id).gte("created_at", since)
                .order("created_at", desc=True).limit(20).execute()).data or []
    except Exception as e:
        print(f"[Opportunity] appetite read failed: {e}")
        rows = []

    if not rows:
        out.append(Signal("appetite", None, 0.0, "nothing offered yet"))
        # and fall through: fatigue is about what reached her this week,
        # which is a different question from how she has taken offers over
        # three. Returning here lost it on every user with no history.
        rows = []

    took = sum(1 for r in rows if r.get("reaction") == "accepted")
    said_no = sum(1 for r in rows if r.get("reaction") == "declined")
    ignored = sum(1 for r in rows if r.get("reaction") in (None, "no_response"))
    n = len(rows)
    v = (took * 1.0 + ignored * 0.3) / n
    out.append(Signal("appetite", round(min(1.0, v), 2),
                      min(1.0, n / 10.0),
                      f"{took} taken, {said_no} declined, {ignored} ignored "
                      f"of {n}"))

    # And fatigue: how many went out this week regardless of what she did.
    # What actually reached her. Eleven offers were decided in a week and
    # none delivered, and this read as her being bombarded — so the one
    # signal meant to stop pestering was suppressing the first message she
    # would ever have received.
    week = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    try:
        sent = (_db().table("proactive_events").select("created_at")
                .eq("user_id", user_id).eq("action", "RECOMMENDATION")
                .not_.is_("delivered_at", "null")
                .gte("created_at", week).execute()).data or []
    except Exception:
        sent = []
    recent = sent
    v2 = max(0.0, 1.0 - len(recent) / 5.0)
    out.append(Signal("not_fatigued", round(v2, 2), 0.9,
                      f"{len(recent)} actually sent in the last week"))
    return out


# ── 6. the thing being offered ──────────────────────────────────────────────

def _fit(user_id: str, subject: str, window_min: Optional[int]) -> List[Signal]:
    """Does this particular thing fit this particular moment?

    Most of what would belong here is not measured anywhere: how long it
    would take her, whether it needs preparation, whether she has to be
    somewhere. Those are reported missing rather than guessed, because four
    invented halves would outweigh the three signals that are real.
    """
    out = []
    if not subject:
        return out

    # Does it fit the gap? Only answerable when both are known, and the
    # effort side never is.
    out.append(Signal("effort_fit", None, 0.0,
                      "nothing measures what an offer costs her"))

    # Is it hers at all, and how strongly?
    try:
        rows = (_db().table("interest_clusters")
                .select("strength,event_count")
                .eq("user_id", user_id).ilike("label", subject)
                .limit(1).execute()).data or []
        if rows:
            s = float(rows[0].get("strength") or 0)
            n = int(rows[0].get("event_count") or 0)
            out.append(Signal("is_hers", round(min(1.0, s / 3.0), 2),
                              min(1.0, n / 6.0),
                              f"strength {s:.1f}, {n} mention(s)"))
    except Exception as e:
        print(f"[Opportunity] interest read failed: {e}")

    return out


# ── the score ───────────────────────────────────────────────────────────────

def score(user_id: str, subject: str = "",
          window_min: Optional[int] = None) -> Opportunity:
    """How good a moment is this? 0 to 1, with the parts kept.

    A weighted mean of what is known, weighted by confidence — so a strong
    signal with twenty observations behind it counts for more than a weak
    one with three, and a signal nobody measures counts for nothing instead
    of silently counting as a half.
    """
    sigs: List[Signal] = []
    sigs += _availability(user_id)
    sigs += _state(user_id)
    sigs += _open_threads(user_id)
    sigs += _patterns(user_id, subject)
    sigs += _appetite(user_id)
    sigs += _fit(user_id, subject, window_min)

    # A reading with no evidence behind it is not a reading. is_hers came
    # back 0.67 at 0% confidence — a strength with no mentions under it —
    # and still moved the mean.
    known = [s for s in sigs if s.known and s.confidence > 0.05]
    missing = [s.name for s in sigs if not s.known]

    # Some things are not votes. A tablet due in five minutes or a woman
    # mid-sentence is not outweighed by a good hour and a strong habit.
    for s in known:
        if s.name in ("free_now", "not_mid_chat") and s.value == 0.0:
            return Opportunity(0.0, sigs, missing, subject, s.why)

    if len(known) < ENOUGH_SIGNALS:
        return Opportunity(0.0, sigs, missing, subject,
                           f"only {len(known)} signal(s)")

    total = sum(s.confidence for s in known) or 1.0
    val = sum(s.value * s.confidence for s in known) / total

    best = max(known, key=lambda s: s.value * s.confidence)
    return Opportunity(round(val, 3), sigs, missing, subject, best.why)


def worth_saying(user_id: str, subject: str = "") -> bool:
    """The one-line answer, for a caller that does not want the parts."""
    return score(user_id, subject).score >= WORTH_SAYING

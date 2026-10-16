"""
PROACTIVE ENGINE
The decision brain the scheduler calls per user: given everything we know
right now (time, location, schedule, silence), should Nancy reach out — and
if so, with what? Decides only; delivery is a separate layer.

Precedence (first match wins, SILENCE is a valid answer):
  0. quiet gate    — late night, nothing fires unless safety-critical
  1. medication    — a due dose is time-critical
  2. safety        — away from home + night -> safety info
  3. silence       — unusually quiet for their rhythm -> gentle check-in
  4. explore       — away from home + day -> offer (LOW, on-ask really)
  5. silence(none) — nothing worth interrupting
"""


# How far ahead of now a scheduled dose counts as "this one". Wider than any
# due window get_due_schedule_items uses, so the dose being reminded about is
# always counted.
_DOSE_AHEAD_MIN = 90


def _dose_covered(user_id: str, label: str, now_min) -> bool:
    """Has every dose of this drug up to now already had its reminder?

    Counted rather than timed. Doses of the drug scheduled up to now, against
    reminders for it delivered today: Metformin at 08:00 and 20:00 is one
    dose by mid-morning and two by evening, so the second reminder goes and
    a repeat of the first does not. Counting needs no comparison between the
    scheduler's clock and the database's, which is what lets a simulated day
    and a real one behave the same.
    """
    try:
        from supabase_store import get_client
        from memory.day import _today, _mins, _mins_now
        db = get_client()
        if now_min is None:
            now_min = _mins_now(user_id)

        rows = (db.table("care_schedule").select("label,time_of_day")
                .eq("user_id", user_id).eq("type", "medication")
                .eq("active", True).execute()).data or []
        doses = sum(1 for r in rows
                    if str(r.get("label") or "").lower() == label.lower()
                    and 0 <= _mins(r.get("time_of_day")) <= now_min + _DOSE_AHEAD_MIN)
        if doses == 0:
            doses = 1     # it is due, so at least this one counts

        now, _, _ = _today(user_id)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timezone as _tz
        since = midnight.astimezone(_tz.utc).isoformat()
        sent = (db.table("proactive_events").select("id")
                .eq("user_id", user_id).eq("action", "MEDICATION_REMINDER")
                .eq("detail", label)
                .not_.is_("delivered_at", "null")
                .gte("created_at", since).execute()).data or []
        return len(sent) >= doses
    except Exception as e:
        # Unknown means remind. A duplicate reminder is a nuisance; a missed
        # dose is not.
        print(f"[Proactive] dose check failed for {label}: {e}")
        return False


# Her last message this recently, and she is mid-conversation.
CHATTING_MINUTES = 15


def _hm(v):
    try:
        h, m = str(v)[:5].split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _awake_minutes(user_id: str, gap: int, hour) -> "int | None":
    """Of the last `gap` minutes, how many she was awake for. None if her
    sleep and wake times are not known, and the caller keeps the raw gap.

    Walks back minute-blocks from now and leaves out whatever falls between
    her declared sleep and wake. A whole night is about eight hours, so this
    is the difference between a silence and a night's sleep.
    """
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from memory.declared import get_declared
        d = get_declared(user_id)
        sleep, wake = _hm(d.rhythm.sleep), _hm(d.rhythm.wake)
        if sleep is None or wake is None:
            sleep, wake = 22 * 60, 6 * 60
        now = datetime.now(ZoneInfo(d.place.timezone or "Asia/Kolkata"))
        now_min = (int(hour) * 60) if hour is not None else now.hour * 60 + now.minute
    except Exception as e:
        print(f"[Proactive] awake-gap read failed: {e}")
        return None

    def asleep(m):
        m %= 1440
        if sleep > wake:                     # 22:00 -> 06:00, across midnight
            return m >= sleep or m < wake
        return sleep <= m < wake

    # Fifteen-minute steps: plenty for a six-hour threshold, and a day at most.
    awake, step = 0, 15
    for back in range(0, min(int(gap), 48 * 60), step):
        if not asleep(now_min - back):
            awake += step
    return awake


# Messages that wait for her. Medicine and safety are never held back.
_WAITS = ("GREETING", "BOUNDARY", "RECOMMENDATION", "EXPLORE_OFFER", "CHECK_IN")
UNANSWERED_LIMIT = 2
# Waiting must not mean silent forever. On 16 October she missed the greeting
# and the puja boundary, and nothing else went out all day: no lunch, no
# dinner, and the silence check-in itself was held back by the silence.
# After this long with nothing delivered, one boundary or check-in may go.
REOPEN_AFTER_MIN = 240
_HOLD_WHEN_REOPENED = ("RECOMMENDATION", "EXPLORE_OFFER", "GREETING")
_REOPENED = {}


def _since_last_wait(user_id: str):
    """Minutes since a message of the waiting kind was last delivered."""
    try:
        from datetime import datetime, timezone
        from supabase_store import get_client
        rows = (get_client().table("proactive_events").select("delivered_at")
                .eq("user_id", user_id).in_("action", list(_WAITS))
                .not_.is_("delivered_at", "null")
                .order("delivered_at", desc=True).limit(1).execute()).data or []
        if not rows:
            return None
        d = datetime.fromisoformat(str(rows[0]["delivered_at"]).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).total_seconds() / 60
    except Exception as e:
        print(f"[Proactive] last-wait read failed: {e}")
        return None


def _unanswered(user_id: str, minutes_since_last) -> int:
    """How many non-medicine messages went out since she last wrote.

    On 14 October she was sent a greeting, a puja boundary, an offer and a
    breakfast boundary between 06:31 and 09:31 with no reply to any of them.
    Each was allowed on its own; nothing counted the silence after them.
    """
    try:
        from datetime import datetime, timezone, timedelta
        from supabase_store import get_client
        now = datetime.now(timezone.utc)
        mins = minutes_since_last if minutes_since_last is not None else 18 * 60
        since = (now - timedelta(minutes=int(mins))).isoformat()
        rows = (get_client().table("proactive_events").select("action")
                .eq("user_id", user_id).gte("delivered_at", since)
                .in_("action", list(_WAITS)).limit(20).execute()).data or []
        return len(rows)
    except Exception as e:
        print(f"[Proactive] unanswered count failed: {e}")
        return 0


def _proactive_check_inner(user_id: str, override_hour: int = None) -> dict:
    from memory.time_context import time_context, _slot, _mode
    from memory.care_reader import get_due_schedule_items

    tc = time_context(user_id)
    if override_hour is not None:
        # testing: recompute slot/mode as if it were override_hour
        tc = dict(tc)
        tc["hour"] = override_hour
        tc["slot"] = _slot(override_hour)
        tc["mode"] = _mode(override_hour, 0)
        # unusual_silence was computed inside time_context() against the REAL
        # hour, so without this the simulated slot and the silence flag
        # disagree — you get slot=late_night with the daytime 6h threshold,
        # a state that cannot occur in production.
        _gap = tc.get("minutes_since_last")
        if _gap is None:
            tc["unusual_silence"] = False
        elif tc["slot"] == "late_night":
            tc["unusual_silence"] = False
        elif tc["slot"] == "night":
            tc["unusual_silence"] = _gap > 12 * 60
        else:
            tc["unusual_silence"] = _gap > 6 * 60
    slot   = tc.get("slot")
    mode   = tc.get("mode")            # explore | safety
    hour   = tc.get("hour")
    quiet  = tc.get("unusual_silence")
    gap    = tc.get("minutes_since_last")
    raw_gap = gap                      # since her last word, night included

    # Quiet while AWAKE, not quiet since she last spoke. The night counted:
    # her last word at 18:32, and at 06:13 the next morning "quiet ~11h
    # during waking hours" sent "subah subah kya dekhne ka irada hai, koi
    # purani movie?" before her puja, before the greeting — the first check
    # of every morning looked like a silence, because she had been asleep.
    if quiet and gap:
        awake_gap = _awake_minutes(user_id, gap, hour)
        if awake_gap is not None:
            gap = awake_gap
            quiet = awake_gap > 6 * 60

    # location context
    away = False
    try:
        from supabase_store import get_client
        rows = (get_client().table("user_context").select("last_lat,last_lng,home_lat,home_lng")
                .eq("user_id", user_id).limit(1).execute()).data or []
        if rows:
            r = rows[0]
            from routes.context import _km_between, NEW_PLACE_KM
            d = _km_between(r.get("last_lat"), r.get("last_lng"),
                            r.get("home_lat"), r.get("home_lng"))
            away = d > NEW_PLACE_KM if d >= 0 else False
    except Exception as e:
        print(f"[Proactive] location check failed: {e}")

    def decision(action, reason, detail="", priority="medium"):
        return {
            "user_id": user_id, "action": action, "reason": reason,
            "detail": detail, "priority": priority,
            "slot": slot, "mode": mode, "away_from_home": away,
        }

    # ── 1. Medication due (time-critical, fires even at night) ──
    try:
        due = get_due_schedule_items(user_id, hour=hour)
    except Exception:
        due = []
    meds = [d for d in due if d.get("type") == "medication"]
    if meds:
        # Sorted, and one drug at a time. The idempotency key includes the
        # detail, so "Thyroid, BP tablet" and "BP tablet, Thyroid" were two
        # different keys — she was told four times this morning to take two
        # tablets, because the batch changed shape as each dose came due and
        # the list was never in a stable order.
        #
        # One reminder per drug per day. Two tablets an hour apart are two
        # reminders an hour apart, which is what she actually needs.
        #
        # And one reminder per DOSE, decided here. A dose is "due" for every
        # tick inside its window, so Calcium at 08:30 was due at the 08:00
        # tick and again at 09:00, and Amlodipine at 19:30 at 19:00 and
        # 20:00. Nothing here remembered the first; the only guard was
        # log_decision's per-day key further down, which a direct caller
        # never reaches and which would also swallow a second daily dose
        # of the same drug.
        now_min = (hour * 60) if hour is not None else None
        names = sorted({m.get("label", "dawai") for m in meds})
        pending = [n for n in names if not _dose_covered(user_id, n, now_min)]
        if pending:
            d = decision("MEDICATION_REMINDER", "dose_due", pending[0], "high")
            # Which dose, not only which drug. log_decision keys on it, so
            # the evening Metformin is no longer a "duplicate" of the
            # morning one.
            d["dose_at"] = next((str(m.get("time_of_day") or "")[:5]
                                 for m in meds
                                 if m.get("label", "dawai") == pending[0]), "")
            return d
        # Every due dose has had its reminder. Fall through: something else
        # may still be worth saying this hour.

    # ── 0. Quiet gate — deep night, nothing non-critical ──
    if slot == "late_night":
        # exception: away from home at night -> safety still matters
        if away:
            return decision("SAFETY_INFO", "away_at_night",
                            "unfamiliar place after dark", "high")
        return decision("SILENCE", "late_night_quiet")

    # ── 2. Safety — away from home + night mode ──
    if away and mode == "safety":
        return decision("SAFETY_INFO", "away_night_mode",
                        "unfamiliar place, night", "high")

    # ── 2.4 Waiting for her ──
    # Two messages she has not answered is enough for OFFERS. Boundaries
    # (breakfast, lunch, dinner follow-ups) and check-ins are her day, not
    # an offer, and still go: on 16 Oct holding them meant no breakfast, no
    # lunch and no silence check-in after she missed two messages.
    _REOPENED.pop(user_id, None)
    unanswered = _unanswered(user_id, raw_gap) if override_hour is None else 0
    if unanswered >= UNANSWERED_LIMIT:
        # Mark only; the wrapper below holds offers and greetings.
        _REOPENED[user_id] = unanswered
        print(f"[Proactive] {user_id}: {unanswered} unanswered -> "
              f"offers held, boundaries/check-ins still go")

    # ── 2.5 Morning greeting ──
    # Before the silence check-in on purpose. Someone quiet since yesterday
    # evening would otherwise be met with "kahan gayab ho gaye" at seven in the
    # morning, which is a reproach dressed as concern — where a greeting asks
    # nothing and is the right first thing to read.
    try:
        from memory.greeting import due as greeting_due
        if greeting_due(user_id):
            return decision("GREETING", "morning", "", "low")
    except Exception as e:
        print(f"[Proactive] greeting check failed: {e}")

    # She is talking with Nancy right now. A push arriving in the middle of a
    # conversation is absurd — the chat reply already folds in what is due
    # (context_builder._due_now) — so nothing but a tablet is pushed while
    # she is here. If she goes quiet, the next pass can still send it.
    chatting = gap is not None and gap < CHATTING_MINUTES

    # ── 2.6 A boundary — something finished, something coming ──
    # Before the silence check-in and before a recommendation: a message that
    # refers to her actual day is better than either, and an offer inside a
    # boundary is invited rather than interrupting.
    try:
        from memory.day import rebuild as day_rebuild, boundary
        day_rebuild(user_id)
        # The hour that was asked about, not the wall clock. override_hour
        # exists so a pass can be run for nine in the morning, and boundary()
        # takes now_min — it just was not given one, so every simulated hour
        # was judged against the real time and nothing ever matched.
        #
        # Fifth time today something decided upstream was re-derived
        # downstream and came back different.
        b = None if chatting else boundary(
            user_id, now_min=(hour * 60) if hour is not None else None)
        if b:
            label = ((b.get("done") or b.get("next") or {}).get("label") or "")
            return decision("BOUNDARY", "day_boundary", label, "low")
    except Exception as e:
        print(f"[Proactive] boundary check failed: {e}")

    # ── 3. Unusual silence -> gentle check-in ──
    if quiet:
        hrs = gap // 60 if gap else 0
        return decision("CHECK_IN", "unusual_silence",
                        f"quiet ~{hrs}h during waking hours", "medium")

    # ── 4. Explore — away + day (LOW; really on-ask) ──
    if away and mode == "explore":
        return decision("EXPLORE_OFFER", "away_daytime",
                        "new place, daytime", "low")

    # ── 5. Something they might enjoy ──
    #
    # Recommendations previously only reached someone who was away from home in
    # daylight (EXPLORE_OFFER above), which is rare — so the whole suggestion
    # loop had almost nothing to work on. This offers one when there is
    # something worth offering and the hour is sociable.
    #
    # Frequency is capped by log_decision, which is idempotent per user/day/
    # action: at most one RECOMMENDATION a day however often the heartbeat
    # runs. Deliberately not mornings (they are getting the day started) or
    # night (winding down).
    # Is she in a stretch of her own day with nothing in it?
    #
    # Not a slot and not a learned hour. slot in (midday, afternoon,
    # evening) excluded her 09:30 to 13:00 — the longest gap she has — and
    # timing.good_moment, which replaced it, computed her free hours as 10,
    # 11 and 15 while the hours she actually answers at are 9, 13 and 18.
    #
    # windows.py takes the gaps from her schedule and shuts the ones she has
    # spoken for: "thoda aaram karungi" closes the afternoon, whatever the
    # schedule says.
    try:
        from memory.windows import current as _window_now
        win = _window_now(user_id)
    except Exception as _we:
        print(f"[Proactive] window read failed: {_we}")
        win = None

    # Not while she is talking. An offer pushed into a conversation she is
    # having is an interruption, whatever it offers.
    if win and chatting:
        return decision("SILENCE", "chatting_now")

    # One per window. The window is the unit — with no spacing rule left,
    # every tick inside an open stretch could send, and two offers went
    # out an hour apart on the first day it worked.
    if win:
        try:
            from memory.offers import offered_in_window
            if offered_in_window(user_id, win):
                return decision("SILENCE", "already_offered_this_window")
        except Exception as _oe:
            print(f"[Proactive] window check failed: {_oe}")

    if win:
        # Only inside an open window, because choosing costs two model
        # calls and sixty ticks a day would pay it sixty times.
        try:
            from memory.offers import choose as _choose
            # The hour too, or _fits has nothing to judge against and a
            # film meant for the evening is offered at eleven.
            from memory.day import _mins_now as _mn
            offer = _choose(user_id, win, _mn(user_id))
        except Exception as _oe:
            print(f"[Proactive] offer failed: {_oe}")
            offer = None

        if offer:
            d = decision("RECOMMENDATION", "something_new", offer.what, "low")
            # Carried, not looked up again — the composer ran
            # pick_suggestion a second time, got None, and every block
            # hanging off it was skipped. The prompt reached the model
            # containing the weather and nothing else.
            d["offer"] = offer
            d["window"] = win
            return d

    # ── 6. Nothing worth interrupting ──
    return decision("SILENCE", "nothing_pressing")


def proactive_check(user_id: str, override_hour: int = None) -> dict:
    """The check, with one rule on top: while she hasn't answered two
    messages, offers and greetings are held (logged as SILENCE with its own
    key); boundaries, check-ins and medicine go as usual."""
    r = _proactive_check_inner(user_id, override_hour)
    if user_id in _REOPENED and isinstance(r, dict) \
            and r.get("action") in _HOLD_WHEN_REOPENED:
        print(f"[Proactive] {user_id}: waiting for her, holding {r.get('action')}")
        r = dict(r, action="SILENCE", reason="waiting_for_her",
                 detail="waiting_for_her", priority="medium")
    _REOPENED.pop(user_id, None)
    if override_hour is None and isinstance(r, dict):
        _trace(user_id, r)
    return r


# One TRACE row each time the engine's decision for her changes, so a day
# can be read back: "held as SILENCE:waiting_for_her from 07:02 to 14:28".
# On 16 Oct that hold left no trace at all. Its own action, so nothing that
# counts sent messages, offers or boundaries ever sees these rows.
_LAST_DECISION = {}


def _trace(user_id: str, r: dict):
    key = (r.get("action"), r.get("reason"), str(r.get("detail") or ""))
    if _LAST_DECISION.get(user_id) == key:
        return
    _LAST_DECISION[user_id] = key
    try:
        from datetime import datetime, timezone
        from supabase_store import get_client
        now = datetime.now(timezone.utc)
        get_client().table("proactive_events").insert({
            "user_id": user_id, "action": "TRACE",
            "reason": f"{key[0]}:{key[1]}"[:200], "detail": key[2][:200],
            "priority": "low", "slot": r.get("slot"), "mode": r.get("mode"),
            "away_from_home": bool(r.get("away_from_home")), "outcome": "trace",
            "idempotency_key": f"{user_id}:{now.isoformat()}:TRACE",
        }).execute()
    except Exception as e:
        print(f"[Proactive] trace write failed: {e}")

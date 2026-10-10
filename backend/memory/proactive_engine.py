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


def proactive_check(user_id: str, override_hour: int = None) -> dict:
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
            return decision("MEDICATION_REMINDER", "dose_due", pending[0], "high")
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
        b = boundary(user_id, now_min=(hour * 60) if hour is not None else None)
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

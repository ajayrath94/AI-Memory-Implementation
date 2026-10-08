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
        names = sorted(m.get("label", "dawai") for m in meds)
        return decision("MEDICATION_REMINDER", "dose_due", names[0], "high")

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
    if slot in ("midday", "afternoon", "evening"):
        try:
            from memory.suggestions import pick_suggestion
            pick = pick_suggestion(user_id)
        except Exception as e:
            print(f"[Proactive] pick_suggestion failed: {e}")
            pick = None
        # No pick means nothing they have shown they like, or everything has
        # been offered recently. Say nothing rather than invent something.
        if pick:
            # At her hour, not fifteen minutes after a boundary.
            #
            # Six offers were decided over three days and none sent: the
            # cadence gate wants ninety minutes since the last message, and
            # every one was decided in the shadow of a boundary. An offer
            # needs its own moment, and which moment is learnable — she has
            # answered at some hours and not others.
            try:
                from memory.timing import good_moment
                if not good_moment(user_id):
                    return decision("SILENCE", "not_her_hour_for_offers",
                                    "", "low")
            except Exception as _te:
                print(f"[Timing] check failed: {_te}")

            return decision("RECOMMENDATION", "something_they_like",
                            pick["label"], "low")

    # ── 6. Nothing worth interrupting ──
    return decision("SILENCE", "nothing_pressing")

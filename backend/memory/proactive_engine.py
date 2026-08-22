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
        labels = ", ".join(m.get("label", "dawai") for m in meds)
        return decision("MEDICATION_REMINDER", "dose_due", labels, "high")

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
            return decision("RECOMMENDATION", "something_they_like",
                            pick["label"], "low")

    # ── 6. Nothing worth interrupting ──
    return decision("SILENCE", "nothing_pressing")

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

    # ── 5. Nothing worth interrupting ──
    return decision("SILENCE", "nothing_pressing")

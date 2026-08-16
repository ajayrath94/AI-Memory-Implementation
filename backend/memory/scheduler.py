"""
SCHEDULER
The heartbeat. Wakes periodically, asks the proactive engine "does anything
fire?" per user, then LOGS the decision (idempotent per user/day/action).
Decide-and-log only; delivery (FCM) is a separate layer. The debug endpoint
stays log-free; only run_scheduler_pass(dry_run=False) writes to the log.
"""
from datetime import datetime, timezone


def _active_user_ids() -> list:
    try:
        from supabase_store import get_client
        rows = (get_client().table("user_context").select("user_id").execute()).data or []
        return [r["user_id"] for r in rows if r.get("user_id")]
    except Exception as e:
        print(f"[Scheduler] user list failed: {e}")
        return []


def run_scheduler_pass(dry_run: bool = False) -> dict:
    """One pass over all users. dry_run decides but does NOT log."""
    from memory.proactive_engine import proactive_check
    from memory.proactive_log import log_decision


    # Memory backstop: summarize sessions idle past the continuation window that
    # never got summarized (users who didn't return to trigger it normally).
    if not dry_run:
        try:
            from memory.user_memory_store import summarize_idle_sessions
            summarize_idle_sessions()
        except Exception as e:
            print(f"[Scheduler] backstop failed: {e}")

    users = _active_user_ids()
    # Track 2 distillation: clean+merge clusters for active users (vector+LLM
    # pass), on the heartbeat, off the hot path. Early-outs for <2 clusters.
    if not dry_run:
        for _uid in _active_user_ids():
            try:
                from memory.cluster_cleaner import clean_clusters
                clean_clusters(_uid)
            except Exception as _e:
                print(f"[Scheduler] cluster clean failed for {_uid}: {_e}")
    # Fire due reminders — the reactive engine delivering prospective memory.
    # A reminder becomes a proactive nudge via the existing proactive channel;
    # mark_fired prevents re-delivery. Reminders are exact + costly-if-missed,
    # so this runs deterministically every heartbeat.
    if not dry_run:
        try:
            from memory.reminder_engine import get_due_reminders, mark_nudge_fired
            from memory.proactive_log import log_decision
            for _item in get_due_reminders():
                _rem = _item["reminder"]
                log_decision({
                    "user_id": _rem["user_id"], "action": "REMINDER",
                    "reason": "scheduled reminder due",
                    "detail": _item.get("message") or _rem.get("what"),
                    "priority": "HIGH",
                })
                mark_nudge_fired(_rem["id"], _item["nudge_index"])
                try:
                    from memory.push_sender import send_push
                    send_push(
                        _rem["user_id"],
                        title="Nancy",
                        body=_item.get("message") or _rem.get("what") or "You have a reminder",
                        data={"type": "reminder", "reminder_id": _rem["id"]},
                    )
                except Exception as _pe:
                    print(f"[Push] reminder push failed: {_pe}")
                print(f"[Reminder] fired nudge for {_rem.get('what')} ({_rem['user_id']})")
        except Exception as _e:
            print(f"[Scheduler] reminder firing failed: {_e}")
    # Caregiver alerts — detect concerning conditions (health cluster strength,
    # low session valence) and email the caregiver. run_alert_engine has a 24h
    # dedup so running every pass is safe (only emails genuinely new alerts).
    if not dry_run:
        for _uid in users:
            try:
                from memory.alert_engine import run_alert_engine
                _r = run_alert_engine(_uid)
                if _r.get("sent"):
                    print(f"[Alerts] sent {_r.get('sent')} alert(s) for {_uid}")
            except Exception as _e:
                print(f"[Scheduler] alert check failed for {_uid}: {_e}")

    results = []

    for uid in users:
        try:
            decision = proactive_check(uid)
            action = decision.get("action")
            entry = {
                "user_id": uid, "action": action,
                "reason": decision.get("reason"), "detail": decision.get("detail"),
            }
            if not dry_run:
                logged = log_decision(decision)
                entry["logged"]    = logged.get("logged")
                entry["duplicate"] = logged.get("duplicate")
            results.append(entry)
        except Exception as e:
            print(f"[Scheduler] check failed for {uid}: {e}")
            results.append({"user_id": uid, "error": str(e)})

    fired = [r for r in results if r.get("action") and r["action"] != "SILENCE"]
    return {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "checked": len(users), "would_fire": len(fired),
        "dry_run": dry_run, "results": results,
    }

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

    users = _active_user_ids()
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

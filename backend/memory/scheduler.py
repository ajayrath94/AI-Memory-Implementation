"""
SCHEDULER
The heartbeat. Wakes periodically, asks the proactive engine "does anything
fire?" per user, then LOGS the decision (idempotent per user/day/action).
Decide-and-log only; delivery (FCM) is a separate layer. The debug endpoint
stays log-free; only run_scheduler_pass(dry_run=False) writes to the log.
"""
from datetime import datetime, timezone


def _active_user_ids() -> list:
    """Users the heartbeat should consider.

    This used to read user_context, which is the LOCATION table — written only
    when the app reports GPS. That made proactive outreach and caregiver alerts
    silently conditional on location permission: someone who declined it was
    invisible to both. For an eldercare product that is the wrong dependency —
    a person who won't share their location still needs their daughter told when
    they're declining.

    user_memory is the honest source: a row exists once a session has been
    summarized, which is exactly the population there is anything to be
    proactive about.
    """
    try:
        from supabase_store import get_client
        # Dormant users cost LLM calls on every heartbeat for cluster cleaning
        # and alert detection, and there is nothing new to detect. Someone who
        # comes back after months re-enters the list on their next session.
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        rows = (get_client().table("user_memory")
                .select("user_id,updated_at")
                .gte("updated_at", cutoff)
                .execute()).data or []
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

                # The thread ages. Cache after seven days, a day's note after
                # fourteen without being mentioned — and nothing was calling
                # this, so nothing aged at all.
                from memory.thread import sweep as _thread_sweep
                _thread_sweep(_uid)

                # And what keeps coming back becomes knowledge.
                #
                # Three distinct days in a fortnight, or in a month for a
                # slower rhythm. The threshold is a guess, but a wrong
                # promotion is cheap — a cluster at strength 0.8 that is
                # rarely drawn, and cluster_cleaner merges duplicates on this
                # same pass. A week of dry-run would have been a week of not
                # learning her habits.
                from memory.promotion import review as _promotion_review
                _promotion_review(_uid, dry_run=False)
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
                    from memory.persona_names import get_companion_name
                    send_push(
                        _rem["user_id"],
                        title=get_companion_name(_rem["user_id"]),
                        body=_item.get("message") or _rem.get("what") or "You have a reminder",
                        data={"type": "reminder", "reminder_id": _rem["id"]},
                    )
                except Exception as _pe:
                    print(f"[Push] reminder push failed: {_pe}")
                print(f"[Reminder] fired nudge for {_rem.get('what')} ({_rem['user_id']})")
        except Exception as _e:
            print(f"[Scheduler] reminder firing failed: {_e}")
    # Refresh observed routines. Cheap — no model calls, just timestamps —
    # and it needs to accumulate over weeks before it says anything useful.
    if not dry_run:
        try:
            from memory.patterns import observe_all
            n = observe_all()
            if n:
                print(f"[Patterns] refreshed routines for {n} user(s)")
        except Exception as e:
            print(f"[Scheduler] pattern observation failed: {e}")

    # Close suggestions nobody answered. Silence is weak evidence on its own,
    # but a run of it says the suggestions are landing badly.
    if not dry_run:
        try:
            from memory.suggestions import expire_stale
            n = expire_stale()
            if n:
                print(f"[Suggest] expired {n} unanswered suggestion(s)")
        except Exception as e:
            print(f"[Scheduler] suggestion expiry failed: {e}")

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

                # Deliver it. The engine was decide-and-log only, so every
                # CHECK_IN ever computed was written to proactive_events and
                # then dropped — the user never heard from anyone. log_decision
                # is idempotent per user/day/action, so `duplicate` is the
                # cadence guard: at most one of each kind per day, however
                # often the heartbeat runs.
                if (action and action != "SILENCE"
                        and (not logged.get("logged") or logged.get("duplicate"))):
                    # Logged-but-duplicate looks identical to held-by-cadence
                    # from the outside: the row says "decided" and nothing
                    # says why it stopped there.
                    print(f"[Scheduler] {uid}: {action} not sent — "
                          f"duplicate={logged.get('duplicate')}")

                if (action and action != "SILENCE"
                        and logged.get("logged") and not logged.get("duplicate")):
                    # log_decision's idempotency is per user/day/ACTION, not
                    # per subject — so the first recommendation of the day
                    # logs and every later one is a duplicate of it, whatever
                    # it was going to offer. Three were decided one morning,
                    # Kishore Kumar then Shakira then South Indian, and the
                    # second and third were dropped as repeats of the first.
                    #
                    # Which means a day's offer rests entirely on the first
                    # attempt: if that one is held for any reason, there is no
                    # second chance until tomorrow. What it cannot see is whether she is replying at
                    # all: someone who has not answered in a week should be
                    # hearing less, not the same amount forever. Checked before
                    # composing so a held message costs no model call.
                    try:
                        from memory.cadence import may_send
                        gate = may_send(uid, action)
                    except Exception as _ge:
                        print(f"[Cadence] gate failed: {_ge}")
                        gate = {"allow": True, "reason": "gate_error"}
                    if not gate["allow"]:
                        print(f"[Scheduler] {uid}: {action} held — {gate['reason']}")
                        try:
                            from memory.proactive_log import record_outcome
                            if logged.get("id"):
                                record_outcome(logged["id"],
                                               "held:" + str(gate["reason"])[:40])
                        except Exception:
                            pass
                        continue

                    try:
                        from memory.schedule_engine import generate_proactive_script
                        from memory.push_sender import send_push
                        from memory.persona_names import get_companion_name

                        try:
                            _r = generate_proactive_script(
                                uid, action=action,
                                detail=str(decision.get('detail') or ''))
                        except Exception as _ge:
                            # "no script, skipped" was hiding the reason.
                            print(f"[Proactive] compose failed for {uid}: {_ge}")
                            _r = None
                        script = (_r or {}).get("script", "")
                        if not script:
                            # Five recommendations were decided and logged on
                            # 23 September and none delivered, while every
                            # boundary that day went out. Composing them by
                            # hand works, so the failure only appears in the
                            # scheduler's own pass — and nothing recorded why.
                            print(f"[Proactive] {uid}: {action} composed "
                                  f"nothing — reason={(_r or {}).get('reason')} "
                                  f"slot={(_r or {}).get('slot')}")
                        if script:
                            # Write it to her session before pushing. A
                            # proactive message currently exists only on the
                            # lock screen — she reads it, opens the app, and
                            # finds an empty chat, so the thing she just read
                            # has vanished. It also belongs in the history:
                            # the companion said it, and the next reply may be
                            # about it.
                            try:
                                from supabase_store import (session_for,
                                                            save_message)
                                sess = session_for(uid)
                                save_message(sess["id"], "assistant", script,
                                             "gemini-flash-latest")
                            except Exception as _se:
                                print(f"[Proactive] session write failed: {_se}")

                            n = send_push(
                                uid,
                                title=get_companion_name(uid),
                                body=script,
                                data={"type": "proactive", "action": action,
                                      "reason": decision.get("reason")},
                            )
                            entry["delivered"] = n
                            print(f"[Proactive] {action} sent to {uid}: {script[:60]}")

                            if n:
                                # record_outcome("delivered") has existed since
                                # the beginning and nothing called it, so every
                                # event stayed outcome=decided with
                                # delivered_at null — and the cadence ledger,
                                # which counts delivered events, was
                                # permanently empty. Spacing and budget never
                                # applied to anyone, which is why two check-ins
                                # arrived an hour apart.
                                try:
                                    from memory.proactive_log import record_outcome
                                    if logged.get("id"):
                                        record_outcome(logged["id"], "delivered")
                                except Exception as _re:
                                    print(f"[Proactive] delivery stamp failed: {_re}")

                                # And a boundary is spent once it has actually
                                # gone out, not when it was composed.
                                if action == "BOUNDARY":
                                    try:
                                        from memory.day import boundary as _b, set_status as _ss
                                        _bd = _b(uid)
                                        if _bd and _bd.get("done"):
                                            _ss(_bd["done"]["id"], "sent")
                                    except Exception as _be:
                                        print(f"[Day] mark failed: {_be}")
                        else:
                            entry["delivered"] = 0
                            print(f"[Proactive] {action} for {uid} — no script, skipped")
                    except Exception as _pe:
                        entry["delivered"] = 0
                        print(f"[Proactive] delivery failed for {uid}: {_pe}")

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

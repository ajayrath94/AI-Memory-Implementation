"""
CADENCE — how often to speak, and when to stop.

Everything until now assumed scarcity: one message a day, so each had to earn
its place. A talkative companion inverts the constraint, and inverts the failure
mode with it. Scarcity risks being absent. Talkativeness risks being annoying —
and annoying is what gets an app deleted by someone who finds notifications
stressful.

So this exists to make being annoying hard.

THE ONE MECHANISM THAT MATTERS
The budget moves with whether she is actually replying. Six messages a day for
someone who answers most of them, one for someone who has not replied in three
days, none after a week — at which point the caregiver view says so, because
someone who has stopped answering entirely is a signal rather than a delivery
problem.

A companion that keeps talking into silence is the thing that feels like spam.
Everything else here degrades gracefully; this does not.

THE LOOP WAS OPEN
record_outcome() has existed since the beginning, with a docstring explaining
that without it we would know what we SENT but not what LANDED. Nothing ever
called it: 0 of 33 events had responded_at set. So the budget had nothing to
read, and this file starts by closing that.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

# A reply within this long counts as a reply TO the message. Longer and she is
# starting a conversation rather than answering one — which is good, but it is
# not evidence that the message landed.
REPLY_WINDOW_HOURS = 6

# Two in ten minutes reads as malfunction.
MIN_GAP_MINUTES = 90

BASE_BUDGET = 4

# Kinds that are conversation, and therefore budgeted. Care is not: a
# medication reminder must never be dropped because the companion has already
# chatted enough today.
# Conversation is what backs off when she stops answering. The day's STRUCTURE
# does not: a greeting, a boundary and a reminder are the shape of her day, and
# someone who has stopped replying — possibly because something is wrong — is
# the last person who should lose it.
CONVERSATIONAL = {"CHECK_IN", "RECOMMENDATION", "QUESTION", "EXPLORE_OFFER",
                  "DISPATCH"}


def _db():
    from supabase_store import get_client
    return get_client()


# ── closing the loop ──────────────────────────────────────────────────────────

def mark_engaged(user_id: str) -> bool:
    """She wrote. If that followed something we sent, record that it landed.

    Called on each user message. Costs one indexed read and, rarely, one write.
    """
    try:
        since = (datetime.now(timezone.utc)
                 - timedelta(hours=REPLY_WINDOW_HOURS)).isoformat()
        rows = (_db().table("proactive_events")
                .select("id,action,created_at")
                .eq("user_id", user_id)
                .is_("responded_at", "null")
                .not_.is_("delivered_at", "null")
                .gte("created_at", since)
                .order("created_at", desc=True).limit(1).execute()).data or []
        if not rows:
            return False

        from memory.proactive_log import record_outcome
        record_outcome(rows[0]["id"], "engaged")
        print(f"[Cadence] {user_id} replied to {rows[0]['action']}")
        return True
    except Exception as e:
        print(f"[Cadence] mark_engaged failed: {e}")
        return False


# ── how she has been responding ───────────────────────────────────────────────

def response_rate(user_id: str, days: int = 7) -> Dict:
    """Sent versus replied-to, and how long since she last answered anything."""
    out = {"sent": 0, "answered": 0, "rate": None, "days_since_reply": None}
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = (_db().table("proactive_events")
                .select("action,created_at,responded_at,delivered_at")
                .eq("user_id", user_id)
                .not_.is_("delivered_at", "null")
                .gte("created_at", since).execute()).data or []
    except Exception as e:
        print(f"[Cadence] response rate failed: {e}")
        return out

    rows = [r for r in rows if r.get("action") in CONVERSATIONAL]
    out["sent"] = len(rows)
    answered = [r for r in rows if r.get("responded_at")]
    out["answered"] = len(answered)
    if rows:
        out["rate"] = round(len(answered) / len(rows), 2)

    # Silence is measured from her last REPLY, not her last message — someone
    # who writes unprompted every day is engaged whatever the ratio says. That
    # is handled by mark_engaged stamping whatever preceded her message.
    # Writing unprompted counts. Silence is not-chatting AND not-responding;
    # either one alone means she is still there, and someone who writes every
    # day but ignores notifications was reading as fully disengaged.
    try:
        # messages is keyed by session, not by user — without this every
        # user inherited everyone else's activity, and two people six days
        # silent both looked like they had written today.
        sess = (_db().table("sessions").select("id")
                .eq("user_id", user_id)
                .gte("updated_at", since).execute()).data or []
        ids = [s["id"] for s in sess]
        own = []
        if ids:
            rows2 = (_db().table("messages")
                     .select("timestamp,session_id,role")
                     .in_("session_id", ids)
                     .eq("role", "user")
                     .gte("timestamp", since)
                     .order("timestamp", desc=True).limit(50).execute()).data or []
            own = [r for r in rows2 if r.get("timestamp")]
    except Exception as e:
        print(f"[Cadence] own-message read failed: {e}")
        own = []

    if own:
        try:
            latest_own = max(r["timestamp"] for r in own)
            dt = datetime.fromisoformat(str(latest_own).replace("Z", "+00:00"))
            d_own = (datetime.now(timezone.utc) - dt).days
            out["days_since_wrote"] = d_own
        except Exception:
            pass

    if answered:
        latest = max(r["responded_at"] for r in answered)
        try:
            dt = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
            out["days_since_reply"] = (datetime.now(timezone.utc) - dt).days
        except Exception:
            pass
    elif rows:
        out["days_since_reply"] = days      # sent things, heard nothing
    return out


def budget(user_id: str) -> int:
    """How many unprompted conversational messages today.

    Care sits outside this entirely.
    """
    rr = response_rate(user_id)

    # Nothing sent yet: a new user, or one we have been quiet with. Start at
    # base rather than assuming either engagement or its absence.
    if not rr["sent"]:
        return BASE_BUDGET

    # The more recent of the two. Not chatting AND not responding is silence;
    # doing either is not.
    since = min([d for d in (rr.get("days_since_reply"),
                             rr.get("days_since_wrote")) if d is not None]
                or [None]) if any(
        d is not None for d in (rr.get("days_since_reply"),
                                rr.get("days_since_wrote"))) else None
    if since is not None:
        if since >= 7:
            return 0        # and the caregiver view should be saying so
        if since >= 3:
            return 1        # a greeting, nothing else

    rate = rr["rate"] or 0
    if rate >= 0.6:
        return 6
    if rate >= 0.25:
        return BASE_BUDGET
    return 2


# ── what has already happened today ───────────────────────────────────────────

def todays_ledger(user_id: str) -> Dict:
    """What has been sent today, of what kind, and when the last one went."""
    out = {"count": 0, "kinds": [], "last_at": None, "minutes_since": None}
    try:
        from zoneinfo import ZoneInfo
        from memory.declared import get_declared
        tz = ZoneInfo(get_declared(user_id).place.timezone)
        start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        rows = (_db().table("proactive_events")
                .select("action,created_at,delivered_at")
                .eq("user_id", user_id)
                # Not filtered on delivered_at. A user with no push token —
                # Kamala — never had anything marked delivered, so her ledger
                # was permanently empty and she got MORE messages, not fewer.
                # A failure to deliver is not permission to send again.
                .neq("action", "SILENCE")
                .gte("created_at", start.astimezone(timezone.utc).isoformat())
                .order("created_at", desc=True).execute()).data or []
    except Exception as e:
        print(f"[Cadence] ledger failed: {e}")
        return out

    # Spacing counts EVERYTHING; the budget counts conversation. Two
    # different questions, and conflating them let a recommendation go
    # seventeen minutes after a boundary — the boundary was not in the ledger,
    # so there was nothing to space against. Her phone does not care which
    # kind a message was.
    # The budget counts what she actually RECEIVED; spacing counts what was
    # decided. Counting decisions for both meant a day where one message
    # arrived and fourteen failed read as nine of six spent, and every
    # remaining offer was refused for messages she never saw.
    conv = [r for r in rows
            if r.get("action") in CONVERSATIONAL and r.get("delivered_at")]
    out["count"] = len(conv)
    out["kinds"] = [r["action"] for r in conv]
    if rows:
        out["last_at"] = rows[0]["created_at"]
        try:
            dt = datetime.fromisoformat(str(rows[0]["created_at"]).replace("Z", "+00:00"))
            out["minutes_since"] = int(
                (datetime.now(timezone.utc) - dt).total_seconds() / 60)
        except Exception:
            pass
    return out


# ── the gate ──────────────────────────────────────────────────────────────────

def may_send(user_id: str, action: str) -> Dict:
    """Should this go out? Returns {"allow": bool, "reason": str}.

    Care and safety pass unconditionally. Everything else answers to the
    budget, the spacing, and the variety rule.
    """
    if action not in CONVERSATIONAL:
        return {"allow": True, "reason": "not_conversational"}

    led = todays_ledger(user_id)
    cap = budget(user_id)

    if cap == 0:
        return {"allow": False, "reason": "no_reply_for_a_week"}
    if led["count"] >= cap:
        return {"allow": False, "reason": f"budget_spent_{led['count']}_of_{cap}"}

    mins = led["minutes_since"]
    if mins is not None and mins < MIN_GAP_MINUTES:
        # A perishable thing is worth the interruption or it is worth nothing:
        # a match result tomorrow is not a match result.
        if action != "DISPATCH":
            return {"allow": False, "reason": f"only_{mins}m_since_last"}

    # One of each kind a day, apart from dispatches. Three offers is a shop; a
    # greeting, a piece of news and one offer is a conversation. This does more
    # for feeling talkative than the budget does.
    if action != "DISPATCH" and action in led["kinds"]:
        return {"allow": False, "reason": f"already_sent_{action}_today"}

    return {"allow": True, "reason": f"{led['count']}_of_{cap}_used"}

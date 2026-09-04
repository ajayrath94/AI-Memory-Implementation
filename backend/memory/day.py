"""
THE DAY — her schedule instantiated, and what has happened so far.

proactive_check ran fresh every fifteen minutes and knew nothing about the rest
of the day. Every slot was independent: the breakfast reminder did not know
whether she ate, the Metformin reminder at 15:45 did not know whether there was
lunch, and the walk nudge did not know it had rained at eight.

But a day is a chain. Thyronorm needs an empty stomach; Metformin needs food.
Rain at breakfast decides the evening walk, and saying so at breakfast is useful
where saying it at five is too late.

BOUNDARIES ARE WHAT MAKE IT CONVERSATION
The thing that was missing until now. Every earlier message stood alone — a
greeting, a reminder, an offer — each correct and none connected, so it read as
a system doing things at someone rather than someone talking to them.

A boundary message refers backwards and forwards in one breath:

    "Sair kaisi rahi? Aur aaj khane mein kya plan hai — koi suggestion chahiye?"

Which confirms the walk, opens dinner, and offers help without pushing. It
assumes shared context, and that is what conversation is.

It also settles where a recommendation belongs. An offer no longer has to find
a moment and interrupt one; the moment is built into the day, and she is asked
whether she wants it.

WHICH EVENTS MAKE A BOUNDARY
Meals and routines. Not medication — "dawai le li?" does not pair with "aur
aage kya plan hai", and dressing a tablet up as conversation is worse than
asking plainly.

WHAT THE STATUS MEANS
    pending    not due yet
    sent       we said something, no answer
    confirmed  she said she did it, or mentioned it in passing
    denied     she said she did not
    unknown    asked, no answer, and the day moved on

Unknown is carried, not chased. One question, and then it is dropped — an
elderly person asked twice about one meal is being supervised, not accompanied.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

# Kinds that are worth a conversation rather than an instruction.
CONVERSATIONAL_KINDS = ("meal", "routine")

# How long after an event before asking about it. At 17:31 it is checking; an
# hour later it is conversation.
LOOKBACK_MIN = 45

# And how close to the next one before it is worth raising.
LOOKAHEAD_MIN = 90


def _db():
    from supabase_store import get_client
    return get_client()


def _today(user_id: str):
    from zoneinfo import ZoneInfo
    from memory.declared import get_declared
    tz = ZoneInfo(get_declared(user_id).place.timezone)
    now = datetime.now(tz)
    return now, now.date().isoformat(), now.hour * 60 + now.minute


def _mins(hhmm) -> int:
    try:
        h, m = str(hhmm)[:5].split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return -1


# ── building the day ──────────────────────────────────────────────────────────

def rebuild(user_id: str) -> int:
    """Instantiate today from her schedule. Idempotent.

    Built each morning rather than continuously, so a caregiver's edit takes
    effect tomorrow rather than halfway through today — a schedule that moves
    under a day already in progress produces events that were never due.
    """
    _, date, _ = _today(user_id)
    db = _db()

    try:
        existing = (db.table("day_events").select("id")
                    .eq("user_id", user_id).eq("date", date)
                    .limit(1).execute()).data or []
        if existing:
            return 0
    except Exception as e:
        print(f"[Day] existing check failed: {e}")
        return 0

    try:
        items = (db.table("care_schedule").select("*")
                 .eq("user_id", user_id).eq("active", True).execute()).data or []
    except Exception as e:
        print(f"[Day] schedule read failed: {e}")
        return 0

    rows = []

    # Meals and routines live in her declared rhythm, not in care_schedule —
    # that table holds what a caregiver set up, which for her is two tablets.
    # Without these there are no boundaries at all, since medication is a
    # reminder rather than a conversation.
    try:
        from memory.declared import get_declared
        r = get_declared(user_id).rhythm
        for name, at in (r.meals or {}).items():
            if at:
                rows.append({"user_id": user_id, "date": date, "kind": "meal",
                             "label": name, "due_at": str(at)[:5],
                             "status": "pending", "schedule_id": None})
        for rt in (r.routines or []):
            if rt.get("at"):
                rows.append({"user_id": user_id, "date": date, "kind": "routine",
                             "label": rt.get("label") or "routine",
                             "due_at": str(rt["at"])[:5],
                             "status": "pending", "schedule_id": None})
    except Exception as e:
        print(f"[Day] rhythm read failed: {e}")

    for it in items:
        at = it.get("time_of_day") or it.get("time") or it.get("at")
        if not at:
            continue
        rows.append({
            "user_id": user_id, "date": date,
            "kind":    it.get("type") or "routine",
            "label":   it.get("label") or "",
            "due_at":  str(at)[:5],
            "status":  "pending",
            "schedule_id": it.get("id"),
        })

    # Her rhythm carries meals from two places and they disagree on casing —
    # "breakfast" and "Breakfast", the walk as both "Evening walk" and
    # "exercise". One event per time and kind, keeping the first, since a day
    # with two dinners produces two boundaries at the same hour.
    seen, unique = set(), []
    for r_ in rows:
        key = (r_["due_at"], r_["kind"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r_)
    rows = unique

    if not rows:
        return 0
    try:
        db.table("day_events").insert(rows).execute()
        print(f"[Day] {user_id}: {len(rows)} events for {date}")
        return len(rows)
    except Exception as e:
        print(f"[Day] insert failed: {e}")
        return 0


def events(user_id: str) -> List[Dict]:
    _, date, _ = _today(user_id)
    try:
        return (_db().table("day_events").select("*")
                .eq("user_id", user_id).eq("date", date)
                .order("due_at").execute()).data or []
    except Exception as e:
        print(f"[Day] read failed: {e}")
        return []


def set_status(event_id: str, status: str, note: str = "") -> bool:
    try:
        upd = {"status": status,
               "updated_at": datetime.now(timezone.utc).isoformat()}
        if status == "sent":
            upd["sent_at"] = upd["updated_at"]
        if note:
            upd["note"] = note[:200]
        _db().table("day_events").update(upd).eq("id", event_id).execute()
        return True
    except Exception as e:
        print(f"[Day] status write failed: {e}")
        return False


# ── boundaries ────────────────────────────────────────────────────────────────

def boundary(user_id: str, now_min: Optional[int] = None) -> Optional[Dict]:
    """Something has just finished and something is coming. Or None.

    None is the common answer, and it is the right one — a message with nothing
    behind it and nothing ahead is where this reads as artificial. If there is
    no boundary there is usually nothing to say, and silence is more natural
    than a manufactured opener.
    """
    if now_min is None:
        _, _, now_min = _today(user_id)

    evs = events(user_id)
    if not evs:
        return None

    conv = [e for e in evs if (e.get("kind") or "") in CONVERSATIONAL_KINDS]

    # What has just passed and was never spoken about.
    just_done = None
    for e in conv:
        due = _mins(e.get("due_at"))
        if due < 0:
            continue
        if due <= now_min <= due + LOOKBACK_MIN + 60 and e.get("status") in ("pending", "sent"):
            if now_min >= due + LOOKBACK_MIN:
                just_done = e

    # And what is coming, whatever kind — dinner is worth raising after a walk
    # even though the walk is the thing being asked about.
    coming = None
    for e in conv:
        due = _mins(e.get("due_at"))
        if due < 0:
            continue
        if now_min < due <= now_min + LOOKAHEAD_MIN:
            coming = e
            break

    if not (just_done or coming):
        return None
    return {"done": just_done, "next": coming}


def boundary_hint(user_id: str, b: Dict) -> str:
    """The line for the composer.

    Both halves in one message where there are two: looking back is what makes
    it a conversation continuing rather than a notification arriving, and
    looking forward is what gives it a reason to exist.
    """
    done = b.get("done")
    nxt  = b.get("next")

    parts = []
    if done:
        parts.append(
            f"Their {done['label'] or done['kind']} was at {done['due_at']} and "
            f"they have not mentioned it. Ask how it went — once, lightly, the "
            f"way you would ask a friend. Not whether they did it."
        )
    if nxt:
        line = (f"Next is {nxt['label'] or nxt['kind']} at {nxt['due_at']}. "
                f"Ask what they are planning.")
        if (nxt.get("kind") or "") == "meal":
            # Where an offer belongs: invited rather than interrupting.
            line += (" If they seem unsure, offer to suggest something — "
                     "\"koi suggestion chahiye\" — but do not suggest anything "
                     "unless they ask.")
        parts.append(line)

    if not parts:
        return ""

    if len(parts) > 1:
        tail = ("\nOne message, not two — but say BOTH halves. Looking back is "
                "what makes it a conversation continuing; looking forward is "
                "what gives it a reason to exist, and the forward half is the "
                "one that keeps getting dropped.")
    else:
        tail = ""
    return ("\n".join(parts) + tail +
            "\nThis may assume they know what you are talking about.")

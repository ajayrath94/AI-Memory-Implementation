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
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

# Kinds that are worth a conversation rather than an instruction.
CONVERSATIONAL_KINDS = ("meal", "routine")

# How long after an event before asking about it. At 17:31 it is checking; an
# hour later it is conversation.
# Half an hour after is checking; an hour is conversation. But 45 minutes
# either side left gaps where nothing fired at all — 24 minutes after her walk
# was too early to ask, and dinner 96 minutes off was too far to raise.
LOOKBACK_MIN = 25

# And how close to the next one before it is worth raising.
LOOKAHEAD_MIN = 150


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
    # Keep the most specific label. The rhythm calls the 17:30 routine
    # "exercise" and the caregiver called it "Evening walk", and keeping
    # whichever came first left the model unable to connect "sair achi rahi" to
    # it — so that event could never be confirmed at all.
    best = {}
    for r_ in rows:
        key = (r_["due_at"], r_["kind"])
        cur = best.get(key)
        if cur is None or len(r_.get("label") or "") > len(cur.get("label") or ""):
            best[key] = r_
    rows = list(best.values())

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

    # A tablet is not a conversation. "BP medicine" sits in her rhythm as a
    # routine, so it produced a boundary — "9 baje wala routine theek se ho
    # gaya na?" about a blood pressure tablet, half an hour after the dinner
    # boundary said almost the same thing. Medication is a reminder; that path
    # already handles it and names the drug.
    def _is_medicine(e):
        lab = (e.get("label") or "").lower()
        return any(w in lab for w in ("medicine", "tablet", "dawai", "dose",
                                      "thyronorm", "amlodipine", "goli"))

    conv = [e for e in evs
            if (e.get("kind") or "") in CONVERSATIONAL_KINDS
            and not _is_medicine(e)]

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

    # A boundary needs something BEHIND it. Forward-only fired at 11:15 and
    # again at 12:15 with the same "lunch is coming" and nothing to look back
    # on — which is a manufactured opener, the thing this design exists to
    # avoid. Twelve of fifteen waking hours qualified.
    if not just_done:
        return None

    # And once per event. Every pass saw the same window afresh, so the
    # fifteen-minute scheduler would have asked about her walk four times.
    if just_done.get("status") == "sent":
        return None
    # Marked by whoever DELIVERS it, not here. A dry run or a push that failed
    # would otherwise burn the boundary silently — you trigger something,
    # nothing arrives, and the retry does nothing because it is already spent.

    return {"done": just_done, "next": coming}




def _said_since(user_id: str, ev: Dict) -> str:
    """What she said about this event, in the hours before this boundary.

    Not message by message. A refusal, a plan and a report all read
    differently one line at a time and obviously in context — and the context
    is everything between one boundary and the next.
    """
    from datetime import timedelta
    try:
        from supabase_store import get_client
        db = get_client()
        since = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        sess = (db.table("sessions").select("id")
                .eq("user_id", user_id).gte("updated_at", since)
                .order("updated_at", desc=True).limit(3).execute()).data or []
        said = []
        for s in sess:
            for m in (db.table("messages").select("content,timestamp")
                      .eq("session_id", s["id"]).eq("role", "user")
                      .gte("timestamp", since)
                      .order("timestamp").execute()).data or []:
                said.append(str(m.get("content") or "")[:200])
    except Exception as e:
        print(f"[Day] window read failed: {e}")
        return ""

    if not said:
        return ""

    label = ev.get("label") or ev.get("kind") or ""
    prompt = f"""Someone said these things over the last few hours:

{chr(10).join('- ' + s for s in said[-12:])}

Did any of it say something about their {label}? If so, reply with that one
line, exactly as they wrote it. Otherwise reply NONE.

Anything counts — that they did it, that they did not, that they are not
going to, how it went, or that something got in the way.

One line, nothing else."""
    try:
        from llm import ask
        got = (ask(prompt, max_tokens=80) or "").strip().strip('"')
    except Exception as e:
        print(f"[Day] window read failed: {e}")
        return ""
    return "" if (not got or got.upper().startswith("NONE")) else got[:200]

def boundary_hint(user_id: str, b: Dict) -> str:
    """The line for the composer.

    Both halves in one message where there are two: looking back is what makes
    it a conversation continuing rather than a notification arriving, and
    looking forward is what gives it a reason to exist.
    """
    done = b.get("done")
    nxt  = b.get("next")

    # What was offered before this event, and whether she took it up. An offer
    # at 11:30 and a boundary at 13:30 are the same conversation an hour apart
    # — "khichdi kaisi bani?" is the companion having listened, where "khana
    # kaisa tha?" is the companion asking again.
    #
    # Only when she ACCEPTED. Raising something she declined, or ignored, is
    # worse than never having offered it.
    took_up = None
    if done:
        try:
            from supabase_store import get_client
            from datetime import timedelta
            since = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
            rows = (get_client().table("suggestions")
                    .select("label,reaction,intent")
                    .eq("user_id", user_id).eq("reaction", "accepted")
                    .neq("intent", "probe")
                    .gte("created_at", since)
                    .order("created_at", desc=True).limit(1).execute()).data or []
            if rows:
                took_up = rows[0].get("label")
        except Exception as e:
            print(f"[Day] offer lookup failed: {e}")

    # Read once. It was called twice — in the test and again in the branch —
    # which is two model calls for the same answer at every boundary.
    _window_said = _said_since(user_id, done) if done else ""

    parts = []
    if done:
        if took_up:
            parts.append(
                f"Earlier you suggested {took_up} and they said yes. Ask how "
                f"THAT went — by name, not in general. They told you an hour "
                f"ago; asking 'khana kaisa tha' as though you had forgotten is "
                f"worse than not asking."
            )
        elif _window_said:
            # She DID mention it, in the window before this boundary. Reading
            # message by message missed it: "aaj sair pe nahi jaungi" half an
            # hour after the walk was due was read as a plan rather than a
            # decision, nothing was recorded, and the evening message asked
            # how the walk had gone.
            #
            # The window is the honest unit. Whatever she said between the
            # last boundary and this one is what happened.
            parts.append(
                f"About their {done['label'] or done['kind']}, they already "
                f"said: \"{_window_said}\"\n"
                f"So do NOT ask how it went. Respond to what they actually "
                f"said — and do not go silent either, because saying nothing "
                f"after someone tells you something is its own answer."
            )
        elif _said_since(user_id, done):
            # She DID mention it, in the window before this boundary. Reading
            # message by message missed it: "aaj sair pe nahi jaungi" half an
            # hour after the walk was due was read as a plan rather than a
            # decision, nothing was recorded, and the evening message asked
            # how the walk had gone.
            #
            # The window is the honest unit. Whatever she said between the
            # last boundary and this one is what happened.
            parts.append(
                f"About their {done['label'] or done['kind']}, they already "
                f"said: \"{_window_said}\"\n"
                f"So do NOT ask how it went. Respond to what they actually "
                f"said — and do not go silent either, because saying nothing "
                f"after someone tells you something is its own answer."
            )
        elif _said_since(user_id, done):
            # She DID mention it, in the window before this boundary. Reading
            # message by message missed it: "aaj sair pe nahi jaungi" half an
            # hour after the walk was due was read as a plan rather than a
            # decision, nothing was recorded, and the evening message asked
            # how the walk had gone.
            #
            # The window is the honest unit. Whatever she said between the
            # last boundary and this one is what happened.
            parts.append(
                f"About their {done['label'] or done['kind']}, they already "
                f"said: \"{_window_said}\"\n"
                f"So do NOT ask how it went. Respond to what they actually "
                f"said — and do not go silent either, because saying nothing "
                f"after someone tells you something is its own answer."
            )
        else:
            parts.append(
                f"Their {done['label'] or done['kind']} was at {done['due_at']} "
                f"and they have not mentioned it. Ask how it went — once, "
                f"lightly, the way you would ask a friend. Not whether they "
                f"did it."
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


def _mins_now(user_id: str) -> int:
    _, _, now_min = _today(user_id)
    return now_min


def open_events(user_id: str) -> List[Dict]:
    """Past due and still unanswered. Usually empty, which is what makes the
    check cheap enough to run on every message."""
    now_min = _mins_now(user_id)
    return [e for e in events(user_id)
            if e.get("status") in ("pending", "sent")
            and 0 <= _mins(e.get("due_at")) <= now_min]


def _which(user_text: str, open_evs: List[Dict]) -> Optional[str]:
    """Which of today's things is this message about? Nothing else.

    Deliberately loose — it may say yes to a neighbour's walk or tomorrow's.
    Whether it counts is the next question, and asking both at once is what
    made the answers oscillate: four rewordings, each fixing some cases and
    breaking others.
    """
    listing = "\n".join(f"- {e['label'] or e['kind']}" for e in open_evs)
    prompt = f"""Someone wrote: "{user_text}"

These are things from their daily routine:
{listing}

Is the message about any of them — in any way at all, whoever did it and
whenever? Reply with ONLY the label, exactly as written above, or the single
word NONE.

They will not use these words. The labels were written in English by whoever
set up their schedule; they speak their own language. "Sair" is the Evening
walk, "nashta" is breakfast, "ਦਵਾਈ" is a medication. Match on what the thing
IS.

If several could equally fit, answer NONE.
One line, nothing else."""
    try:
        import anthropic
        client = __import__("llm").client()
        r = client.messages.create(model=__import__("llm").model("claude-haiku-4-5-20251001"),
                                   max_tokens=30,
                                   messages=[{"role": "user", "content": prompt}])
        got = (r.content[0].text or "").strip().strip('"').strip()
    except Exception as e:
        print(f"[Day] which-event read failed: {e}")
        return None
    if not got or got.upper() == "NONE":
        return None
    return got.split(" (a ")[0].strip()


def _happened(user_text: str, label: str) -> Optional[Dict]:
    """Did THIS person do it TODAY, and is it already done?

    One narrow question. All three conditions failed when they were conditions
    inside a larger prompt — the neighbour's walk, tomorrow's walk and
    yesterday's walk each got confirmed on different attempts.
    """
    prompt = f"""Someone wrote: "{user_text}"
This is about: {label}

Answer with ONE word.

done      — they themselves did it, today, and it is finished
not_done  — they themselves are not doing it today. Either the time passed
            and they did not, or they have said they are not going to.
other     — anything else

"other" covers more than it sounds. Someone else did it — "padosan sair karti
hai" is the neighbour. It was another day — "kal sair achi rahi thi". Or it is
still ahead of them — "shaam ko sair karne jaungi" is a plan, "soch rahi hoon
khichdi banaun" is a thought. None of those is a thing done.

But saying they are NOT doing it is not a plan, it is a decision, and it is
not_done. "Aaj sair pe nahi jaungi" said half an hour after the walk was due
came back as other, so nothing was recorded and the evening message asked how
the walk had gone.

One word, nothing else."""
    try:
        import anthropic
        client = __import__("llm").client()
        r = client.messages.create(model=__import__("llm").model("claude-haiku-4-5-20251001"),
                                   max_tokens=10,
                                   messages=[{"role": "user", "content": prompt}])
        a = (r.content[0].text or "").strip().lower().strip(".")
    except Exception as e:
        print(f"[Day] happened read failed: {e}")
        return None

    if a == "done":
        return {"label": label, "status": "confirmed", "detail": user_text[:120]}
    if a == "not_done":
        return {"label": label, "status": "denied", "detail": user_text[:120]}
    return None


def _read(user_text: str, open_evs: List[Dict]) -> Optional[Dict]:
    """Two narrow questions rather than one loaded with conditions.

    The second call only runs when the first found something, which is rare —
    so this is usually no more expensive than the single call it replaces.
    """
    label = _which(user_text, open_evs)
    if not label:
        return None
    return _happened(user_text, label)


def note_from_message(user_id: str, user_text: str) -> Optional[str]:
    """Called on every message she writes. Cheap when there is nothing open."""
    if not (user_text or "").strip():
        return None

    open_evs = open_events(user_id)
    if not open_evs:
        return None

    got = _read(user_text, open_evs)
    if not got:
        return None

    match = next((e for e in open_evs
                  if (e.get("label") or e.get("kind") or "").lower()
                  == got["label"].lower()), None)
    if not match:
        return None

    # A vague medication mention picks one anyway — "మాత్ర వేసుకున్నాను" with
    # three tablets open resolved to Thyronorm on no evidence, and the prompt
    # would not stop it. Recording the wrong tablet as taken is worse than
    # recording nothing, so it is refused here instead.
    if match.get("kind") == "medication":
        meds_open = [e for e in open_evs if e.get("kind") == "medication"]
        # What SHE said, not the model's summary of it — detail comes back
        # empty on a plain confirmation, so the guard was refusing "thyroid ki
        # goli le li" for naming nothing.
        said = f"{user_text} {got.get('detail') or ''}".lower()
        named = any(w for w in (match.get("label") or "").lower()
                    .replace("(", " ").replace(")", " ").split()
                    if len(w) > 3 and w in said)
        if len(meds_open) > 1 and not named:
            # She said "le li" with two tablets open and named neither. The
            # old answer was to record nothing, on the reasoning that the
            # wrong tablet is worse than none — and she confirmed twice in a
            # morning and both stayed pending all day, which a caregiver
            # would read as two missed doses.
            #
            # Nobody takes one tablet of two and says "le li". If every open
            # one is already overdue, she means all of them.
            # open_events already returns only what is past due, so every
            # tablet here is one she should have taken by now.
            if got["status"] == "confirmed":
                for e in meds_open:
                    set_status(e["id"], "confirmed", got.get("detail", ""))
                print(f"[Day] {user_id}: {len(meds_open)} overdue tablets "
                      f"confirmed together")
                return None
            print(f"[Day] {user_id}: a tablet was mentioned but not which one")
            return None

    set_status(match["id"], got["status"], got.get("detail", ""))
    print(f"[Day] {user_id}: {match['label'] or match['kind']} "
          f"{got['status']}" + (f" — {got['detail']}" if got["detail"] else ""))

    # A meal that named a dish is an EVENT, not a preference.
    #
    # This called record_declared_interest — the path for things she types
    # into the setup form — so "aaj lemon rice khaya" arrived as a favourite
    # with strength 1.33 and salience 0.8, the same weight as a dish she had
    # chosen from a list.
    #
    # The old comment argued that someone who cooked khichdi on Tuesday
    # demonstrated a preference where someone naming it on a form only stated
    # one. That is true and it is not a licence to promote the first
    # demonstration: one meal is Tuesday, and three across a fortnight is a
    # habit worth offering back to her.
    #
    # So it is recorded with its date, the dish lands in the day's untagged
    # subjects through the usual path, and repetition is what makes it a
    # cluster.
    if (match.get("kind") == "meal" and got["status"] == "confirmed"
            and got.get("detail")):
        try:
            from memory.events import record_event
            record_event(user_id, f"ate {got['detail']}",
                         kind="meal", feeling="")
        except Exception as e:
            print(f"[Day] meal event failed: {e}")

    return got["status"]

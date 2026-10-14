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

# How many of their day's moments get asked about, and how far apart.
#
# Every meal and routine was a boundary, so a day with five prayers, three
# meals and a walk produced seven messages, and the evening ones arrived an
# hour apart: the walk at 19:00, Maghrib at 20:00, dinner at 21:00, with the
# dinner question asked twice. Asking how each prayer went is supervision.
#
# The day is known each morning, so which moments to ask about is chosen
# once, from the whole day, rather than discovered tick by tick. Meals
# first, since they are what a boundary is best at; then routines, in order,
# while they fit the spacing and the cap.
MAX_BOUNDARIES_PER_DAY = 4
MIN_BOUNDARY_APART = 120


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

def _worth_asking(conv: List[Dict]) -> List[Dict]:
    """The moments in their day a boundary may be about. Deterministic: the
    same day gives the same answer at every tick, so nothing depends on the
    order the ticks happen to run in."""
    timed = [(e, _mins(e.get("due_at"))) for e in conv]
    timed = [(e, t) for e, t in timed if t >= 0]

    chosen: List[tuple] = []
    for want in ("meal", "routine"):
        for e, t in sorted(timed, key=lambda x: x[1]):
            if (e.get("kind") or "") != want:
                continue
            if len(chosen) >= MAX_BOUNDARIES_PER_DAY:
                break
            if all(abs(t - ct) >= MIN_BOUNDARY_APART for _, ct in chosen):
                chosen.append((e, t))
    return [e for e, _ in sorted(chosen, key=lambda x: x[1])]


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
    #
    # Whether an entry is a medicine is asked, not matched: "Pastilla de la
    # tensión" and "BP ki goli" are both tablets, and a word list knows only
    # the languages someone wrote it in. Asked once per label and remembered.
    # If the model cannot say, it is treated as a medicine — a tablet that
    # gets no check-in loses nothing; one that gets "how did it go?" is the
    # mistake this exists to stop.
    def _is_medicine(e):
        lab = (e.get("label") or "").strip()
        if not lab:
            return False
        try:
            from memory.judge import yes_no
            return yes_no(f'A daily schedule entry reads: "{lab}". Is it '
                          f'about taking a medicine, tablet, injection or '
                          f'other dose?', key="med:" + lab.lower())
        except Exception as ex:
            print(f"[Day] medicine check failed for {lab!r}: {ex}")
            return True

    conv = [e for e in evs
            if (e.get("kind") or "") in CONVERSATIONAL_KINDS
            and not _is_medicine(e)]

    # Only the moments chosen for today, for both halves: "how was Zuhr" and
    # "what are you planning for Asr" are the same over-asking.
    conv = _worth_asking(conv)

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

    # Already asked in the chat. The chat asked "nashta ho gaya?" at 09:03
    # and this asked "nashta kaisa raha?" at 09:08; "lunch ka time ho gaya
    # kya?" at 13:05 and "lunch kaisa gaya?" at 14:08. The chat and the
    # boundary did not know about each other. Whatever Nancy has already
    # said about this part of the day, in any message, counts as asked —
    # answered or not. One question per meal.
    asked = _already_raised(user_id, just_done, coming)
    if just_done.get("id") in asked:
        print(f"[Day] {user_id}: {just_done.get('label')!r} already raised "
              f"in chat, no boundary")
        return None
    if coming and coming.get("id") in asked:
        coming = None

    return {"done": just_done, "next": coming, "now_min": now_min}


# ── what has already been said today ─────────────────────────────────────────

# Event ids found already raised. Only positives are kept: a "not yet" can
# change by the next tick, an "already asked" cannot.
_RAISED: set = set()


def _at_iso(user_id: str, mins: int) -> str:
    """A minute of their local day as a UTC timestamp, for querying."""
    now, _, _ = _today(user_id)
    t = now.replace(hour=0, minute=0, second=0, microsecond=0) \
        + timedelta(minutes=max(0, mins))
    return t.astimezone(timezone.utc).isoformat()


def _conversation(user_id: str, since_iso: str) -> List[Dict]:
    """Both sides since a moment, in order: [{"who", "text", "at"}].

    who is "nancy" for anything Nancy sent (chat replies and proactive
    messages alike) and "them" for the person.
    """
    out: List[Dict] = []
    try:
        db = _db()
        sess = (db.table("sessions").select("id")
                .eq("user_id", user_id).gte("updated_at", since_iso)
                .order("updated_at", desc=True).limit(5).execute()).data or []
        for s in sess:
            for m in (db.table("messages").select("content,timestamp,role")
                      .eq("session_id", s["id"]).gte("timestamp", since_iso)
                      .order("timestamp").execute()).data or []:
                text = str(m.get("content") or "").strip()
                if text:
                    out.append({"who": "nancy" if m.get("role") == "assistant"
                                else "them",
                                "text": text, "at": m.get("timestamp") or ""})
    except Exception as e:
        print(f"[Day] conversation read failed: {e}")
    out.sort(key=lambda m: m["at"])
    _tag_reminders(user_id, since_iso, out)
    return out


def _ts(s) -> Optional[datetime]:
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _tag_reminders(user_id: str, since_iso: str, convo: List[Dict]) -> None:
    """Mark Nancy's medication reminders as such, from the decision log.

    "Nashte ke baad goli le lijiye" names breakfast, and the model counted
    it as having asked about breakfast, which would have cancelled the
    breakfast check-in on every day with a morning tablet. Which message
    was a reminder is a fact on record, so it is looked up, not judged.
    """
    try:
        rows = (_db().table("proactive_events").select("created_at,delivered_at")
                .eq("user_id", user_id).eq("action", "MEDICATION_REMINDER")
                .gte("created_at", since_iso).execute()).data or []
    except Exception as e:
        print(f"[Day] reminder read failed: {e}")
        return
    sent = [t for r in rows for t in (_ts(r.get("created_at")), _ts(r.get("delivered_at"))) if t]
    if not sent:
        return
    for m in convo:
        if m["who"] != "nancy":
            continue
        at = _ts(m.get("at"))
        if at and any(timedelta(minutes=-1) <= at - t <= timedelta(minutes=10)
                      for t in sent):
            m["kind"] = "medication"


def _transcript(convo: List[Dict], limit: int = 16) -> str:
    return "\n".join(f"{'COMPANION' if m['who'] == 'nancy' else 'THEM'}: "
                     f"{m['text'][:300]}" for m in convo[-limit:])


def _raised(convo: List[Dict], labels: List[str]) -> set:
    """Which of these parts of their day the companion has already asked
    about or brought up in this stretch of conversation. Indices into labels.

    No database: the harness calls this directly with real transcripts.
    """
    labels = [l for l in labels if l]
    # A medication reminder is not a question about the meal it is timed to.
    convo = [m for m in convo if m.get("kind") != "medication"]
    if not labels or not any(m["who"] == "nancy" for m in convo):
        return set()
    listed = "\n".join(f"{i + 1}. {l}" for i, l in enumerate(labels))
    prompt = f"""A companion has been talking with someone today. In order:

{_transcript(convo)}

For each of these parts of their day, has the COMPANION already asked about
it or brought it up: how it went, whether it happened yet, or what they plan
for it?

{listed}

It counts whether or not they answered. It counts in their own words: nashta
is breakfast, sair is the walk.

It does not count when the thing is only a time reference inside a message
about something else: "take your tablet after breakfast" has not asked about
breakfast.

Reply with the numbers that were asked about or brought up, separated by
commas, or NONE."""
    try:
        from llm import ask
        got = (ask(prompt, max_tokens=20) or "").strip()
    except Exception as e:
        print(f"[Day] raised check failed: {e}")
        return set()
    if not got or got.upper().startswith("NONE"):
        return set()
    import re
    return {int(n) - 1 for n in re.findall(r"\d+", got)
            if 0 < int(n) <= len(labels)}


def _already_raised(user_id: str, done: Dict, nxt: Optional[Dict]) -> set:
    """Event ids among done/nxt that Nancy already asked about in chat, from
    an hour before the earlier one was due."""
    evs = [e for e in (done, nxt) if e]
    out = {e.get("id") for e in evs if e.get("id") in _RAISED}
    todo = [e for e in evs if e.get("id") not in out]
    if not todo:
        return out
    due = _mins(done.get("due_at"))
    convo = _conversation(user_id, _at_iso(user_id, (due if due >= 0 else 0) - 60))
    hit = _raised(convo, [str(e.get("label") or e.get("kind") or "") for e in todo])
    for i in hit:
        _RAISED.add(todo[i].get("id"))
        out.add(todo[i].get("id"))
    return out




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
        # Since the LAST boundary, not the last five hours.
        #
        # She was asked at 09:03 how breakfast had gone and answered at
        # 11:30, "aloo ke parathe khaye". The lunch boundary at 13:33 read a
        # five-hour window, swept that up as its own, decided lunch was
        # already answered and did not ask — and she said "aj lunch k liye
        # toh pucha nai tumne" twice.
        #
        # A message belongs to the boundary it came after. That is a
        # timestamp, not a judgement, and proactive_events has every one.
        since = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        try:
            prev = (db.table("proactive_events")
                    .select("created_at")
                    .eq("user_id", user_id).eq("action", "BOUNDARY")
                    .not_.is_("delivered_at", "null")
                    .gte("created_at", since)
                    .order("created_at", desc=True)
                    .limit(1).execute()).data or []
            if prev:
                since = prev[0]["created_at"]
        except Exception as _pe:
            print(f"[Day] previous boundary read failed: {_pe}")
        convo = _conversation(user_id, since)
    except Exception as e:
        print(f"[Day] window read failed: {e}")
        return ""

    # Not what was already the answer about something else. "Saaptachu" at
    # 08:20 confirmed breakfast, and at the lunch boundary it was read again
    # as being about lunch: "saaptachu nalla irukku" to someone who had
    # not been asked about lunch at all. A line that settled one event is
    # spent; this is a fact on the record, not a judgement about times.
    try:
        spent = [str(e.get("note") or "").strip().lower()
                 for e in (events(user_id) or [])
                 if e.get("id") != ev.get("id")
                 and e.get("status") in ("confirmed", "denied")
                 and (e.get("note") or "").strip()]
    except Exception as e:
        print(f"[Day] spent-line filter failed: {e}")
        spent = []

    return _their_line(convo, ev.get("label") or ev.get("kind") or "", spent)


def _their_line(convo: List[Dict], label: str, spent: Optional[List[str]] = None) -> str:
    """The line of theirs about this event today, exactly as written, or "".

    Read WITH what the companion said before each line. "Mila hai" on its
    own was taken as news about lunch, and the lunch boundary asked her
    "yeh kya naya mila hai aapko?". It was the answer to "did you get some
    rest after the puja?", which only the question shows.

    No database: the harness calls this directly with real transcripts.
    """
    spent = spent or []

    def _is_spent(x: str) -> bool:
        x = x.lower().strip()
        return any(n in x or x in n for n in spent)

    convo = [m for m in convo if m["who"] == "nancy" or not _is_spent(m["text"])]
    theirs = [m["text"] for m in convo if m["who"] == "them"]
    if not theirs or not label:
        return ""

    prompt = f"""A companion and someone have been talking. In order:

{_transcript(convo)}

Did THEY (not the companion) say anything about their {label} TODAY:
something they did, skipped, or decided about it?

Read each of their lines as the reply to what the companion said just
before it. A short reply means whatever it answers: "mila hai" after
"did you get some rest?" is about rest, not about the {label}, and "haan"
after a question about the walk is about the walk.

It must be the {label} itself, not anything else that happened near it.

Yes:
  "aaj lunch mein khichdi banaungi"     they decided this lunch
  "shaam ko sair nahi jaungi"           they decided the walk
  "mandir ho aayi"                      they did the puja

No:
  "aloo ke parathe khaye"               a different meal, not this one
  "aj lunch k liye toh pucha nai"       asking to be asked
  "thak gayi hoon"                      about how they feel
  "thodi neend aa rahi hai"             about resting, not about this

Their own words count: sair is the walk, vrat is the fast. But any food is
not this meal, and a nap in the afternoon says nothing about dinner.

Reply with their line exactly as written, or NONE. One line, nothing else."""
    try:
        from llm import ask
        got = (ask(prompt, max_tokens=80) or "").strip().strip('"')
    except Exception as e:
        print(f"[Day] window read failed: {e}")
        return ""
    if not got or got.upper().startswith("NONE"):
        return ""
    # It must be one of THEIR lines. A line of the companion's coming back
    # here is answered as if they had said it.
    g = got.lower().strip()
    if not any(g in t.lower() or t.lower().strip() in g for t in theirs):
        print(f"[Day] window line not theirs, ignored: {got[:60]!r}")
        return ""
    return got[:200]

def _ago(mins: int) -> str:
    """How long ago, in words. A clock time in the hint becomes a clock time
    in the message, and nobody asks how your lunch at 13:30 was."""
    if mins < 75:
        return "a little while ago"
    if mins < 150:
        return "an hour or two ago"
    return "earlier today"


def _soon(mins: int) -> str:
    """How far ahead, in words. Same reason as _ago()."""
    if mins < 45:
        return "very soon"
    if mins < 90:
        return "in a little while"
    return "later on"


_SPOKEN: Dict[str, str] = {}


def _speakable(label: str) -> str:
    """How a person would refer to this part of someone's day.

    Asked once per label and remembered. A label that already names a thing
    (a meal, a prayer, a walk) comes back unchanged.
    """
    if not label:
        return label
    if label in _SPOKEN:
        return _SPOKEN[label]
    out = label
    try:
        from llm import ask
        got = (ask(f"""A schedule entry reads: "{label}"

How would a friend refer to that part of someone's day in conversation, as a
short noun phrase, in the same language as the entry? If the entry is already
the name of a thing (a meal, a prayer, a walk, a rest), return it unchanged.

Only the phrase, nothing else.""", max_tokens=20) or "").strip().strip('"').strip(".")
        if got and len(got) <= 60 and "\n" not in got:
            out = got
    except Exception as e:
        print(f"[Day] speakable failed for {label!r}: {e}")
    _SPOKEN[label] = out
    if out != label:
        print(f"[Day] {label!r} -> {out!r}")
    return out


def boundary_hint(user_id: str, b: Dict) -> str:
    """The line for the composer.

    Both halves in one message where there are two: looking back is what makes
    it a conversation continuing rather than a notification arriving, and
    looking forward is what gives it a reason to exist.

    Nothing in here is a phrase to copy. Every line is an instruction in
    English about what to say, because the composer writes in the person's
    language and any quoted example overrides that: "koi suggestion chahiye"
    was quoted here and came back inside a Tamil message and a Bengali one.
    """
    done = b.get("done")
    nxt  = b.get("next")
    if not (done or nxt):
        return ""

    # The clock boundary() decided on, so the hint and the decision agree.
    now_min = b.get("now_min")
    if now_min is None:
        try:
            now_min = _mins_now(user_id)
        except Exception:
            now_min = None

    def _label(ev: Dict) -> str:
        raw = str(ev.get("label") or ev.get("kind") or "").strip()
        # A routine's label is a schedule note, and a note in a sentence
        # reads as one: "How was home from office?" twice, after the hint
        # was told not to do it. So the composer is given the spoken form.
        return _speakable(raw) if (ev.get("kind") or "") == "routine" else raw

    # What was offered before this event, and whether they took it up. An
    # offer at 11:30 and a boundary at 13:30 are the same conversation an
    # hour apart: asking about the thing they chose is the companion having
    # listened, asking about the meal in general is the companion asking again.
    #
    # Only when they ACCEPTED. Raising something declined or ignored is worse
    # than never having offered it.
    took_up = None
    if done:
        try:
            since = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
            rows = (_db().table("suggestions")
                    .select("label,reaction,intent")
                    .eq("user_id", user_id).eq("reaction", "accepted")
                    .neq("intent", "probe")
                    .gte("created_at", since)
                    .order("created_at", desc=True).limit(1).execute()).data or []
            if rows:
                took_up = rows[0].get("label")
        except Exception as e:
            print(f"[Day] offer lookup failed: {e}")

    # Read once: it is a model call. The old version called it again in two
    # duplicated elif branches, which cost two more calls at every boundary
    # where they had said nothing.
    window_said = _said_since(user_id, done) if (done and not took_up) else ""

    parts = []

    if done:
        label = _label(done)
        if took_up:
            parts.append(
                f"Earlier you suggested {took_up} and they said yes. Ask how "
                f"that went, naming it. Asking about their {label} in general, "
                f"as though you had forgotten, is worse than not asking."
            )
        elif window_said:
            # They DID mention it, in the window before this boundary. The
            # window is the honest unit: whatever they said between the last
            # boundary and this one is what happened.
            parts.append(
                f"About their {label}, they already said: \"{window_said}\"\n"
                f"So do NOT ask how it went. Respond to what they said, in "
                f"your own words, and do not repeat their words back to them: "
                f"quoting someone hours later reads as a machine, not a "
                f"friend. Do not go silent either; saying nothing after "
                f"someone tells you something is its own answer."
            )
        else:
            due = _mins(done.get("due_at"))
            when = (_ago(max(0, now_min - due))
                    if (now_min is not None and due >= 0) else "a little while ago")
            parts.append(
                f"They had their {label} {when} and have not mentioned it. Ask "
                f"how it went, once and lightly, the way you would ask a "
                f"friend. Not whether they did it."
            )

    if nxt:
        label = _label(nxt)
        due = _mins(nxt.get("due_at"))
        when = (_soon(max(0, due - now_min))
                if (now_min is not None and due >= 0) else "soon")
        line = f"Their {label} is {when}. Ask what they are planning for it."
        if (nxt.get("kind") or "") == "meal":
            # Where an offer belongs: invited rather than interrupting.
            line += (" If they sound unsure about it, you may offer, in their "
                     "own language and your own words, to suggest something, "
                     "and then stop. Do not actually suggest anything unless "
                     "they ask.")
        parts.append(line)

    # The part of the day, said plainly. At 13:00 the composer wished
    # Kamala "the rest of the Sunday evening".
    part = ""
    if now_min is not None:
        h = now_min // 60
        part = ("morning" if h < 12 else "afternoon" if h < 17
                else "evening" if h < 21 else "night")

    rules = [
        *( [f"It is {part} now. If you mention the time of day at all, it "
            f"is {part}."] if part else [] ),
        "One message, not two. This is a conversation continuing, so it may "
        "assume they know what you are talking about.",
        "Never state a clock time. You know when these things happen; they "
        "live it. Say 'this morning', 'tonight', or nothing at all.",
        "The names above are entries from their schedule. Where one is the "
        "name of a thing (a meal, a prayer, a walk), use their word for it. "
        "Where it is a note of something they do, say what it means in your "
        "own words; never put the note into a sentence as if it were a noun.",
        "Name nothing they like" + (f", apart from {took_up} above" if took_up else "")
        + ". No song, singer, film, dish, team or hobby, not even one they "
        "mentioned today, and not as a pleasant aside. A boundary asks about "
        "their day and carries nothing else; anything new has its own "
        "message later.",
        "Mention only what is above. You can see their whole day elsewhere in "
        "this prompt; that is context for understanding them, not a list of "
        "things to raise. Raising something still hours away makes the next "
        "message repeat itself.",
    ]
    if done and nxt:
        rules.insert(1, "Say BOTH halves. The forward half is the one that "
                        "keeps getting dropped.")

    return "\n".join(parts) + "\n\nHOW TO WRITE IT:\n" + "\n".join(
        f"- {r}" for r in rules)


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


def _which(user_text: str, open_evs: List[Dict], replying_to: str = "") -> Optional[str]:
    """Which of today's things is this message about? Nothing else.

    Deliberately loose — it may say yes to a neighbour's walk or tomorrow's.
    Whether it counts is the next question, and asking both at once is what
    made the answers oscillate: four rewordings, each fixing some cases and
    breaking others.
    """
    listing = "\n".join(f"- {e['label'] or e['kind']}" for e in open_evs)
    before = (f'\nThey were replying to this, from their companion: "{replying_to[:300]}"\n'
              f'Read the message as that reply. A short answer is about whatever it '
              f'answers.\n') if replying_to else ""
    prompt = f"""Someone wrote: "{user_text}"
{before}
These are things from their daily routine:
{listing}

Is the message about any of them — in any way at all, whoever did it and
whenever? Reply with ONLY the label, exactly as written above, or the single
word NONE.

They will not use these words. The labels were written in English by whoever
set up their schedule; they speak their own language. "Sair" is the Evening
walk, "nashta" is breakfast, "ਦਵਾਈ" is a medication. Match on what the thing
IS.

If several could equally fit, answer NONE. If it is about something that is
not on this list, answer NONE: a remark about a film is not about breakfast.
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


def _happened(user_text: str, label: str, replying_to: str = "") -> Optional[Dict]:
    """Did THIS person do it TODAY, and is it already done?

    One narrow question. All three conditions failed when they were conditions
    inside a larger prompt — the neighbour's walk, tomorrow's walk and
    yesterday's walk each got confirmed on different attempts.
    """
    before = (f'They were replying to: "{replying_to[:300]}"\n') if replying_to else ""
    prompt = f"""Someone wrote: "{user_text}"
{before}This is about: {label}

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

not_done needs them to SAY so about this thing. "Subh subh kaun movie
dekhega" said about a film is not a skipped breakfast; nothing said about
it at all is "other", never not_done.

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


def _read(user_text: str, open_evs: List[Dict], replying_to: str = "") -> Optional[Dict]:
    """Two narrow questions rather than one loaded with conditions.

    The second call only runs when the first found something, which is rare —
    so this is usually no more expensive than the single call it replaces.
    """
    label = _which(user_text, open_evs, replying_to)
    if not label:
        return None
    return _happened(user_text, label, replying_to)


def _last_said_to_her(user_id: str) -> str:
    """What Nancy said last, within the last three hours, before this message.

    Her lines answer questions. "Sab acha raha, subh subh kaun movie dekhega"
    was a reply to "kaise raha aapka puja?" and to a film suggested at six in
    the morning; read alone it was taken as a skipped breakfast, breakfast was
    marked denied, and nobody asked her about it.
    """
    try:
        now = datetime.now(timezone.utc)
        convo = _conversation(user_id, (now - timedelta(hours=3)).isoformat())
        # The last message is usually hers (just saved); the line before it
        # from Nancy is what she is answering.
        for m in reversed(convo):
            if m["who"] == "nancy":
                return m["text"]
    except Exception as e:
        print(f"[Day] last-said read failed: {e}")
    return ""


def note_from_message(user_id: str, user_text: str) -> Optional[str]:
    """Called on every message she writes. Cheap when there is nothing open."""
    if not (user_text or "").strip():
        return None

    open_evs = open_events(user_id)
    if not open_evs:
        return None

    got = _read(user_text, open_evs, _last_said_to_her(user_id))
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

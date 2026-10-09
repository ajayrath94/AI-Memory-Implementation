"""
ONE DECISION — made once, carried to whoever writes the message.

Six bugs in a single day, all the same shape: something was decided, then
derived again somewhere else, and the two answers differed.

    the dose      proactive_check chose ONE tablet, deliberately sorted, so
                  that two an hour apart are two reminders an hour apart.
                  The composer looked them up again with a 45-minute window,
                  found both, and told her to take her BP tablet at seven
                  when it is due at eight.

    the boundary  the decision found the lunch boundary and marked it spent.
                  The composer asked for it again, got None, and wrote about
                  Kishore Kumar. She said "aj lunch k liye toh pucha nai
                  tumne" twice.

    the offer     proactive_check picked Kishore Kumar and passed it along.
                  The composer ran pick_suggestion again, got None at that
                  moment, and every block guarded by `if picked:` was
                  skipped — the expansion, the artefact, the days-since. The
                  prompt reached the model containing the weather and
                  nothing else.

They differ because the world moves between the two calls. A boundary marks
itself spent. A clock ticks. A picker's cooldown changes. So the second
answer is not merely redundant — it is reliably different in exactly the
cases that matter.

THE RULE
Whoever decides something passes it on. Nobody looks it up twice.

WHAT THIS IS
A Decision carries everything the message will need. The builder runs the
lookups once, in one place, in a known order, where `picked` stays in scope.
The composer reads the object.

NOT A QUEUE
A Decision is for the pass that made it. Held means discarded — an
hour-old artefact and a day that has moved on would reintroduce the same
class of bug by a slower route.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Decision:
    user_id: str
    action: str = "SILENCE"
    reason: str = ""
    detail: str = ""
    priority: str = "medium"

    # where she is, as the decision saw it
    slot: str = ""
    hour: Optional[int] = None
    away_from_home: bool = False

    # a medication reminder: the one dose that was chosen
    dose: Optional[Dict] = None

    # a boundary: {done, next}, found once
    boundary: Optional[Dict] = None

    # an offer: the whole chain, resolved together
    subject: str = ""            # the cluster that was drawn
    cluster_id: Optional[str] = None
    category: str = ""
    offering: str = ""           # what it expands to, or the subject itself
    because: str = ""            # what it expands FROM, when paired
    artefact: Optional[Dict] = None
    days_ago: Optional[int] = None

    # anything a caller wants to attach without changing this file
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict:
        """The shape the scheduler and the log already expect."""
        return {
            "user_id": self.user_id, "action": self.action,
            "reason": self.reason, "detail": self.detail,
            "priority": self.priority, "slot": self.slot,
            "away_from_home": self.away_from_home,
        }

    def summary(self) -> str:
        """One line, for a log or a stored row — so "why did she get this"
        is answerable a week later, which it is not today."""
        bits = [self.action]
        if self.detail:
            bits.append(repr(self.detail))
        if self.offering and self.offering != self.subject:
            bits.append(f"-> {self.offering}"
                        + (f" (because of {self.because})" if self.because else ""))
        if self.artefact:
            bits.append(f"+{self.artefact.get('kind', 'artefact')}")
        if self.dose:
            bits.append(f"dose={self.dose.get('label')}")
        if self.boundary:
            d = (self.boundary.get("done") or {})
            bits.append(f"after={d.get('label') or d.get('kind')}")
        return " ".join(str(b) for b in bits)


def with_offer(d: Decision) -> Decision:
    """Resolve the whole offer chain, here, once.

    pick -> expand -> fetch the artefact for what is being OFFERED -> how
    long since she last had it.

    This ran inside the composer, where pick_suggestion was called a second
    time and returned None — a different moment, a cooldown that had moved —
    so every block hanging off it was skipped and the message was written
    with no idea what it was for.
    """
    try:
        from memory.suggestions import pick_suggestion
        picked = pick_suggestion(d.user_id)
    except Exception as e:
        print(f"[Decision] pick failed: {e}")
        return d

    if not picked:
        # Nothing she has shown she likes, or everything is on cooldown.
        # Say nothing rather than invent something.
        return d

    d.subject = picked.get("label") or ""
    d.cluster_id = picked.get("cluster_id")
    d.days_ago = picked.get("days_ago")
    attrs = picked.get("attributes")
    d.category = (attrs or {}).get("category", "") if isinstance(attrs, dict) else ""

    # One step out. Kishore Kumar becomes a song by Lata or Rafi — the
    # adjacency list was being generated and thrown away.
    try:
        from memory.artefacts import what_to_offer
        o = what_to_offer(d.user_id, picked)
        d.offering = o.get("subject") or d.subject
        d.because = o.get("with_") or ""
    except Exception as e:
        print(f"[Decision] expand failed: {e}")
        d.offering = d.subject

    # And something she can act on, fetched for what is being offered rather
    # than for what was drawn — the hint said "offer R.D. Burman" and a
    # Kishore jukebox was attached, so the composer took the link.
    try:
        from memory.artefacts import fetch_artefact, fetch_along_axis
        art = fetch_artefact(d.user_id, d.category, d.offering)
        if not art:
            art = fetch_along_axis(d.user_id, picked)
            if art:
                # fell back to a variation on the original, so say so
                d.offering = d.subject
                d.because = ""
        d.artefact = art
    except Exception as e:
        print(f"[Decision] artefact failed: {e}")

    d.detail = d.subject
    return d


def hints_for(d: Decision) -> str:
    """What the composer needs to know, from the object alone.

    Everything here was previously assembled inside the composer by calling
    the same functions a second time.
    """
    if d.action != "RECOMMENDATION" or not d.subject:
        return ""

    out = []

    # How long since she last had it. The same subject is three different
    # offers depending on when, and the picker was handing over a label with
    # no date — so chole she ate two days ago arrived as a fresh idea.
    if d.days_ago is not None:
        if d.days_ago <= 3:
            when = "today" if d.days_ago == 0 else f"{d.days_ago} day(s) ago"
            out.append(f"They had {d.subject} {when}. So this is picking "
                       f"something up, not introducing it — 'phir se' rather "
                       f"than 'try kijiye'.")
        elif d.days_ago >= 14:
            out.append(f"It has been {d.days_ago} days since {d.subject} came "
                       f"up. That gap is itself the reason to mention it — "
                       f"'bahut din se' — and it should not sound like the "
                       f"first time.")

    # What to offer, and nothing else. Naming the familiar one is how every
    # message ended up being about the same singer.
    thing = d.offering or d.subject
    out.append(f"Offer {thing}. That one, and nothing else — do not name any "
               f"other artist, film or dish, whatever else you know she "
               f"likes. And do not credit it to anyone else: 'Kishore Kumar "
               f"ka Chaudhvin Ka Chand' is Rafi's song with the wrong "
               f"singer's name on it.")

    if d.artefact:
        title = str(d.artefact.get("title") or "")[:120]
        url = d.artefact.get("url") or ""
        if title:
            out.append(f"There is something she can tap: \"{title}\""
                       + (f" — {url}" if url else "")
                       + ". Offer that, in one line, as a thing to listen to "
                         "or watch now. Not a description of it.")

    return "\n\n" + "\n".join(out)


def build(user_id: str, hour: int = None) -> Decision:
    """What, if anything, to say — resolved completely.

    Wraps proactive_check's precedence and then finishes the job: an offer
    arrives with its expansion and its artefact already found, rather than
    as a label the composer has to look up again.
    """
    from memory.proactive_engine import proactive_check

    raw = proactive_check(user_id, override_hour=hour) or {}
    d = Decision(
        user_id=user_id,
        action=raw.get("action") or "SILENCE",
        reason=raw.get("reason") or "",
        detail=str(raw.get("detail") or ""),
        priority=raw.get("priority") or "medium",
        slot=raw.get("slot") or "",
        hour=hour,
        away_from_home=bool(raw.get("away_from_home")),
    )

    if d.action == "RECOMMENDATION":
        d = with_offer(d)
        if not d.subject:
            # The pick came back empty at the moment of deciding. Better to
            # say nothing than to send a message with nothing in it — which
            # is what happened when this was discovered a second time inside
            # the composer.
            d.action = "SILENCE"
            d.reason = "nothing_to_offer"

    elif d.action == "MEDICATION_REMINDER":
        # The dose proactive_check chose, kept rather than re-derived.
        try:
            from memory.care_reader import get_due_schedule_items
            due = get_due_schedule_items(user_id, hour=hour) or []
            d.dose = next((x for x in due
                           if str(x.get("label")) == d.detail), None)
        except Exception as e:
            print(f"[Decision] dose lookup failed: {e}")

    elif d.action == "BOUNDARY":
        # And the boundary it was about, before it marks itself spent.
        try:
            from memory.day import events
            m = next((e for e in (events(user_id) or [])
                      if (e.get("label") or e.get("kind") or "").lower()
                      == d.detail.lower()), None)
            if m:
                d.boundary = {"done": m, "next": None}
        except Exception as e:
            print(f"[Decision] boundary lookup failed: {e}")

    return d

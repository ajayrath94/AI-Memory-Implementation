"""
WINDOWS — the gaps in her day, and what she has said about them.

Her day is a sequence: medicine at six, medicine at seven, breakfast at nine,
lunch at one, exercise at half past five, dinner at eight, sleep at ten. Each
of those is a moment to say something about the thing itself. Between them
are gaps, and the gaps are where everything else belongs.

The gaps come from HER schedule. Nine to one is four hours; six to seven is
twenty minutes and not a window at all. Someone with a crowded day has narrow
ones and someone with two events has wide ones, and nothing here needs a
fixed hour or a learned one — which is what open_hours and best_hour were
trying to compute, and they computed her free hours as 10, 11 and 15 while
the hours she actually answers at are 9, 13 and 18.

AND THEN SHE SPEAKS
This is the part nothing has ever done.

    "thoda aaram karungi"        the afternoon is shut, whatever the
                                 schedule says
    "bazar jana hai sham ko"     she will be out; the evening window is gone
    "aaj kuch kaam nahi hai"     a day the schedule thinks is busy is open

A window closed by something she said is the one that matters. A message
arriving after "I'm going to rest" is the kind of thing that makes someone
feel unheard, and no amount of good timing makes up for it.

WHAT THIS RETURNS
A description. Which windows exist today, how wide, what she has said about
each, and whether it is open. Nothing here decides to send anything and
nothing marks itself spent — those were the two things that made boundary()
impossible to test and made her lunch message miss.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

# Below this, two events are back to back and there is no gap between them —
# her two morning tablets are twenty minutes apart and that is not a window.
NARROWEST = 75

# A window she is inside right now, with this much left in it, is still
# usable. Less than that and the next thing is nearly here.
LEAVE_ALONE_AT_THE_END = 20


@dataclass
class Window:
    starts: int                  # minutes past midnight, her clock
    ends: int
    after: str = ""              # the event it opens after
    before: str = ""             # and the one it closes before
    open: bool = True
    why_shut: str = ""
    said: str = ""               # what she said that bears on it

    @property
    def minutes(self) -> int:
        return max(0, self.ends - self.starts)

    def holds(self, now_min: int) -> bool:
        return self.starts <= now_min <= (self.ends - LEAVE_ALONE_AT_THE_END)

    def clock(self) -> str:
        return (f"{self.starts // 60:02d}:{self.starts % 60:02d}"
                f"–{self.ends // 60:02d}:{self.ends % 60:02d}")

    def __str__(self) -> str:
        s = f"{self.clock()} ({self.minutes}m"
        if self.after:
            s += f", after {self.after}"
        s += ")"
        if not self.open:
            s += f" SHUT: {self.why_shut}"
        return s


def _db():
    from supabase_store import get_client
    return get_client()


def _mins(hhmm) -> int:
    try:
        h, m = str(hhmm)[:5].split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return -1


# ── what she has said about being busy ──────────────────────────────────────
#
# She said "thoda aaram karungi" at two and the afternoon shut, which is
# right. It stayed shut through the five o'clock walk boundary where she
# said "haan sair kar aayi" — which plainly means the resting is over.
#
# Nothing ever cleared it, because the shut was derived fresh from a flat
# list of her messages with no order and no end.
#
# So it is written down, and it expires at the next boundary. A boundary
# goes whatever she has said — her lunch happens whether she is resting or
# not — and her answer to it is what decides the rest of the day. Which
# means a shut window can never outlive one boundary, and nothing stays
# wrong for more than a few hours.


def _next_boundary_after(user_id: str, now_min: int) -> int:
    """The next thing on her day that will be asked about.

    A shut window lasts until this and no longer.
    """
    try:
        from memory.day import events, _mins, CONVERSATIONAL_KINDS
        after = [_mins(e.get("due_at")) for e in (events(user_id) or [])
                 if (e.get("kind") or "") in CONVERSATIONAL_KINDS
                 and _mins(e.get("due_at")) > now_min]
        return min(after) if after else 24 * 60
    except Exception as e:
        print(f"[Windows] next boundary failed: {e}")
        return now_min + 180


def shut_window(user_id: str, starts: int, why: str,
                now_min: int = None) -> bool:
    """She has said she is busy. Until the next boundary asks."""
    if now_min is None:
        try:
            from memory.day import _mins_now
            now_min = _mins_now(user_id)
        except Exception:
            now_min = starts
    try:
        _db().table("window_state").upsert({
            "user_id": user_id,
            "on_day": date.today().isoformat(),
            "starts": int(starts),
            "shut": True,
            "why": (why or "")[:160],
            "said_at": datetime.now(timezone.utc).isoformat(),
            "until": _next_boundary_after(user_id, now_min),
        }, on_conflict="user_id,on_day,starts").execute()
        print(f"[Windows] {user_id}: shut {starts // 60:02d}:"
              f"{starts % 60:02d} — {why}")
        return True
    except Exception as e:
        print(f"[Windows] shut write failed: {e}")
        return False


def clear_shut(user_id: str, why: str = "") -> int:
    """She is about again. Everything shut today reopens.

    Called when a boundary answer says the resting is over — which is the
    reset the design was missing.
    """
    try:
        r = (_db().table("window_state").delete()
             .eq("user_id", user_id)
             .eq("on_day", date.today().isoformat())
             .execute())
        n = len(r.data or [])
        if n:
            print(f"[Windows] {user_id}: {n} window(s) reopened"
                  + (f" — {why}" if why else ""))
        return n
    except Exception as e:
        print(f"[Windows] clear failed: {e}")
        return 0


def _stored_shut(user_id: str, now_min: int) -> dict:
    """What is shut right now, by start minute.

    A row past its `until` has expired — the boundary it was waiting for
    has been and gone.
    """
    out = {}
    try:
        rows = (_db().table("window_state").select("*")
                .eq("user_id", user_id)
                .eq("on_day", date.today().isoformat())
                .eq("shut", True).execute()).data or []
        for r in rows:
            if int(r.get("until") or 0) <= now_min:
                continue
            out[int(r["starts"])] = str(r.get("why") or "she said so")
    except Exception as e:
        print(f"[Windows] stored read failed: {e}")
    return out


# ── and the boundary is what resets it ──────────────────────────────────────

def hear_status(user_id: str, text: str) -> str:
    """Are they busy, or about again? Called on each of their messages.

    The boundary goes whatever they have said — their lunch happens whether
    they are resting or not — and this reads the answer.
    """
    said = (text or "").strip()
    if len(said) < 3:
        return ""

    prompt = f"""Someone said: "{said[:200]}"

Does this tell you whether they are free to be interrupted for the next hour
or two? Answer with one word: busy, free, or neither.

busy    — something takes up their time from now on. Resting, sleeping,
          going out, leaving, travelling, running late, a visitor coming,
          starting any activity they will be in the middle of.
free    — they are back and unoccupied. Something is finished and nothing
          has replaced it.
neither — anything else, which is most things. How they feel, what they
          ate, a memory, an opinion, a question.

THREE RULES, IN THIS ORDER:

1. If the message mentions something finished AND something ahead, it is
   BUSY. The thing ahead is what decides it. "I've had lunch, now I'll lie
   down" is busy, not free — the lunch is irrelevant, the lying down is not.

2. Judge what the words MEAN, not their grammatical tense. Many languages
   describe something starting with a completed form. "Sleep has come to me"
   means sleep is ahead of them: busy. "I got tired" is a feeling, not a
   plan: neither.

3. Something finished with NOTHING ahead is never busy. "I went for a walk
   with friends, it was nice" reports a walk that is over: neither, or free
   if they say they are back.

One word."""

    try:
        from llm import ask
        a = (ask(prompt, max_tokens=6) or "").strip().lower()
    except Exception as e:
        print(f"[Windows] status read failed: {e}")
        return ""

    # Logged either way. This fired on nothing for three people and nobody
    # could tell, because a miss and a 'neither' looked identical.
    if a.startswith("free"):
        print(f"[Windows] free: {said[:50]!r}")
        clear_shut(user_id, said[:60])
        return "free"
    if a.startswith("busy"):
        print(f"[Windows] busy: {said[:50]!r}")
        try:
            from memory.day import _mins_now
            now = _mins_now(user_id)
            for w in windows_today(user_id, read_her_words=False):
                if w.holds(now) or w.starts >= now:
                    shut_window(user_id, w.starts, said[:120], now)
                    break
        except Exception as e:
            print(f"[Windows] shut failed: {e}")
        return "busy"
    print(f"[Windows] neither ({a[:12]!r}): {said[:50]!r}")
    return ""


def _her_day(user_id: str) -> List[Dict]:
    """Everything on her day today, in order, with the times."""
    try:
        from memory.day import events
        out = []
        for e in events(user_id) or []:
            at = _mins(e.get("due_at"))
            if at < 0:
                continue
            out.append({"at": at, "label": e.get("label") or e.get("kind"),
                        "kind": e.get("kind") or "", "status": e.get("status")})
        return sorted(out, key=lambda x: x["at"])
    except Exception as e:
        print(f"[Windows] day read failed: {e}")
        return []


def _waking(user_id: str) -> tuple:
    """When she is up, from her own declared rhythm."""
    wake, sleep = 7 * 60, 22 * 60
    try:
        from memory.declared import get_declared
        r = get_declared(user_id).rhythm
        if getattr(r, "wake", None):
            w = _mins(r.wake)
            if w >= 0:
                wake = w
        if getattr(r, "sleep", None):
            s = _mins(r.sleep)
            if s >= 0:
                sleep = s
    except Exception:
        pass
    return wake, sleep


def _said_today(user_id: str) -> List[str]:
    """Her own words today, in order."""
    try:
        from zoneinfo import ZoneInfo
        from memory.declared import get_declared
        tz = ZoneInfo(get_declared(user_id).place.timezone)
        start = datetime.now(tz).replace(hour=0, minute=0, second=0)
        db = _db()
        sess = (db.table("sessions").select("id")
                .eq("user_id", user_id)
                .gte("updated_at", start.isoformat())
                .limit(10).execute()).data or []
        said = []
        for s in sess:
            said += [str(m.get("content") or "")[:200] for m in
                     (db.table("messages").select("content,timestamp")
                      .eq("session_id", s["id"]).eq("role", "user")
                      .gte("timestamp", start.isoformat())
                      .order("timestamp").limit(40).execute()).data or []]
        return [s for s in said if len(s.strip()) > 1]
    except Exception as e:
        print(f"[Windows] said read failed: {e}")
        return []


def _plans(user_id: str, said: List[str], windows: List[Window]) -> None:
    """What she has said about her own time, applied to the windows.

    The thing nothing has ever done. Her schedule says the afternoon is
    free; she said she was going to rest, and that is the better source.
    """
    if not said or not windows:
        return

    listing = "\n".join(
        f"{i}. {w.clock()}" + (f", after {w.after}" if w.after else "")
        for i, w in enumerate(windows))

    prompt = f"""Someone elderly said these things today, in order:

{chr(10).join('- ' + s for s in said[-15:])}

These are the free stretches in her day:

{listing}

Has she said anything that means one of those stretches is NOT free? JSON
only:

{{"shut": [{{"window": 0, "why": "she said she would rest"}}]}}

  Shut means she will not be available, or does not want to be disturbed:
  resting, sleeping, going out, visitors coming, something she has to do.

    "thoda aaram karungi"        resting — shut
    "bazar jana hai sham ko"     out — the evening stretch is shut
    "beti aa rahi hai dopahar"   someone is coming — shut
    "mandir jaungi subah"        out — shut

  NOT shut:

    "thak gayi hoon"             tired is not the same as resting
    "lunch acha tha"             about a meal, not about her time
    "aaj kuch kaam nahi hai"     that is her saying she IS free

  TENSE DECIDES IT, and it is the whole question.

  A stretch is shut by something still AHEAD of her. Anything she has
  already done is finished and takes up none of her day. An errand she
  had completed shut four hours of her morning, because the reading saw
  an errand and did not see that it was over.

  Ahead of her: jana hai, jaungi, aa rahe hain, karna hai.
  Behind her: ho aayi, kar liya, aa gaye, gayi thi, khatam.

  And TODAY only. "Beti kal aayi thi" is yesterday and shuts nothing
  today; "beti kal aa rahi hai" is tomorrow and shuts nothing today
  either.

  If she is reporting rather than planning, shut nothing.

  Only her own time, today, and only when she has actually said it. An
  empty list is the usual answer — most of what she says is not about her
  availability.

No prose."""

    try:
        from llm import ask
        import json as _j
        raw = (ask(prompt, max_tokens=250) or "").replace("```json", "").replace("```", "")
        for s in (_j.loads(raw.strip()).get("shut") or []):
            i = int(s.get("window", -1))
            if 0 <= i < len(windows):
                windows[i].open = False
                windows[i].why_shut = str(s.get("why") or "she said so")[:120]
    except Exception as e:
        print(f"[Windows] plans read failed: {e}")


def windows_today(user_id: str, read_her_words: bool = True) -> List[Window]:
    """The gaps in her day, shaped by what she has said about them.

    A description, not a decision. Nothing here sends anything and nothing
    marks itself spent — boundary() did both, which is why it could not be
    tested and why her lunch message asked about the wrong meal.
    """
    day = _her_day(user_id)
    wake, sleep = _waking(user_id)

    # Her day as a sequence of fixed points, from waking to bed.
    points = [{"at": wake, "label": "waking", "kind": "wake"}]
    points += [e for e in day if wake <= e["at"] <= sleep]
    points.append({"at": sleep, "label": "bed", "kind": "sleep"})
    points.sort(key=lambda x: x["at"])

    out: List[Window] = []
    for a, b in zip(points, points[1:]):
        gap = b["at"] - a["at"]
        if gap < NARROWEST:
            # Her two morning tablets are twenty minutes apart. That is not
            # a window, it is the space between two tablets.
            continue
        out.append(Window(
            # Not the instant the last thing finished — she is still eating.
            starts=a["at"] + 30,
            ends=b["at"],
            after=str(a.get("label") or a.get("kind") or ""),
            before=str(b.get("label") or b.get("kind") or ""),
        ))

    # What she has said she is doing, as written down — not re-derived
    # from a flat list of her messages every call. A shut window lasts
    # until the next boundary and no longer.
    try:
        from memory.day import _mins_now
        for starts, why in _stored_shut(user_id, _mins_now(user_id)).items():
            for w in out:
                if w.starts == starts:
                    w.open = False
                    w.why_shut = why
    except Exception as e:
        print(f"[Windows] stored shut failed: {e}")

    return out


def current(user_id: str, now_min: int = None) -> Optional[Window]:
    """The window she is in right now, if it is open. Usually None."""
    if now_min is None:
        try:
            from memory.day import _mins_now
            now_min = _mins_now(user_id)
        except Exception:
            return None

    for w in windows_today(user_id):
        if w.holds(now_min):
            return w if w.open else None
    return None


def widest(user_id: str) -> Optional[Window]:
    """The longest open stretch of her day.

    Where a rhythm wants to settle: the same window three days running is
    something she can feel, where a different well-chosen gap each day is
    not.
    """
    open_ones = [w for w in windows_today(user_id) if w.open]
    return max(open_ones, key=lambda w: w.minutes) if open_ones else None


def describe(user_id: str) -> str:
    """Her day's windows, one per line. For a log or a dashboard."""
    ws = windows_today(user_id)
    if not ws:
        return "no windows today"
    return "\n".join("  " + str(w) for w in ws)

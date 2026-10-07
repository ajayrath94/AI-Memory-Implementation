"""
THE CARRY — what the evening leaves for the morning.

She said on Tuesday morning that she had caught a cold. The companion asked
after it at lunch, which was right, and on Wednesday asked about her breakfast
and offered her a Kishore Kumar song. The cold was never mentioned again.

The thread holds inside a day and drops at midnight, because nothing has ever
looked at a day whole. summarize_session runs per session — hers had five on
Tuesday — so each one sees a fragment and folds it into a running profile
where "had a cold on Tuesday" becomes "frequently mentions a cold".

WHAT THIS IS
One pass after she has gone to bed, reading everything she said that day, and
writing down two things:

    carry   what deserves a word tomorrow. Usually nothing.
    shape   what kind of day it was, in a sentence.

The morning reads the first. A boundary reads the second. Neither derives
anything: the evening decided, and they honour it.

WHAT CARRIES
Not what was important — what has a TOMORROW. An illness gets better or
worse. A visit has an aftermath. A worry resolves or it does not. A meal is
finished when it is eaten.

And nothing she was merely asked about. On Tuesday night she was asked about
paneer and said another time; asking again on Wednesday is nagging, because
she never raised it.

HOW IT CLOSES
There is no expiry rule. Tomorrow evening's pass reads the same day, sees the
morning asked and sees whether she answered, and decides again. Which is what
a person does.
"""
from datetime import datetime, timedelta
from typing import Dict, Optional

# If her sleep time is not known. Late enough that the day is over, early
# enough that the pass still runs before midnight rolls the date.
DEFAULT_SLEEP_HOUR = 22


def _db():
    from supabase_store import get_client
    return get_client()


def _sleep_hour(user_id: str) -> int:
    try:
        from memory.declared import get_declared
        t = getattr(get_declared(user_id).rhythm, "sleep", None)
        if t and str(t)[:2].isdigit():
            return int(str(t)[:2])
    except Exception:
        pass
    return DEFAULT_SLEEP_HOUR


def _todays_talk(user_id: str, day: str) -> str:
    """Everything she said today, and what was said to her, in order.

    Both sides: "aapki sardi kaisi hai" followed by silence is itself the
    answer to whether the cold still needs asking about.
    """
    try:
        db = _db()
        sess = (db.table("sessions").select("id")
                .eq("user_id", user_id)
                .gte("updated_at", day + "T00:00:00+00:00")
                .limit(20).execute()).data or []
        rows = []
        for s in sess:
            rows += (db.table("messages")
                     .select("role,content,timestamp")
                     .eq("session_id", s["id"])
                     .gte("timestamp", day + "T00:00:00+00:00")
                     .limit(60).execute()).data or []
    except Exception as e:
        print(f"[Carry] read failed: {e}")
        return ""

    rows.sort(key=lambda r: str(r.get("timestamp") or ""))
    lines = []
    for r in rows:
        who = "SHE" if r.get("role") == "user" else "companion"
        txt = str(r.get("content") or "").strip()[:200]
        if txt:
            lines.append(f"{who}: {txt}")
    return "\n".join(lines[-50:])


def _already(user_id: str, day: str) -> Optional[Dict]:
    try:
        rows = (_db().table("day_events").select("*")
                .eq("user_id", user_id).eq("on_day", day)
                .eq("kind", "carry").limit(1).execute()).data or []
        return rows[0] if rows else None
    except Exception:
        return None


def yesterdays(user_id: str) -> Optional[Dict]:
    """What last night left. {carry, shape, status, asked_before}.

    None when there is nothing — which is the usual answer, and the caller
    should say nothing rather than reach for something.
    """
    try:
        from memory.day import _today
        _, today, _m = _today(user_id)
        y = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
        rows = (_db().table("day_events").select("*")
                .eq("user_id", user_id).eq("on_day", y)
                .eq("kind", "carry").limit(1).execute()).data or []
    except Exception as e:
        print(f"[Carry] yesterday read failed: {e}")
        return None
    if not rows:
        return None

    r = rows[0]
    detail = r.get("detail")
    if isinstance(detail, str):
        try:
            import json as _j
            detail = _j.loads(detail)
        except Exception:
            detail = {}
    detail = detail if isinstance(detail, dict) else {}
    if not detail.get("carry") and not detail.get("shape"):
        return None

    return {
        "carry": detail.get("carry") or "",
        "shape": detail.get("shape") or "",
        "status": r.get("status"),
        # Raised once already and she did not answer. Worth one more, never a
        # third: an elderly person asked three times about one cold is being
        # supervised, not accompanied.
        "asked_before": r.get("status") in ("sent", "unknown"),
        "id": r.get("id"),
    }


def write(user_id: str, force: bool = False) -> Optional[Dict]:
    """Read her day, write the two lines. Returns them, or None.

    Runs on the heartbeat like everything else here, and guards itself: after
    her sleep hour, once per day.
    """
    from memory.day import _today
    now, day, _m = _today(user_id)

    if not force:
        if now.hour < _sleep_hour(user_id):
            return None
        if _already(user_id, day):
            return None

    talk = _todays_talk(user_id, day)
    if len(talk) < 40:
        # Nothing said all day. Not a carry — and not a failure either: she is
        # allowed a quiet day.
        return None

    # What was left over from the night before, so a cold already asked about
    # twice is not asked about a third time.
    prev = yesterdays(user_id)
    prev_line = ""
    if prev and prev.get("carry"):
        prev_line = (f"\n\nLast night left this: \"{prev['carry']}\"\n"
                     f"It was {'raised this morning' if prev.get('asked_before') else 'not raised'}.")

    prompt = f"""Here is everything an elderly woman said today, and what her
companion said to her.

{talk}{prev_line}

Two things, as JSON and nothing else:

{{"carry": "...", "shape": "..."}}

carry — what deserves a word TOMORROW morning. One sentence, or empty.

  The test is not whether it was important. It is whether it has a TOMORROW:

    an illness          gets better or worse
    a visit or a call   has an aftermath
    a worry she named   resolves or does not
    something cancelled still stings the next day
    a plan she made     happened or did not

  Not: what she ate, the weather, a song, a film. Those are finished.

  And NOT something she was merely asked about. If the companion suggested it
  and she said "another time", she never raised it — asking again tomorrow is
  nagging.

  EMPTY IS THE USUAL ANSWER. Most days leave nothing. A companion that finds
  something to follow up on every single day is performing attentiveness, and
  she will learn to ignore it.

  If last night left something and it was raised this morning and she did not
  answer, you may carry it ONE more time. Never a third.

  If she answered — she is better, the visit was nice — it is finished.
  Write empty.

shape — what kind of day it was. One sentence, for tomorrow's companion to
  take its cue from, not to repeat back to her.

    "Quiet day, unwell, stayed in."
    "Out with her son most of the day, came back tired."
    "Ordinary, talkative in the evening."

  Describe, do not prescribe. "She was tired" — not "she needs rest".

Both in the language she uses. No prose outside the JSON."""

    try:
        from llm import ask
        import json as _j
        raw = (ask(prompt, max_tokens=250) or "").replace("```json", "").replace("```", "")
        got = _j.loads(raw.strip())
        carry = str(got.get("carry") or "").strip()[:300]
        shape = str(got.get("shape") or "").strip()[:300]
    except Exception as e:
        print(f"[Carry] read failed for {user_id}: {e}")
        return None

    if not carry and not shape:
        return None

    try:
        import json as _j
        _db().table("day_events").insert({
            "user_id": user_id,
            "date": day,
            "on_day": day,
            "kind": "carry",
            "label": (carry or shape)[:120],
            "due_at": f"{_sleep_hour(user_id):02d}:00:00",
            "status": "pending",
            "detail": _j.dumps({"carry": carry, "shape": shape},
                               ensure_ascii=False),
        }).execute()
        print(f"[Carry] {user_id}: " + (f"carry={carry[:60]!r} " if carry else "nothing to carry, ")
              + f"shape={shape[:60]!r}")
    except Exception as e:
        print(f"[Carry] write failed for {user_id}: {e}")
        return None

    return {"carry": carry, "shape": shape}


def hint(user_id: str) -> str:
    """One line for the morning, or "".

    Marks it raised, so tonight's pass knows it was asked and can tell the
    difference between no answer and no question.
    """
    y = yesterdays(user_id)
    if not y or not y.get("carry"):
        return ""
    if y.get("status") in ("confirmed", "denied"):
        return ""

    try:
        from memory.day import set_status
        set_status(y["id"], "sent", "")
    except Exception as e:
        print(f"[Carry] mark sent failed: {e}")

    return (f"\n\nYESTERDAY: {y['carry']}\n"
            f"Ask after it — once, at the start, in her own words and briefly. "
            f"Not as the whole message, and not as a report of what you "
            f"remember. A person asks 'sardi kaisi hai aaj?' and then carries "
            f"on with the morning.")


def shape_hint(user_id: str) -> str:
    """What kind of day yesterday was, for an offer to take its cue from.

    Replaces the weighted draw over her interests, which is how she came to
    be offered the same singer three days running.
    """
    y = yesterdays(user_id)
    if not y or not y.get("shape"):
        return ""
    return (f"\n\nYesterday: {y['shape']}\n"
            f"Let that steer what you offer, and whether to offer at all. "
            f"Do not mention it to her — it is background, not news.")

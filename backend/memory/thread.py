"""
THE THREAD — what was said, so it can be picked up tomorrow.

Clusters hold what is durable: her knee, her son, Kishore Kumar. They cannot
hold "kal aapne dal banayi thi, thodi namkeen ho gayi thi" — that is not a fact
about her, it is a conversation, and it is exactly what you would ask about the
next day.

WHY THE OLD TIERS COULD NOT DO THIS
stm_clusters is keyed by SESSION, so yesterday is invisible today — and
continuity across days is the one thing it exists for. What it stored was not
a conversation either: "FAMILY: Mera beta Arjun Delhi mein doctor hai" is a
fact, and facts are what clusters are for.

And ltm_patterns holds "GENERAL: Nai aj aram kr rahi hoon, abhi Janmashtami hai
toh mandir Jana hai" with a recall count of twenty-three. Undated, permanent,
and fed into the prompt as current a fortnight after Janmashtami.

EVERYTHING CARRIES ITS DATE
That row is why. A line saying "abhi Janmashtami hai" with no date attached
will be read as now, every time, forever.

    cache   7 days     her words, verbatim, by conversation
    stm    14 days     a few lines a day, tagged and dated
    ltm    onwards     a line a month

TAGS ARE CLUSTER IDS, NOT WORDS
Which makes retrieval exact — she says "beta", the resolver points at the Arjun
cluster, and every day tagged with it is found without embedding anything. And
it makes promotion a count rather than a judgement: a tag with no cluster
appearing across three days is something new she keeps returning to.
"""
import json
from datetime import datetime, date, timezone, timedelta
from typing import List, Dict, Optional

CACHE_DAYS = 7
STM_DAYS = 14


def _db():
    from supabase_store import get_client
    return get_client()


def _today(user_id: str) -> date:
    """Her date, not the server's. Railway is not in Bengaluru."""
    try:
        from zoneinfo import ZoneInfo
        from memory.declared import get_declared
        tz = ZoneInfo(get_declared(user_id).place.timezone or "Asia/Kolkata")
        return datetime.now(tz).date()
    except Exception:
        return datetime.now(timezone.utc).date()


def _embed(text: str) -> Optional[List[float]]:
    try:
        from classifier.pillar_classifier import embed_text
        return embed_text(text[:2000])
    except Exception as e:
        print(f"[Thread] embed failed: {e}")
        return None


# ── cache: what was said ──────────────────────────────────────────────────────

def write_cache(user_id: str, session_id: str, messages: List[dict],
                when: date = None) -> int:
    """Her side of a conversation, verbatim, with the day it happened.

    Only her messages. What the companion said is not something she needs
    reminding of, and it would double the rows for nothing.
    """
    day = when or _today(user_id)
    rows = []
    for m in (messages or []):
        if m.get("role") != "user":
            continue
        text = (m.get("content") or "").strip()
        if len(text) < 2:
            continue
        rows.append({
            "user_id": user_id,
            "session_id": session_id or None,
            "happened_on": day.isoformat(),
            "role": "user",
            "text": text[:2000],
            "embedding": _embed(text),
        })

    if not rows:
        return 0
    try:
        _db().table("memory_cache").insert(rows).execute()
        return len(rows)
    except Exception as e:
        print(f"[Thread] cache write failed: {e}")
        return 0


# ── stm: the day, compressed and tagged ───────────────────────────────────────

def _resolve_tags(user_id: str, subjects: List[str]) -> List[str]:
    """Subjects to cluster ids.

    A tag that resolves is a subject she already has; one that does not is
    either new or not worth being a cluster yet. Both are recorded — the
    unresolved ones are what promotion counts.
    """
    if not subjects:
        return []
    ids, loose = [], []
    try:
        from supabase_store import get_client
        rows = (get_client().table("interest_clusters").select("id,label")
                .eq("user_id", user_id).eq("status", "active")
                .limit(200).execute()).data or []
        by_label = {str(r["label"]).lower(): r["id"] for r in rows}
        for s in subjects:
            low = str(s).lower().strip()
            hit = by_label.get(low)
            if not hit:
                # A loose match, because "Kishore Kumar songs" and "Kishore
                # Kumar" are the same tag.
                hit = next((i for l, i in by_label.items()
                            if low and (low in l or l in low)), None)
            if hit and hit not in ids:
                ids.append(hit)
            elif not hit and low:
                # No cluster yet. Kept rather than dropped, because a subject
                # appearing across three days with nothing to resolve to is
                # precisely what promotion looks for — "dal" today is noise,
                # "dal" on Tuesday, Thursday and Sunday is a new interest.
                loose.append(str(s).strip()[:60])
    except Exception as e:
        print(f"[Thread] tag resolve failed: {e}")
    return ids, loose


def write_stm(user_id: str, messages: List[dict], topics: List[Dict] = None,
              when: date = None) -> bool:
    """One row per day: what was said, short enough to carry, tagged.

    Not "FAMILY: mera beta Arjun doctor hai" — that is a fact and belongs in a
    cluster. This is "Arjun called about Diwali. Knee worse in the morning."
    """
    day = when or _today(user_id)
    hers = "\n".join((m.get("content") or "")[:400] for m in (messages or [])
                     if m.get("role") == "user")
    if len(hers.strip()) < 12:
        return False

    prompt = f"""Someone said these things during one day:

{hers}

Write what happened, in two or three short sentences, as a note to yourself
for tomorrow. Third person, plain.

Keep what you would ASK ABOUT tomorrow. Small things are the point; this is
the thread of a conversation, not a record of who they are.

Only what they actually said. Given an example of the kind of thing to keep,
this wrote "ask whether she had a bad night" about someone who had not
mentioned sleeping badly — an illustration read as a list to fill in.

Do not add a question at the end either. Write what happened; what to ask is
obvious from it.

Leave out what is permanently true — that her son lives in Delhi, that she
takes a tablet for her thyroid. That is kept elsewhere.

No dates and no "today" or "yesterday" — the day is stored beside this and
relative words go stale. Say "cooked dal", not "cooked dal today".

Just the note."""

    try:
        from llm import ask
        text = (ask(prompt, max_tokens=250) or "").strip()
    except Exception as e:
        print(f"[Thread] stm compose failed: {e}")
        return False
    if len(text) < 10:
        return False

    # The subjects come from the topics extraction, which already ran on this
    # session — no second call to work out what it was about.
    subjects = [t.get("subject") for t in (topics or []) if t.get("subject")]
    tag_ids, loose = _resolve_tags(user_id, subjects)

    row = {
        "user_id": user_id,
        "happened_on": day.isoformat(),
        "text": text[:1200],
        "tags": tag_ids,
        "untagged": loose,
        "embedding": _embed(text),
    }
    try:
        # One row a day. A second conversation the same day merges into it
        # rather than making a second row — a day is the unit.
        _db().table("memory_stm").upsert(
            row, on_conflict="user_id,happened_on").execute()
        print(f"[Thread] {day}: {text[:70]}")
        return True
    except Exception as e:
        print(f"[Thread] stm write failed: {e}")
        return False


# ── recall: three routes, in order ────────────────────────────────────────────

def recent_days(user_id: str, n: int = 2) -> List[Dict]:
    """The last day or two, always, whatever she just said.

    Continuity is not a search. "Kal aapne dal banayi thi" should be there
    whether or not she mentions dal.
    """
    try:
        return (_db().table("memory_stm").select("happened_on,text,tags")
                .eq("user_id", user_id)
                .order("happened_on", desc=True).limit(n).execute()).data or []
    except Exception as e:
        print(f"[Thread] recent read failed: {e}")
        return []


def days_about(user_id: str, cluster_ids: List[str],
               limit: int = 3) -> List[Dict]:
    """Days tagged with any of these subjects. Exact, no embedding.

    The first route and the one that answers most questions — she names
    something, and the days it came up are found by lookup.
    """
    if not cluster_ids:
        return []
    try:
        return (_db().table("memory_stm").select("happened_on,text,tags")
                .eq("user_id", user_id)
                .overlaps("tags", cluster_ids)
                .order("happened_on", desc=True).limit(limit).execute()).data or []
    except Exception as e:
        print(f"[Thread] tag read failed: {e}")
        return []


def touch(user_id: str, happened_on: str):
    """A day that was recalled stays where it is.

    Neglect is what moves something down a tier; a mention resets its clock.
    """
    try:
        _db().table("memory_stm").update({
            "last_recalled": datetime.now(timezone.utc).isoformat(),
        }).eq("user_id", user_id).eq("happened_on", happened_on).execute()
    except Exception:
        pass


def as_lines(user_id: str, rows: List[Dict]) -> str:
    """For the prompt. Dates become phrases, because a date is not a feeling.

    "2026-09-04" means less to a model than "twelve days ago" even when it
    knows today's date — and an undated line is read as now, which is how
    "abhi Janmashtami hai" survived a fortnight.
    """
    if not rows:
        return ""
    today = _today(user_id)
    out = []
    for r in rows:
        try:
            d = date.fromisoformat(str(r.get("happened_on"))[:10])
        except Exception:
            continue
        gap = (today - d).days
        when = ("today" if gap == 0 else "yesterday" if gap == 1
                else f"{gap} days ago" if gap < 14
                else d.strftime("%-d %B"))
        out.append(f"- {when}: {r.get('text', '')}")
    return "\n".join(out)

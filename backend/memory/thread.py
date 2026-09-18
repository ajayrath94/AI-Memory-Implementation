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
        return [], []
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

Write only what CHANGED or HAPPENED that day. A phone call, a meal, a bad
morning, a visit.

Told to leave out what is permanently true, this wrote "she mentioned that he
lives in Mumbai and works as an engineer" — the instruction named the thing
and the note included it anyway. So: if the sentence would still be true next
year, it does not go here.

"Rajesh called" — yes, that was Tuesday.
"Rajesh lives in Mumbai" — no, that is true every day and is kept elsewhere.

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


# How long something survives WITHOUT being mentioned. A recall resets it —
# these are not deadlines, they are how long neglect takes.
CACHE_KEEP = 7       # her exact words
STM_KEEP = 14        # the day's note
# LTM is not swept. A line a month is small enough to keep indefinitely, and
# it is the only thing left that reaches back beyond a fortnight.


def _stale_before(days: int, user_id: str) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def sweep_cache(user_id: str) -> int:
    """Her verbatim words, after a week. The day's note has them in summary.

    Deleted rather than moved: STM was written from these at session end, so
    there is nothing here that is not already compressed.
    """
    cutoff = (_today(user_id) - timedelta(days=CACHE_KEEP)).isoformat()
    try:
        r = (_db().table("memory_cache").delete()
             .eq("user_id", user_id).lt("happened_on", cutoff).execute())
        n = len(r.data or [])
        if n:
            print(f"[Thread] cache: {n} messages older than {CACHE_KEEP} days")
        return n
    except Exception as e:
        print(f"[Thread] cache sweep failed: {e}")
        return 0


def compress_stm(user_id: str, now: date = None) -> int:
    """Days nobody has touched in a fortnight become a line about their month.

    Grouped by month because that is the next coarser bucket, and because she
    would think of it that way — "that month Arjun was here".
    """
    today = now or _today(user_id)
    cutoff = (today - timedelta(days=STM_KEEP)).isoformat()

    try:
        rows = (_db().table("memory_stm").select("*")
                .eq("user_id", user_id)
                .lt("happened_on", cutoff)
                .order("happened_on").limit(120).execute()).data or []
    except Exception as e:
        print(f"[Thread] stm read failed: {e}")
        return 0

    # A day she has come back to stays. Neglect is what moves things down,
    # not the calendar.
    stale = []
    for r in rows:
        last = r.get("last_recalled")
        if last:
            try:
                if (datetime.now(timezone.utc) -
                        datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                        ).days < STM_KEEP:
                    continue
            except Exception:
                pass
        stale.append(r)

    if not stale:
        return 0

    # By month.
    months = {}
    for r in stale:
        try:
            d = date.fromisoformat(str(r["happened_on"])[:10])
        except Exception:
            continue
        months.setdefault(d.replace(day=1), []).append(r)

    # Never fold a month that is still running. September folded from one
    # stale day while two of its days were still in stm, and produced "the
    # month was quiet and unremarkable" — about a month that had not
    # finished, from a single note that said a neighbour brought sabzi.
    this_month = (now or _today(user_id)).replace(day=1)

    done = 0
    for period, days in months.items():
        if period >= this_month:
            continue
        if _fold_month(user_id, period, days):
            done += len(days)
    return done


def _fold_month(user_id: str, period: date, days: list) -> bool:
    """A month of days into one line, keeping every tag."""
    existing = ""
    try:
        prev = (_db().table("memory_ltm").select("text,tags")
                .eq("user_id", user_id).eq("period", period.isoformat())
                .limit(1).execute()).data or []
        if prev:
            existing = prev[0].get("text") or ""
    except Exception:
        pass

    listing = "\n".join(f"- {r.get('text', '')}" for r in days)
    prior = f"\nAlready recorded for this month:\n{existing}\n" if existing else ""

    prompt = f"""These are notes from separate days in {period.strftime('%B %Y')}:

{listing}
{prior}
Write ONE or TWO sentences covering the month. Third person, plain.

Keep what recurred or mattered — someone visiting, an illness, a change in how
they are living. Drop the particular days: a dal that was too salty on one
Tuesday is not part of a month.

Do not invent a pattern from two mentions, and do not call a month
unremarkable — given one note about a neighbour bringing sabzi, this wrote
"the month was quiet and unremarkable", which says less than the note did.
Write what the days actually contain, however little that is.

No dates inside the sentence — the month is stored beside it.

Just the sentence."""

    try:
        from llm import ask
        text = (ask(prompt, max_tokens=200) or "").strip()
    except Exception as e:
        print(f"[Thread] fold failed: {e}")
        return False
    if len(text) < 8:
        return False

    # Every tag the month's days carried, so LTM can be searched and not only
    # read. "When did her knee start" needs the months to carry the knee.
    tags, loose = [], []
    for r in days:
        for t in (r.get("tags") or []):
            if t not in tags:
                tags.append(t)
        for u in (r.get("untagged") or []):
            if u not in loose:
                loose.append(u)

    try:
        _db().table("memory_ltm").upsert({
            "user_id": user_id,
            "period": period.isoformat(),
            "text": text[:800],
            "tags": tags,
            "untagged": loose[:20],
        }, on_conflict="user_id,period").execute()

        _db().table("memory_stm").delete().eq("user_id", user_id).in_(
            "id", [r["id"] for r in days]).execute()

        print(f"[Thread] {period.strftime('%B %Y')}: {len(days)} days -> {text[:60]}")
        return True
    except Exception as e:
        print(f"[Thread] ltm write failed: {e}")
        return False


def sweep(user_id: str) -> dict:
    """The daily pass. Cheap when nothing has aged, which is most days."""
    return {
        "cache_removed": sweep_cache(user_id),
        "days_folded": compress_stm(user_id),
    }


def _clusters_named(user_id: str, text: str) -> List[str]:
    """Which of her subjects this message touches. Ids, not words.

    The same resolution the tags were written with, so a mention of "beta"
    finds days tagged with Arjun's cluster.
    """
    if not (text or "").strip():
        return []
    try:
        rows = (_db().table("interest_clusters").select("id,label")
                .eq("user_id", user_id).eq("status", "active")
                .limit(200).execute()).data or []
    except Exception:
        return []

    low = text.lower()
    hits = []
    for r in rows:
        label = str(r.get("label") or "").strip().lower()
        if len(label) < 3:
            continue
        if label in low:
            hits.append(r["id"])
    return hits


def _similar_days(user_id: str, text: str, limit: int = 2) -> List[Dict]:
    """The last resort. Only called when tags and dates found nothing."""
    v = _embed(text)
    if not v:
        return []
    try:
        # pgvector does the work; 3072 dimensions cannot be indexed, but a
        # fortnight of days is a handful of rows and a scan is instant.
        r = _db().rpc("match_stm", {
            "p_user_id": user_id, "p_embedding": v, "p_limit": limit,
        }).execute()
        return r.data or []
    except Exception:
        # No rpc defined: fall back to reading and comparing here. Slower and
        # fine at this size.
        try:
            from classifier.pillar_classifier import cosine_similarity
            rows = (_db().table("memory_stm")
                    .select("happened_on,text,tags,embedding")
                    .eq("user_id", user_id).limit(40).execute()).data or []
        except Exception as e:
            print(f"[Thread] similar read failed: {e}")
            return []

        scored = []
        for row in rows:
            emb = row.get("embedding")
            if isinstance(emb, str):
                try:
                    emb = json.loads(emb)
                except Exception:
                    continue
            if not emb:
                continue
            s = cosine_similarity(v, emb)
            # A floor, so "nothing matched" is a possible answer. Without it
            # the nearest of fourteen days is always returned, however far.
            if s >= 0.62:
                scored.append((s, row))
        scored.sort(key=lambda x: -x[0])
        return [r for _s, r in scored[:limit]]


def recall(user_id: str, text: str = "", days_back: int = 1) -> str:
    """What was said recently that bears on this. For the prompt, or "".

    Always the last day. Then whatever she named, by tag. Then, only if both
    came back empty, whatever reads as similar.
    """
    seen, rows = set(), []

    # Continuity, unconditionally.
    for r in recent_days(user_id, days_back):
        key = str(r.get("happened_on"))
        if key not in seen:
            seen.add(key)
            rows.append(r)

    # What she just named.
    tagged = []
    ids = _clusters_named(user_id, text)
    if ids:
        for r in days_about(user_id, ids, limit=3):
            key = str(r.get("happened_on"))
            if key not in seen:
                seen.add(key)
                rows.append(r)
                tagged.append(r)

    # And only then, similarity.
    if text and not tagged:
        for r in _similar_days(user_id, text, limit=2):
            key = str(r.get("happened_on"))
            if key not in seen:
                seen.add(key)
                rows.append(r)

    if not rows:
        return ""

    # Touched, so a day she came back to stays where it is. Neglect is what
    # moves things down.
    for r in rows:
        touch(user_id, str(r.get("happened_on")))

    rows.sort(key=lambda r: str(r.get("happened_on")), reverse=True)
    lines = as_lines(user_id, rows)
    if not lines:
        return ""
    return ("\n\nWHAT WAS SAID RECENTLY — the thread, not facts about them:\n"
            + lines +
            "\nPick it up if it fits. Do not recite it back.")


def months(user_id: str, n: int = 6) -> str:
    """The shape of the last few months. Small enough to read whole.

    A line a month, so no retrieval — twelve lines is a year and it all fits.
    """
    try:
        rows = (_db().table("memory_ltm").select("period,text")
                .eq("user_id", user_id)
                .order("period", desc=True).limit(n).execute()).data or []
    except Exception as e:
        print(f"[Thread] ltm read failed: {e}")
        return ""
    if not rows:
        return ""

    out = []
    for r in reversed(rows):
        try:
            p = date.fromisoformat(str(r["period"])[:10])
        except Exception:
            continue
        out.append(f"- {p.strftime('%B %Y')}: {r.get('text', '')}")
    return "\n\nEARLIER MONTHS:\n" + "\n".join(out) if out else ""

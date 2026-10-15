"""
MENTIONS — when a subject came up, kept so the count survives.

Promotion reads memory_stm.untagged to find subjects that keep returning. That
works for a fortnight and then quietly stops: when a day folds into its month,
its untagged array goes with it. A subject mentioned on the 1st, the 10th and
the 20th would lose the 1st the moment September folds, and the count that
earned it a cluster would silently reset.

So the dates live here instead, one row per subject per day, and compression
cannot touch them.

WHAT IT IS FOR

    promotion     three distinct days in a fortnight makes a habit. The count
                  has to be reliable or the rule is not.

    the offer     "lemon rice teen baar bana chuki hain is mahine" is specific
                  and true. "Aapko South Indian pasand hai" is generic, and a
                  strength number cannot produce the first.

    her question  "Kitni baar banayi maine?" is a count and three dates, and
                  nothing today can answer it.

EVERY SUBJECT, NOT ONLY THE UNRESOLVED ONES
A resolved subject like Arjun accumulates dated mentions too. That overlaps
with user_behavioral_events, which counts recalls against a cluster — but this
answers a different question: not "how strong is this" but "when did she talk
about it". cluster_id is filled in on promotion, so the two join.
"""
from datetime import date, datetime, timezone, timedelta
from typing import List, Dict, Optional


def _db():
    from supabase_store import get_client
    return get_client()


# Phrasings already resolved, so the same sentence never asks twice.
_CANON: dict = {}


def canonical(user_id: str, subject: str, seen_before: list = None) -> str:
    """The name she has used for this thing before, or this one if it is new.

    Every count groups by this string — rhythms, promotion, the diet check,
    the weekday leanings. "Chicken" on one Sunday and "chicken curry and rice"
    on the next were two subjects, so two Sundays of chicken grouped as
    nothing.
    """
    s = (subject or "").strip()
    if len(s) < 3:
        return s

    key = (user_id, s.lower())
    if key in _CANON:
        return _CANON[key]

    if seen_before is None:
        from datetime import date, timedelta
        since = (date.today() - timedelta(days=90)).isoformat()
        try:
            seen_before = sorted({
                str(r["subject"]).strip() for r in
                (_db().table("subject_mentions").select("subject")
                 .eq("user_id", user_id).gte("happened_on", since)
                 .limit(600).execute()).data or []
                if str(r.get("subject") or "").strip()})
        except Exception as e:
            print(f"[Mentions] canon read failed: {e}")
            return s

    # Exactly what she said before, give or take case.
    for prev in seen_before:
        if prev.lower() == s.lower():
            _CANON[key] = prev
            return prev

    if not seen_before:
        _CANON[key] = s
        return s

    listing = "\n".join("- " + p for p in seen_before[:60])
    prompt = f"""Someone has mentioned these things before:

{listing}

They have now mentioned: "{s}"

Is that the SAME THING as one of the above, said differently? Reply with that
line exactly as written above, or the single word NEW.

Same means the same thing — "chicken curry and rice" is chicken, "Mohammed
Rafi ke gaane" is Mohammed Rafi, "ghutne mein dard" is ghutna, "sair" and
"walk" are the same walk.

Different means a different thing of the same kind. Two singers are not the
same singer. Two dishes are not the same dish — chicken curry and chicken
biryani are different, though both are chicken.

NEW is the usual answer. When unsure, answer NEW: splitting one thing in two
costs a pattern, merging two things costs the truth.

One line, nothing else."""

    try:
        from llm import ask
        got = (ask(prompt, max_tokens=40) or "").strip().strip('"').lstrip("- ")
    except Exception as e:
        print(f"[Mentions] canon failed for {s!r}: {e}")
        _CANON[key] = s
        return s

    if not got or got.upper().startswith("NEW"):
        _CANON[key] = s
        return s

    # Only a name she has actually used.
    for prev in seen_before:
        if prev.lower() == got.lower():
            print(f"[Mentions] {s!r} -> {prev!r}")
            _CANON[key] = prev
            return prev

    _CANON[key] = s
    return s


def record(user_id: str, topics: List[Dict], when: date = None) -> int:
    """One row per subject per day. Repeated mentions the same day are one.

    Saying "khichdi" four times in one conversation is one day of evidence,
    which is why the unique key is (user, subject, day) and a second write
    the same day does nothing.
    """
    if not topics:
        return 0
    day = (when or date.today()).isoformat()

    # What she already has a cluster for. A mention of something known is
    # recorded against it, so promotion never offers up a subject that is
    # already knowledge — Rajesh had a cluster and was still a candidate,
    # because cluster_id was only ever filled in ON promotion.
    known = {}
    try:
        for r in (_db().table("interest_clusters").select("id,label")
                  .eq("user_id", user_id).eq("status", "active")
                  .limit(200).execute()).data or []:
            known[str(r["label"]).strip().lower()] = r["id"]
    except Exception as e:
        print(f"[Mentions] cluster read failed: {e}")

    # One name for a thing, or nothing can be counted.
    #
    # "Chicken" on one Sunday and "chicken curry and rice" on the next were
    # two rows, so two Sundays of chicken grouped as two unrelated meals —
    # and every count here groups by this column.
    from datetime import timedelta as _td
    try:
        _since = (date.fromisoformat(day) - _td(days=90)).isoformat()
        _seen = sorted({str(r["subject"]).strip() for r in
                        (_db().table("subject_mentions").select("subject")
                         .eq("user_id", user_id).gte("happened_on", _since)
                         .limit(600).execute()).data or []
                        if str(r.get("subject") or "").strip()})
    except Exception as _ce:
        print(f"[Mentions] canon history failed: {_ce}")
        _seen = []

    rows = []
    for t in topics:
        subject = str(t.get("subject") or "").strip()
        if len(subject) < 2:
            continue
        subject = canonical(user_id, subject, _seen)
        low = subject.lower()
        cid = known.get(low)
        if not cid:
            # Loosely, because "Kishore Kumar's songs" and "Kishore Kumar"
            # are the same subject to her.
            cid = next((i for l, i in known.items()
                        if len(l) > 3 and (low in l or l in low)), None)
        rows.append({
            "user_id": user_id,
            "subject": subject[:80],
            "cluster_id": cid,
            "pillar": t.get("pillar") or None,
            "sentiment": t.get("sentiment"),
            "happened_on": day,
        })
    if not rows:
        return 0

    try:
        _db().table("subject_mentions").upsert(
            rows, on_conflict="user_id,subject,happened_on").execute()
        return len(rows)
    except Exception as e:
        print(f"[Mentions] write failed: {e}")
        return 0


def days_for(user_id: str, subject: str, window: int = 0) -> List[str]:
    """Which days this came up. Newest first.

    Matched loosely, because "lemon rice" and "Lemon Rice" and "lemon rice
    with curd" are the same dish to her.
    """
    q = (_db().table("subject_mentions").select("happened_on")
         .eq("user_id", user_id).ilike("subject", f"%{subject.strip()}%"))
    if window:
        q = q.gte("happened_on",
                  (date.today() - timedelta(days=window)).isoformat())
    try:
        rows = q.order("happened_on", desc=True).execute().data or []
    except Exception as e:
        print(f"[Mentions] read failed: {e}")
        return []
    return [str(r["happened_on"])[:10] for r in rows]


def count_for(user_id: str, subject: str, window: int = 0) -> Dict:
    """How often, when first, when last — the shape of a habit."""
    days = days_for(user_id, subject, window)
    if not days:
        return {"subject": subject, "days": 0, "dates": []}
    return {
        "subject": subject,
        "days": len(days),
        "dates": days,
        "first": days[-1],
        "last": days[0],
        # Spread separates a habit from a spell. Three times across a
        # fortnight is one; three times in a week and nothing since is the
        # other, and a count alone cannot tell them apart.
        "spread": (date.fromisoformat(days[0])
                   - date.fromisoformat(days[-1])).days,
    }


def recurring(user_id: str, min_days: int = 3, window: int = 14,
              unresolved_only: bool = True) -> List[Dict]:
    """Subjects that keep coming back. What promotion acts on.

    unresolved_only skips anything already a cluster — an existing subject
    coming up again is reactivation's job, not promotion's.
    """
    cutoff = (date.today() - timedelta(days=window)).isoformat()
    try:
        rows = (_db().table("subject_mentions")
                .select("subject,happened_on,cluster_id,pillar,sentiment,junk")
                .eq("user_id", user_id).gte("happened_on", cutoff)
                .limit(500).execute()).data or []
    except Exception as e:
        print(f"[Mentions] recurring read failed: {e}")
        return []

    by_subject: Dict[str, dict] = {}
    for r in rows:
        # Marked as not a thing ("aj", "sab", a whole sentence): never a habit.
        if r.get("junk"):
            continue
        if unresolved_only and r.get("cluster_id"):
            continue
        key = str(r.get("subject") or "").strip().lower()
        if len(key) < 3:
            continue
        e = by_subject.setdefault(key, {"subject": r["subject"], "dates": [],
                                        "pillars": [], "sentiments": []})
        d = str(r["happened_on"])[:10]
        if d not in e["dates"]:
            e["dates"].append(d)
        if r.get("pillar"):
            e["pillars"].append(r["pillar"])
        if r.get("sentiment") is not None:
            e["sentiments"].append(float(r["sentiment"]))

    out = []
    for e in by_subject.values():
        if len(e["dates"]) < min_days:
            continue
        e["dates"].sort()
        sents = e["sentiments"]
        out.append({
            "subject": e["subject"],
            "days": len(e["dates"]),
            "dates": e["dates"],
            "spread": (date.fromisoformat(e["dates"][-1])
                       - date.fromisoformat(e["dates"][0])).days,
            "pillar": max(set(e["pillars"]), key=e["pillars"].count)
                      if e["pillars"] else "GENERAL",
            "feeling": round(sum(sents) / len(sents), 2) if sents else 0.0,
        })

    out.sort(key=lambda x: -x["days"])
    return out


def attach(user_id: str, subject: str, cluster_id: str) -> int:
    """Point a subject's mentions at the cluster it became.

    So the cluster can say when it was mentioned, and so promotion stops
    counting something it has already promoted.
    """
    try:
        r = (_db().table("subject_mentions").update({"cluster_id": cluster_id})
             .eq("user_id", user_id).ilike("subject", f"%{subject.strip()}%")
             .is_("cluster_id", "null").execute())
        return len(r.data or [])
    except Exception as e:
        print(f"[Mentions] attach failed: {e}")
        return 0


def about(user_id: str, cluster_id: str, limit: int = 20) -> List[str]:
    """Every day a cluster's subject came up. For the offer, and the caregiver.

    "She has mentioned her knee on eleven days since June" is a sentence with
    evidence under it, which a strength of 3.44 is not.
    """
    try:
        rows = (_db().table("subject_mentions").select("happened_on")
                .eq("user_id", user_id).eq("cluster_id", cluster_id)
                .order("happened_on", desc=True).limit(limit).execute()).data or []
    except Exception:
        return []
    return [str(r["happened_on"])[:10] for r in rows]

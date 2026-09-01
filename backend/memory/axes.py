"""
AXES — which direction someone follows.

A decline currently means one thing less wanted. With interests decomposed it
can mean something more useful: she turned down another Dharmendra film, which
says nothing about Sholay and quite a lot about CAST as a direction. Music might
still be alive.

    Sholay ──cast──→ Dharmendra ──→ his other films
           ──music──→ R.D. Burman ──→ his other songs
           ──era────→ 1975 ──→ that decade

Learning which edge she follows is the fastest useful thing in this system. A
handful of answers settles it, and it transfers across everything in the
category — where day-of-week needs a year of Tuesdays and time-of-day needs
dozens of confounded observations.

HOW IT IS LEARNED
From her replies, not from a setting. A card asking "would you like more
music-based suggestions?" is the same abstract question as the code-mixing
toggle we removed: it asks someone to reason about a mechanism instead of
answering something concrete. She says "haan, unke gaane bahut ache hain" and
that is the signal.

The classifier is the one suggestions already uses. Four reactions map onto
this cleanly:

    accepted            she engaged with the direction
    declined_preference she answered, and that direction is dead
    declined_timing     about the moment, not the axis — ignored
    unrelated           the question did not land; learn nothing

That last distinction matters. Silence and a change of subject are not evidence
against an axis; they are evidence that the question was missed.
"""
from datetime import datetime, timezone
from typing import Dict, Optional

# Enough answers to mean something. Below this the numbers are noise and the
# picker should not be steered by them.
MIN_ANSWERS = 3

# Every direction an offer could travel, proven or not.
KNOWN_AXES = ("music", "cast", "director", "era")

# Below this an axis is dead: asked several times, engaged with none.
DEAD_BELOW = 0.2


def _memory_row(user_id: str) -> dict:
    try:
        from supabase_store import get_client
        rows = (get_client().table("user_memory").select("axes")
                .eq("user_id", user_id).limit(1).execute()).data or []
        a = rows[0].get("axes") if rows else None
        return a if isinstance(a, dict) else {}
    except Exception as e:
        print(f"[Axes] read failed: {e}")
        return {}


def get_axes(user_id: str) -> Dict[str, dict]:
    """{axis: {asked, engaged, rate}} — what is known so far."""
    raw = _memory_row(user_id)
    out = {}
    for axis, v in raw.items():
        if not isinstance(v, dict):
            continue
        asked = int(v.get("asked") or 0)
        eng   = int(v.get("engaged") or 0)
        out[axis] = {
            "asked": asked, "engaged": eng,
            "rate": round(eng / asked, 2) if asked else None,
        }
    return out


def record(user_id: str, axis: str, engaged: Optional[bool]) -> bool:
    """One answer about one axis.

    engaged=None means the question did not land — not counted at all, because
    a missed question is not evidence against the direction it was about.
    """
    if not axis or engaged is None:
        return False
    try:
        from supabase_store import get_client
        db = get_client()
        axes = _memory_row(user_id)
        cur = axes.get(axis) if isinstance(axes.get(axis), dict) else {}
        axes[axis] = {
            "asked":   int(cur.get("asked") or 0) + 1,
            "engaged": int(cur.get("engaged") or 0) + (1 if engaged else 0),
            "last":    datetime.now(timezone.utc).isoformat(),
        }
        db.table("user_memory").update({"axes": axes}).eq("user_id", user_id).execute()
        print(f"[Axes] {user_id}: {axis} {'engaged' if engaged else 'declined'} "
              f"({axes[axis]['engaged']}/{axes[axis]['asked']})")
        return True
    except Exception as e:
        print(f"[Axes] write failed: {e}")
        return False


def live_axes(user_id: str) -> list:
    """Directions worth following, best first.

    An axis with no answers yet is included — untried is not the same as
    rejected, and the only way to learn is to ask.
    """
    axes = get_axes(user_id)
    scored = []
    for axis, v in axes.items():
        if v["asked"] >= MIN_ANSWERS and (v["rate"] or 0) < DEAD_BELOW:
            continue                      # asked enough, never landed
        scored.append((axis, v["rate"] if v["rate"] is not None else 0.5))
    scored.sort(key=lambda x: -x[1])
    out = [a for a, _ in scored]

    # Untried axes go last rather than being left out. An axis nobody has asked
    # about is unknown, not rejected — and trying it is the only way to find
    # out. Without this, someone whose only proven axis is music got nothing at
    # all when the subject was a singer, since a singer has no composer.
    known = set(axes)
    dead = set(dead_axes(user_id))
    out += [a for a in KNOWN_AXES if a not in known and a not in dead]
    return out


def dead_axes(user_id: str) -> list:
    """Directions she has answered about and does not follow. Worth knowing
    separately: these should not be probed again, and offers should not travel
    them."""
    return [a for a, v in get_axes(user_id).items()
            if v["asked"] >= MIN_ANSWERS and (v["rate"] or 0) < DEAD_BELOW]


# ── reading her reply ─────────────────────────────────────────────────────────

def _classify_probe(subject: str, reply: str) -> Optional[str]:
    """Did she engage with this direction, or brush it aside?

    Not the offer classifier. That one asks whether a reply accepts or declines
    something OFFERED, and a probe offers nothing — so "haan, us zamane ki
    filmein bahut acchi thi", which is warm agreement about an era, came back
    as declined_preference. The question is different and needs its own
    judgement.
    """
    import os
    prompt = f"""Someone was asked about: "{subject}"
They replied: "{reply}"

Did they ENGAGE with that subject? One word:

engaged        — they had something to say about it: agreed, disagreed with
                 feeling, reminisced, asked more. Interest, whatever its sign.
not_interested — they dismissed it or were plainly indifferent
missed         — they answered something else, or the reply is not about it

"Haan, us zamane ki filmein achhi thi" is ENGAGED — they warmed to the subject.
"Woh mujhe pasand nahi" is NOT_INTERESTED.
"Aaj ghutne mein dard hai" is MISSED — a different subject entirely.

One word, nothing else."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=10,
            messages=[{"role": "user", "content": prompt}])
        answer = resp.content[0].text.strip().lower().strip(".")
        return answer if answer in ("engaged", "not_interested", "missed") else None
    except Exception as e:
        print(f"[Axes] classify failed: {e}")
        return None

def handle_probe_reply(user_id: str, user_text: str,
                       session_id: Optional[str] = None) -> Optional[str]:
    """If a probe is open, read the reply against it.

    Probes are recorded in the suggestions table with intent='probe' rather than
    in a second pending-question mechanism — an open question awaiting an answer
    is the same shape whether it offered something or asked something.
    """
    try:
        from supabase_store import get_client
        from datetime import timedelta
        from memory.suggestions import PENDING_MINUTES

        db = get_client()
        since = (datetime.now(timezone.utc)
                 - timedelta(minutes=PENDING_MINUTES)).isoformat()
        rows = (db.table("suggestions")
                .select("id,label,cluster_id")
                .eq("user_id", user_id).eq("intent", "probe")
                .is_("reaction", "null").gte("created_at", since)
                .order("created_at", desc=True).limit(1).execute()).data or []
        if not rows:
            return None

        pending = rows[0]
        # label holds "axis:subject" — the axis is what is being learned, the
        # subject is what makes the question judgeable.
        axis, _, subject = (pending.get("label") or "").partition(":")
        reaction = _classify_probe(subject or axis, user_text)
        if not reaction:
            return None

        engaged = {"engaged": True, "not_interested": False}.get(reaction)
        record(user_id, axis, engaged)

        db.table("suggestions").update({
            "reaction": reaction,
            "reacted_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", pending["id"]).execute()
        return reaction
    except Exception as e:
        print(f"[Axes] reply handling failed: {e}")
        return None

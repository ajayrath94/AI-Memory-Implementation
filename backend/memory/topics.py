"""
TOPICS — what she talked about, and how she felt about each thing.

Session valence says how a conversation went. It cannot say what about. She
scores -0.4 and nobody knows whether that is her knee, her son, or being
alone — and those need different responses from a companion and different
words to a caregiver.

WHY NOT THE PILLAR CLASSIFIER
Nineteen centroids in one embedding space, compared against short phrases.
Every pillar scores around 0.7 for the same session:

    HEALTH_WELLNESS 0.739   STRESS 0.718   FEAR 0.708   SADNESS 0.744

"Ghutne mein dard hai" is HEALTH_WELLNESS and SADNESS and arguably TRACK, so
the similarity splits three ways and nothing wins. Four false alerts went out
this morning on the back of it — "sadness increasing, may need emotional
support" about a woman whose last twelve sessions were neutral or positive,
who replied to the resulting message with "are sab acha hai".

SUBJECTS SEPARATE WHERE CATEGORIES DO NOT
"Arjun" and "knee" are particular things. Asked what a conversation was about,
a model names them reliably; asked to choose between nineteen abstractions, it
cannot.

And the emotions are gone from the pillar list, because the sentiment score
already carries them. A negative sentiment on health IS the sadness about her
knee. Having both was what split the signal.

NOTHING IS REPLACED
DIMENSION_ORDER stays exactly as it is — it feeds the classifier, the centroid
tables, personalization and the router. This writes to one new column beside
it. Both run, and in a few weeks there is evidence about which is worth
keeping rather than a hunch.

BUILT TO TRAVEL
Eight pillars, none of them India-specific. FAITH covers puja, namaz, church
and synagogue alike. The subject is whatever she named, in whatever language
she named it.
"""
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

# Eight. Domains only — what a conversation is ABOUT.
#
# Not emotions: the sentiment score carries those, and having both is what
# made nineteen dimensions fail to separate.
#
# Not intents: PLAN, SEARCH, ORDER and TRACK belong to the router deciding
# what to do, not to memory recording what happened.
#
# CAREER_GOAL and ASPIRATIONS stay even though this user is retired. Plenty of
# people over sixty work, consult, or run something, and building for one
# person is how a product ends up fitting only her.
PILLARS = (
    "HEALTH_WELLNESS",   # her body, her medicines, her sleep
    "FAMILY",            # the people
    "ENTERTAINMENT",     # music, films, television, sport
    "FAITH",             # puja, namaz, church — practice of any kind
    "FINANCE",           # money, bills, the pension
    "CAREER_GOAL",       # work, for those who still have it
    "ASPIRATIONS",       # what they want to do or see
    "GENERAL",           # everything else
)


def _db():
    from supabase_store import get_client
    return get_client()


def extract_topics(messages: List[dict]) -> List[Dict]:
    """What she talked about, and how she felt about each.

    Only her words are read. What the companion said is not evidence about her
    mood — and half her sessions are the scheduler talking to itself, with no
    reply at all.
    """
    hers = "\n".join(m.get("content", "")[:400] for m in (messages or [])
                     if m.get("role") == "user")
    if len(hers.strip()) < 10:
        return []

    prompt = f"""Someone said:

{hers}

What did they talk about, and how do they feel about each thing? JSON only:

{{"topics": [{{"subject": "...", "pillar": "...", "sentiment": 0.0}}]}}

subject    the particular thing they named — a person, a place, a dish, a
           condition, a film. In THEIR words: "ghutna" not "knee joint",
           "Arjun" not "son". Keep the name; translate only common nouns.

pillar     one of: {" | ".join(PILLARS)}
           FAITH covers any practice — puja, namaz, church, temple, fasting.
           GENERAL when nothing else fits. Do not force it.

sentiment  -1.0 to 1.0, how THEY feel about that thing in THIS conversation.
           Not how the conversation went overall — how they feel about the
           subject. Someone can be cheerful and still tired of their knee.

At most five. An empty list is fine — a greeting answered with "theek hai" is
not about anything.

Say nothing else."""

    try:
        from llm import ask
        raw = ask(prompt, max_tokens=500).replace("```json", "").replace("```", "")
        found = json.loads(raw.strip()).get("topics") or []
    except Exception as e:
        print(f"[Topics] extraction failed: {e}")
        return []

    out = []
    for t in found[:5]:
        subj = str(t.get("subject") or "").strip()
        if not subj:
            continue
        pillar = str(t.get("pillar") or "GENERAL").strip().upper()
        if pillar not in PILLARS:
            pillar = "GENERAL"
        try:
            s = max(-1.0, min(1.0, float(t.get("sentiment", 0.0))))
        except Exception:
            s = 0.0
        out.append({"subject": subj[:60], "pillar": pillar,
                    "sentiment": round(s, 2)})
    return out


def save_topics(session_id: str, topics: List[Dict]) -> bool:
    if not topics:
        return False
    try:
        _db().table("sessions").update({"topics": topics}).eq("id", session_id).execute()
        return True
    except Exception as e:
        print(f"[Topics] write failed: {e}")
        return False


# ── reading it back ───────────────────────────────────────────────────────────

def _sessions_with_topics(user_id: str, days: int) -> List[Dict]:
    """Only sessions where SHE spoke.

    The scheduler writes one at 00:46 and 08:02 every day and she often never
    replies — a valence of 0 stored for a conversation she was not in.
    Twenty-five of her forty-nine sessions had a real reading.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        return (_db().table("sessions").select("created_at,topics")
                .eq("user_id", user_id).gte("created_at", since)
                .not_.is_("topics", "null")
                .order("created_at").execute()).data or []
    except Exception as e:
        print(f"[Topics] read failed: {e}")
        return []


def feeling_about(user_id: str, subject: str, days: int = 30) -> Optional[float]:
    """How she has felt about one thing lately, or None if she has not said.

    For the picker: a subject she has soured on should not be offered on a
    quiet afternoon, and nothing today can tell it that.
    """
    vals = []
    low = subject.lower().strip()
    for s in _sessions_with_topics(user_id, days):
        for t in (s.get("topics") or []):
            subj = str(t.get("subject", "")).lower()
            if low in subj or subj in low:
                vals.append(float(t.get("sentiment", 0)))
    return round(sum(vals) / len(vals), 2) if vals else None


def by_pillar(user_id: str, days: int = 30) -> Dict[str, Dict]:
    """Rolled up: how each part of her life has been going.

    "HEALTH_WELLNESS averaged -0.4 this month, driven by her knee" is a
    sentence with evidence under it, which "sadness increasing" never had.
    """
    acc: Dict[str, list] = {}
    subj: Dict[str, dict] = {}

    for s in _sessions_with_topics(user_id, days):
        for t in (s.get("topics") or []):
            p = t.get("pillar") or "GENERAL"
            v = float(t.get("sentiment", 0))
            acc.setdefault(p, []).append(v)
            name = str(t.get("subject", ""))
            subj.setdefault(p, {}).setdefault(name, []).append(v)

    out = {}
    for p, vals in acc.items():
        worst = None
        if subj.get(p):
            worst = min(subj[p].items(),
                        key=lambda kv: sum(kv[1]) / len(kv[1]))[0]
        out[p] = {
            "mean": round(sum(vals) / len(vals), 2),
            "mentions": len(vals),
            "lowest": worst,
        }
    return out


def declining(user_id: str, days: int = 30, drop: float = 0.3) -> List[Dict]:
    """Subjects she has soured on. The signal worth telling a caregiver.

    Halves rather than a regression: robust to one bad day, and the output is
    a sentence rather than a slope. "Her average about Arjun went from +0.7 to
    -0.1 over three weeks" is something a son can act on.
    """
    series: Dict[str, list] = {}
    for s in _sessions_with_topics(user_id, days):
        for t in (s.get("topics") or []):
            series.setdefault(str(t.get("subject", "")), []).append(
                float(t.get("sentiment", 0)))

    out = []
    for name, vals in series.items():
        # Three mentions is the floor. Two points is a line through noise.
        if len(vals) < 3:
            continue
        half = len(vals) // 2
        early = sum(vals[:half]) / half
        late = sum(vals[half:]) / (len(vals) - half)
        if early - late >= drop:
            out.append({"subject": name, "was": round(early, 2),
                        "now": round(late, 2), "mentions": len(vals)})

    out.sort(key=lambda x: x["now"] - x["was"])
    return out

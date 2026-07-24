"""
INTEREST SCORES — turn raw behavioural events into a ranked view of what a
person currently cares about.

Scoring happens at READ time, never stored. Weights change, half-lives get
retuned, and decay curves are guesses until proven otherwise — computing on
demand means none of that requires a backfill.

    score = Σ  strength × sentiment_sign × exp(-age_days / half_life)

Three deliberate choices:

  - Recency decay, not raw counts. Someone deep in a World Cup should not still
    be getting cricket nudges eight months later.
  - Signed by sentiment. "I don't enjoy these songs" mentioned five times must
    rank BELOW something mentioned twice warmly, or the engine confidently
    recommends things people dislike.
  - User-declared interests never decay. If someone explicitly told us they
    care about something, letting it fade because they stopped mentioning it
    is just forgetting.
"""

import math
from datetime import datetime, timezone
from typing import List, Dict

HALF_LIFE_DAYS = 30.0

SENTIMENT_SIGN = {
    "positive": 1.0,
    "neutral":  0.5,   # a mention is weak evidence of salience, not affinity
    "negative": -0.6,  # dampened: dislike is informative but shouldn't dominate
}


def _age_days(ts: str) -> float:
    if not ts:
        return 0.0
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
    except Exception:
        return 0.0


def get_interest_scores(user_id: str, pillar: str = "", limit: int = 400) -> List[Dict]:
    """
    Ranked interests for a user, highest first.

    Returns one entry per canonical entity with its decayed score, how often it
    came up, when it was last seen, and the words the person actually used.
    """
    if not user_id:
        return []

    try:
        from supabase_store import get_client
        q = (get_client()
             .table("user_behavioral_events")
             .select("value,surface_form,pillar,sub_pillar,strength,sentiment,"
                     "created_at,source,decay_exempt")
             .eq("user_id", user_id)
             .order("created_at", desc=True)
             .limit(limit))
        if pillar:
            q = q.eq("pillar", pillar)
        rows = (q.execute()).data or []
    except Exception as e:
        print(f"[Interest] fetch failed: {e}")
        return []

    agg: Dict[str, Dict] = {}

    for r in rows:
        name = (r.get("value") or "").strip()
        if not name:
            continue

        strength  = float(r.get("strength") or 0.5)
        sign      = SENTIMENT_SIGN.get((r.get("sentiment") or "neutral").lower(), 0.5)
        exempt    = bool(r.get("decay_exempt")) or (r.get("source") == "user")
        age       = _age_days(r.get("created_at"))
        decay     = 1.0 if exempt else math.exp(-age / HALF_LIFE_DAYS)

        entry = agg.setdefault(name, {
            "entity":       name,
            "pillar":       r.get("pillar"),
            "type":         r.get("sub_pillar"),
            "score":        0.0,
            "mentions":     0,
            "last_seen":    r.get("created_at"),
            "surface_forms": [],
            "user_declared": False,
        })

        entry["score"]    += strength * sign * decay
        entry["mentions"] += 1
        if exempt:
            entry["user_declared"] = True

        sf = (r.get("surface_form") or "").strip()
        if sf and sf not in entry["surface_forms"]:
            entry["surface_forms"].append(sf)

    out = list(agg.values())
    for e in out:
        e["score"] = round(e["score"], 4)
        e["surface_forms"] = e["surface_forms"][:5]

    out.sort(key=lambda x: x["score"], reverse=True)
    return out

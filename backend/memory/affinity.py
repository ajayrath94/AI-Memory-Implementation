"""
AFFINITY — what kind of thing suits which part of the day, for this person.

Two layers.

    THE MAP      a default: devotional music and gardening belong to the
                 morning, a dish to the hour before a meal, a film or a ghazal
                 to the evening. Right for most people on day one, and wrong
                 in detail for nearly everyone.

    THEIR REPLIES  each offer is closed as accepted, declined_timing ("not
                 now"), declined_preference ("not this") or no_response.
                 "Not now" is exactly the signal for this: the thing was fine,
                 the hour was not. "Not this" is about the thing and is
                 already handled on the cluster, so it is ignored here.

The two are blended so the map dominates at first and their own pattern
takes over as it accumulates: four offers' worth of evidence is worth as
much as the default. Someone who says yes to films at four in the afternoon
and "abhi nahi" to them at eight ends up with films in the afternoon.

Nothing here decides. offers.choose() asks which kinds suit this hour, in
order, and still checks the particular thing against the moment.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional


# ── the map ──────────────────────────────────────────────────────────────────

# Slots of an older person's day, by the hour they start.
SLOTS = (
    (5,  "early_morning"),     # waking, prayer, the cool of the morning
    (9,  "morning"),
    (12, "midday"),            # around lunch
    (15, "afternoon"),         # after the rest
    (18, "evening"),           # settled, the television hours
    (21, "night"),             # winding down
)

# category -> weight, per slot. 0..1. Keys are the category keys from the
# interest clusters: sangeet, dekhna, khana, shauk, bhakti.
#
# bhakti is listed for completeness; offers never expand it (fulfil-only),
# so it only matters if something serves a named devotion directly.
DEFAULT: Dict[str, Dict[str, float]] = {
    "early_morning": {"bhakti": 1.0, "sangeet": 0.8, "shauk": 0.6,
                      "khana": 0.3, "dekhna": 0.1},
    "morning":       {"shauk": 0.8, "sangeet": 0.7, "khana": 0.5,
                      "bhakti": 0.5, "dekhna": 0.3},
    "midday":        {"khana": 0.7, "sangeet": 0.6, "shauk": 0.4,
                      "dekhna": 0.4, "bhakti": 0.2},
    "afternoon":     {"sangeet": 0.7, "dekhna": 0.6, "shauk": 0.5,
                      "khana": 0.4, "bhakti": 0.3},
    "evening":       {"dekhna": 1.0, "sangeet": 0.9, "khana": 0.5,
                      "bhakti": 0.5, "shauk": 0.3},
    "night":         {"sangeet": 0.7, "bhakti": 0.6, "dekhna": 0.5,
                      "khana": 0.1, "shauk": 0.1},
}

# How many offers' worth of evidence the default counts as. Higher means
# slower to change; four means a month of one-offer-a-day at a slot moves
# it most of the way.
PRIOR_WEIGHT = 4.0

# How far back their replies count. Habits change; a winter of evening
# films says little about summer.
LOOKBACK_DAYS = 60


def slot_of(now_min: int) -> str:
    h = (now_min // 60) % 24
    name = "night"                       # before five is still the night
    for start, s in SLOTS:
        if h >= start:
            name = s
    return name


# ── their replies ────────────────────────────────────────────────────────────

def _evidence(user_id: str) -> Dict[tuple, Dict[str, float]]:
    """(slot, category) -> {"yes": n, "no": n} from offers they answered.

    accepted          yes
    declined_timing   no, fully: the hour was wrong
    no_response       no, half: silence is weak evidence
    declined_preference  ignored: about the thing, not the hour
    """
    out: Dict[tuple, Dict[str, float]] = {}
    try:
        from supabase_store import get_client
        since = (datetime.now(timezone.utc)
                 - timedelta(days=LOOKBACK_DAYS)).isoformat()
        def _q(cols):
            return (get_client().table("suggestions").select(cols)
                    .eq("user_id", user_id).eq("intent", "recommendation")
                    .not_.is_("reaction", "null")
                    .not_.is_("offered_hour", "null")
                    .gte("created_at", since).limit(500).execute()).data or []
        try:
            rows = _q("cluster_id,offered_hour,reaction,kind")
        except Exception:
            rows = _q("cluster_id,offered_hour,reaction")    # before the column
        if not rows:
            return out
        from memory.offers import hers
        cat_of = {v.get("id"): v.get("category") or ""
                  for v in hers(user_id).values()}
    except Exception as e:
        print(f"[Affinity] evidence read failed: {e}")
        return out

    for r in rows:
        # What was OFFERED, not what it came from. Lag Ja Gale came "because
        # of movie", and her yes to a song counted as a yes to films at two
        # in the afternoon. Rows from before the kind was stored fall back to
        # the interest's category.
        cat = r.get("kind") or cat_of.get(r.get("cluster_id"), "")
        if not cat:
            continue
        key = (slot_of(int(r["offered_hour"]) * 60), cat)
        e = out.setdefault(key, {"yes": 0.0, "no": 0.0})
        rx = r.get("reaction")
        if rx == "accepted":
            e["yes"] += 1
        elif rx == "declined_timing":
            e["no"] += 1
        elif rx == "no_response":
            e["no"] += 0.5
    return out


def weights(user_id: str, now_min: int,
            evidence: Optional[Dict[tuple, Dict[str, float]]] = None) -> Dict[str, float]:
    """category -> how well it suits this hour for this person, 0..1."""
    slot = slot_of(now_min)
    prior = DEFAULT.get(slot, {})
    ev = _evidence(user_id) if evidence is None else evidence
    out = {}
    for cat in set(prior) | {c for (s, c) in ev if s == slot}:
        p = prior.get(cat, 0.3)
        e = ev.get((slot, cat), {"yes": 0.0, "no": 0.0})
        out[cat] = (p * PRIOR_WEIGHT + e["yes"]) / (PRIOR_WEIGHT + e["yes"] + e["no"])
    return out


def describe(user_id: str, now_min: int) -> str:
    """One line for the log: what this hour leans towards, and whether it is
    still the default or has been learned."""
    slot = slot_of(now_min)
    ev = _evidence(user_id)
    w = weights(user_id, now_min, ev)
    learned = sum(v["yes"] + v["no"] for (s, _), v in ev.items() if s == slot)
    top = ", ".join(f"{c} {v:.2f}" for c, v in
                    sorted(w.items(), key=lambda x: -x[1]))
    return f"{slot} ({'default' if not learned else f'{learned:g} replies'}): {top}"

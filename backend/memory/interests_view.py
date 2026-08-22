"""
INTERESTS VIEW — computed from clusters, not stored.

The profile used to hold its own interests block, written by the session
extractor on every summarise. It drifted badly: one profile accumulated 55
entries including twenty music variants ("Bhaag Milkha Bhaag" five times),
eight rephrasings of "Hindu (Namaste greeting)", and topics the person had
mentioned exactly once — physics, Australia, household chores. Only one of the
55 had a cluster behind it.

The clusters already know better. They carry sentiment, a mention count, a
first-seen date, and now a segmentation (preference / concern / person). So
interests are derived from them rather than kept as a second, diverging copy.
Clean the clusters and the interests are clean; that was never true before.

WHAT COUNTS AS AN INTEREST
  Either they said they liked it — relationship=preference with positive
  sentiment, which lands on the first mention — or they keep coming back to it
  (event_count >= REPEAT_FLOOR) without ever saying so. The old code required
  three mentions for everything, which lost stated passions; then that gate was
  removed entirely, which is how "physics" got in.

DISLIKES are the same shape with the sentiment inverted, kept separately so the
companion knows what NOT to suggest.
"""
from typing import Optional

# Someone who mentions a thing this many times means it, whether or not they
# ever said so.
REPEAT_FLOOR = 3

# Health has its own section of the profile and its own handling. A concern is
# not an interest, however often it comes up.
# FAMILY too: people are not interests, and older clusters predate the
# segmentation so the relationship check below cannot catch them. One of them
# surfaced as places: ["Meena"] — a daughter, filed as a place because her
# events carried sub_pillar=place from "daughter lives abroad".
EXCLUDED_PILLARS = {"HEALTH_WELLNESS", "FAMILY"}

# sub_pillar carries the extractor's entity_type. Categories are the user-facing
# names — these appear in the app, so they read as a person would say them.
CATEGORY_BY_TYPE = {
    "artist":  "music",
    "media":   "entertainment",
    "food":    "food",
    "hobby":   "hobbies",
    "place":   "places",
    "person":  None,          # people are not interests; family has its own block
    "health":  None,
}

# Fallback for clusters with no usable sub_pillar (older rows, mostly).
CATEGORY_BY_PILLAR = {
    "ENTERTAINMENT": "entertainment",
    "ASPIRATIONS":   "hopes",
    "CAREER_GOAL":   "work",
    "FINANCE":       None,
    "FAMILY":        None,
    "GENERAL":       None,
}


def _category(cluster: dict, sub_pillar: Optional[str]) -> Optional[str]:
    if sub_pillar and sub_pillar in CATEGORY_BY_TYPE:
        return CATEGORY_BY_TYPE[sub_pillar]
    return CATEGORY_BY_PILLAR.get(cluster.get("pillar") or "")


def _sub_pillars_for(user_id: str, cluster_ids: list) -> dict:
    """Most common sub_pillar per cluster. It lives on events, not clusters."""
    if not cluster_ids:
        return {}
    try:
        from supabase_store import get_client
        rows = (get_client().table("user_behavioral_events")
                .select("cluster_id,sub_pillar")
                .eq("user_id", user_id)
                .in_("cluster_id", cluster_ids).execute()).data or []
    except Exception as e:
        print(f"[Interests] sub_pillar read failed: {e}")
        return {}

    from collections import Counter, defaultdict
    tally = defaultdict(Counter)
    for r in rows:
        if r.get("cluster_id") and r.get("sub_pillar"):
            tally[r["cluster_id"]][r["sub_pillar"]] += 1
    return {cid: c.most_common(1)[0][0] for cid, c in tally.items() if c}


def computed_interests(user_id: str) -> dict:
    """
    {category: [labels]} — what this person actually likes.

    Ordered by strength within each category, so the first entry is the one
    they care most about rather than whichever was mentioned first.
    """
    try:
        from supabase_store import get_client
        rows = (get_client().table("interest_clusters")
                .select("id,label,pillar,relationship,current_state,"
                        "event_count,strength")
                .eq("user_id", user_id).eq("status", "active")
                .order("strength", desc=True).execute()).data or []
    except Exception as e:
        print(f"[Interests] cluster read failed: {e}")
        return {}

    subs = _sub_pillars_for(user_id, [r["id"] for r in rows])
    out = {}

    for r in rows:
        if (r.get("pillar") or "") in EXCLUDED_PILLARS:
            continue

        rel   = (r.get("relationship") or "").lower()
        state = r.get("current_state")
        count = r.get("event_count") or 0

        # Concerns and people are segmented out. Older clusters predate the
        # segmentation and have subject_ref here (self, daughter) rather than a
        # kind — those fall through to the repetition test below.
        if rel in ("concern", "person", "feeling", "action"):
            continue

        stated   = rel == "preference" and state is not None and state > 0
        repeated = count >= REPEAT_FLOOR and (state is None or state >= 0)
        if not (stated or repeated):
            continue

        cat = _category(r, subs.get(r["id"]))
        if not cat:
            continue
        out.setdefault(cat, []).append(r["label"])

    return out


def computed_dislikes(user_id: str) -> list:
    """Things they said they did NOT like — so the companion stops offering
    them. A retraction ("ab main coffee nahi peeti") fades the cluster rather
    than deleting it, precisely so this stays answerable."""
    try:
        from supabase_store import get_client
        rows = (get_client().table("interest_clusters")
                .select("label,relationship,current_state,pillar")
                .eq("user_id", user_id).eq("status", "active").execute()).data or []
    except Exception as e:
        print(f"[Interests] dislike read failed: {e}")
        return []

    out = []
    for r in rows:
        if (r.get("pillar") or "") in EXCLUDED_PILLARS:
            continue
        if (r.get("relationship") or "").lower() != "preference":
            continue
        state = r.get("current_state")
        if state is not None and state < 0:
            out.append(r["label"])
    return out

"""
SOMEWHERE NEW — what changes when she is away, and for how long.

Arriving somewhere is a moment, not a state. The first days at her daughter's
she does not know where anything is; three weeks in she lives there, and a
companion still pointing out the nearest chemist has become a tourist brochure.

    days 0–2    orientation — where things are
    days 3–7    her own life, locally — the food she likes, near where she is
    day 8+      nothing. This is where she lives now, or she is going home soon

The decay is the whole design. Without it this is either useless after a week
or never useful at all.

WHAT ORIENTATION MEANS HERE
Not tourism. She is living somewhere for a fortnight, not sightseeing — so
where the temple is matters and what is worth seeing does not. A chemist, a
park with benches, somewhere to walk. The things you need when you are eighty
and the streets are unfamiliar.

VISIT OR MOVE
The coordinates look identical, and the difference matters: a fortnight decays
to nothing, a move should rebuild her routine entirely. This does not attempt
to tell them apart — after day eight it simply goes quiet, which is right for
both. Asking her outright is the honest fix and belongs with the ambiguity
work, not here.
"""
from typing import Optional, Dict

ORIENT_DAYS = 3     # while she is still finding her feet
LOCAL_DAYS  = 8     # after which it is simply where she is


def phase(user_id: str) -> Optional[str]:
    """orient | local | None — None meaning nothing about being away."""
    try:
        from memory.declared import get_declared
        d = get_declared(user_id)
    except Exception as e:
        print(f"[Away] declared read failed: {e}")
        return None

    if not d.place.away:
        return None

    days = d.place.days_away
    if days is None:
        # Away, but we do not know since when — the arrival stamp is only set
        # going forward. Treat it as settled rather than assuming she has just
        # arrived, because the cost of being wrong is a chemist she found
        # weeks ago.
        return None

    if days <= ORIENT_DAYS:
        return "orient"
    if days < LOCAL_DAYS:
        return "local"
    return None


# Where she is, and what was found there. A hospital does not move and a
# temple does not move, so the answer is the same all fortnight — and without
# this, every greeting during a two-week stay is a fresh Google Places call.
_FOUND: dict = {}


def _nearby(user_id: str, place_type: str, limit: int = 2) -> list:
    """The route takes a place_type and reads her coordinates itself, rather
    than a free-text query."""
    try:
        from routes.integrations import get_nearby_places
        from memory.declared import get_declared
        here = (get_declared(user_id).place.current or "").lower()
        key = (user_id, here, place_type)
        if key in _FOUND:
            return _FOUND[key][:limit]

        data = get_nearby_places(user_id, place_type=place_type) or {}
        out = []
        for p in (data.get("places") or [])[:limit]:
            name = p.get("name")
            if name:
                out.append({"name": name, "address": p.get("address") or "",
                            "distance": p.get("distance") or ""})
        _FOUND[key] = out
        return out
    except Exception as e:
        # place_type, not query — the name in here was wrong, so any failure
        # raised a NameError instead of logging one.
        print(f"[Away] places lookup failed for {place_type!r}: {e}")
        return []


# What kind of place a category can happen in. Coarse on purpose — Google
# takes a free-text type and a narrow one returns nothing in a small town.
#
# The subject is what makes it hers; this only decides where to look.
_PLACE_FOR = {
    "khana":   ("restaurant", "a place to eat"),
    "sangeet": ("music store", "somewhere for music"),
    "bhakti":  ("temple", "somewhere to pray"),
    "dekhna":  ("cinema", "somewhere to watch something"),
    "shauk":   ("park", "somewhere to sit outside"),
}

# Everyone needs these wherever they are, whatever they like.
_ESSENTIAL = ("pharmacy", "hospital")


def _interests_by_category(user_id: str) -> dict:
    """Her live clusters, grouped by category.

    From interest_clusters rather than the declared list, so anything she has
    mentioned in conversation counts — which is most of what she likes, now
    that talking builds clusters at all.
    """
    out = {}
    try:
        from supabase_store import get_client
        rows = (get_client().table("interest_clusters")
                .select("label,attributes,strength")
                .eq("user_id", user_id).eq("status", "active")
                .neq("kind", "event")
                .order("strength", desc=True).limit(40).execute()).data or []
    except Exception as e:
        print(f"[Away] interests read failed: {e}")
        return out

    for r in rows:
        a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        cat = a.get("category")
        if cat in _PLACE_FOR:
            out.setdefault(cat, []).append(r["label"])
    return out


def suggestion(user_id: str) -> dict:
    """One place near her, tied to something she likes. Or nothing.

    Nothing is a fine answer — she is home, or she has been here long enough
    that it is no longer news, or there is nothing of the kind nearby.
    """
    ph = phase(user_id)
    if not ph:
        return {}

    try:
        from memory.declared import get_declared
        d = get_declared(user_id)
        where = d.place.current or ""
    except Exception:
        return {}
    if not where:
        return {}

    # Orienting: what she needs, not what she enjoys. Two days into a strange
    # city the chemist matters more than the cinema.
    if ph == "orient":
        for t in _ESSENTIAL:
            found = _nearby(user_id, t, limit=1)
            if found:
                return {"phase": ph, "place": found[0], "kind": t,
                        "subject": "", "where": where}
        return {}

    # Settled enough to have a life here. Draw across everything she likes,
    # weighted by how much — not likes[0], which meant the same interest
    # every single time.
    import random
    by_cat = _interests_by_category(user_id)
    if not by_cat:
        return {}

    pool = []
    for cat, labels in by_cat.items():
        for i, label in enumerate(labels):
            # The strongest interest in a category is likeliest, the rest
            # still possible.
            pool += [(label, cat)] * max(1, 3 - i)
    if not pool:
        return {}

    random.shuffle(pool)
    for subject, cat in pool[:4]:
        place_type, _ = _PLACE_FOR[cat]
        found = _nearby(user_id, place_type, limit=1)
        if found:
            return {"phase": ph, "place": found[0], "kind": place_type,
                    "subject": subject, "where": where}
    return {}


def hint(user_id: str) -> str:
    """A line for the composer, or nothing.

    Facts, not instructions about tone — the same rule as the weather. It is
    told what is nearby and what she likes; what to say about it is its own
    judgement.
    """
    s = suggestion(user_id)
    if not s:
        return ""

    p = s["place"]
    place = p["name"] + (f" ({p['distance']})" if p.get("distance") else "")

    if s["phase"] == "orient":
        return (
            f"\n\nThey arrived in {s['where']} recently and will not know "
            f"where anything is. Nearby: {place} ({s['kind']}).\n"
            "Mention it once, in passing, the way a neighbour would — not a "
            "list and not a tour. They are living there for a while, not "
            "sightseeing.\n"
            "This is the POINT of the message on the first days, not a "
            "garnish on it. Told about the chemist round the corner, the "
            "composer wrote about the weather and her music and left the "
            "chemist out — which is the one thing she cannot find for "
            "herself in a city she does not know."
        )

    return (
        f"\n\nThey are in {s['where']}, away from home, and they like "
        f"{s['subject']}. Nearby: {place}.\n"
        "If it fits what you were going to say, mention it — because of the "
        "thing they like, not because it is close. A maps app can tell them "
        "what is 400m away. Do not list the distance."
    )

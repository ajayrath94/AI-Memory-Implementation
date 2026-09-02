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


def _nearby(user_id: str, place_type: str, limit: int = 2) -> list:
    """The route takes a place_type and reads her coordinates itself, rather
    than a free-text query."""
    try:
        from routes.integrations import get_nearby_places
        data = get_nearby_places(user_id, place_type=place_type) or {}
        out = []
        for p in (data.get("places") or [])[:limit]:
            name = p.get("name")
            if name:
                out.append({"name": name, "address": p.get("address") or "",
                            "distance": p.get("distance") or ""})
        return out
    except Exception as e:
        print(f"[Away] places lookup failed for {query!r}: {e}")
        return []


def hint(user_id: str) -> str:
    """A line for the composer, or nothing.

    Nothing is the common answer — she is at home, or she has been away long
    enough that it is no longer news.
    """
    ph = phase(user_id)
    if not ph:
        return ""

    try:
        from memory.declared import get_declared
        d = get_declared(user_id)
        where = d.place.current or "somewhere new"
        days = d.place.days_away
    except Exception:
        return ""

    if ph == "orient":
        # What someone needs in an unfamiliar place at that age: a temple if
        # they pray, a chemist, somewhere to sit outside. Not restaurants.
        wants = []
        if (d.interests or {}).get("bhakti"):
            wants.append("temple")
        wants += ["pharmacy", "park"]

        found = []
        for w in wants[:2]:
            found += _nearby(user_id, w, limit=1)
        if not found:
            return ""

        listed = "; ".join(
            f"{p['name']}" + (f" ({p['distance']})" if p["distance"] else "")
            for p in found)
        return (
            f"They have recently arrived in {where}"
            + (f", {days} day(s) ago" if days is not None else "")
            + " and will not know where "
            f"anything is. Nearby: {listed}.\n"
            "Mention ONE of these, the one most likely to matter to them, as a "
            "passing helpful remark. Not a list, not a tour — the way a "
            "neighbour would mention it. They are living there for a while, "
            "not sightseeing."
        )

    # local: her own life, where she happens to be
    likes = []
    for cat in ("khana", "shauk"):
        likes += ((d.interests or {}).get(cat) or [])
    if not likes:
        return ""

    subject = likes[0]
    # A dish is not a place type. "restaurant" is the closest the route
    # offers, and the subject is what makes the mention hers.
    found = _nearby(user_id, "restaurant", limit=1)
    if not found:
        return ""

    return (
        f"They like {subject}, and they are in {where} at the moment. "
        f"Nearby: {found[0]['name']}"
        + (f" ({found[0]['distance']})" if found[0]["distance"] else "") + ".\n"
        "Mention it once, lightly — something of theirs that happens to be "
        "close by, not a recommendation."
    )

"""
EMERGENCY — numbers she can tap.

She mentioned chest pain and her son got an email. She got a reply about her
day. The alert chain works and none of it helps the woman sitting alone with
the pain, at the moment she has it.

A screen she opens is a tool. A message that arrives saying "I noticed your
chest pain, here is a cardiac hospital" is the thing that makes her feel
watched — so this is somewhere she goes, not something that comes to her.

WHAT IS ON IT, IN ORDER
    her caregiver      the person she actually wants. One tap.
    ambulance          108
    emergency          112
    the hospital       nearest to where she is now

Nothing else. No banner, no explanation of why that hospital, and no mention
of her conditions. She knows what is wrong with her; she needs a number.

THE NUMBERS ARE CONSTANTS, NOT A MODEL CALL
112 reaches everything in India and 108 is the ambulance in most states. Those
are facts and they live in code. A model asked for an emergency number might
be right, and an elderly woman dialling a hallucinated digit while frightened
is the worst failure this product could have.

HER CONDITIONS SHAPE THE SEARCH, SILENTLY
A chest-pain history means the nearest HOSPITAL rather than the nearest clinic.
The screen never says why. The rule from everywhere else in this codebase: her
state decides what is chosen, never what is said.

BUILT TO TRAVEL
The national numbers are per country and everything else is not. Swapping
_NATIONAL for another country's is the whole change.
"""
from typing import Dict, List, Optional

# India. 112 is the single emergency number and reaches police, fire and
# ambulance; 108 is the dedicated ambulance in most states. Both are worth
# showing — an elderly user is likelier to have heard of 108.
_NATIONAL = [
    {"label": "Ambulance", "label_hi": "Ambulance", "number": "108"},
    {"label": "Emergency", "label_hi": "Emergency", "number": "112"},
]

# What kind of place to look for. A hospital, not a clinic, when there is
# cardiac history — a clinic cannot help with a heart.
_SERIOUS = ("chest pain", "heart", "cardiac", "stroke", "bp", "blood pressure",
            "hypertension", "diabetes", "breathless", "asthma")


def _db():
    from supabase_store import get_client
    return get_client()


def _caregivers(user_id: str) -> List[Dict]:
    """The people she would actually ring, with the word she uses for them."""
    out = []
    try:
        from memory.alert_engine import get_caregivers_for_user
        for link in get_caregivers_for_user(user_id):
            cg = link.get("caregivers") or {}
            phone = (cg.get("phone") or "").strip()
            if not phone:
                continue
            out.append({
                "name": cg.get("name") or "",
                "relation": (link.get("relationship") or "").strip(),
                "number": phone,
            })
    except Exception as e:
        print(f"[Emergency] caregiver read failed: {e}")
    return out


def _needs_a_hospital(user_id: str) -> bool:
    """Is a clinic enough, or does she need somewhere with a cardiac unit?

    Read from her conditions and never shown. She knows what is wrong with
    her and does not need it repeated on a screen she opens when frightened.
    """
    try:
        from memory.profile_store import get_user_profile
        h = (get_user_profile(user_id) or {}).get("health") or {}
        blob = " ".join(str(x) for x in
                        (h.get("conditions") or []) + (h.get("concerns") or [])).lower()
        return any(s in blob for s in _SERIOUS)
    except Exception:
        return True          # when unsure, the bigger place


# Google's type=hospital is loose. Searching near her returned "S.A Medical",
# a chemist, then an eye clinic, and only third an actual hospital. A woman
# with chest pain sent to a chemist is the failure this screen exists to
# prevent.
_REALLY_A_HOSPITAL = ("hospital", "medical centre", "medical center",
                      "nursing home", "multispecial", "multi-special")
_NOT_A_HOSPITAL = ("medical store", "medicals", "pharmacy", "chemist",
                   "nethralaya", "dental", "clinic", "diagnostics", "lab",
                   "optical", "ayurved")


def _nearest(user_id: str, kind: str) -> List[Dict]:
    """Up to two: the nearest, and the nearest she can ring.

    They are often not the same place. Google has no phone number for plenty
    of hospitals, and an address alone is little use to a frightened woman —
    but the nearest one still matters, because someone driving her there does
    not need to ring ahead.
    """
    try:
        from routes.integrations import get_nearby_places, place_details
        data = get_nearby_places(user_id, place_type=kind) or {}
        places = [p for p in (data.get("places") or []) if p.get("name")]
    except Exception as e:
        print(f"[Emergency] places lookup failed: {e}")
        return None
    if not places:
        return None

    def rank(p):
        n = str(p.get("name", "")).lower()
        if any(w in n for w in _REALLY_A_HOSPITAL):
            return 0
        if any(w in n for w in _NOT_A_HOSPITAL):
            return 2
        return 1

    # Prefer one she can actually ring. Shirdi Sai ranked first and Google
    # has no number for it, so the card showed a name and an address and
    # nothing to dial — which is most of the point.
    # Hospitals only, as a filter and not a preference. Ranking alone let a
    # chemist through the moment it was the one with a phone number — and
    # "S.A Medical" is where she buys her tablets, not where she goes with
    # chest pain.
    hospitals = [p for p in places if rank(p) == 0] or \
                [p for p in places if rank(p) <= 1]
    if not hospitals:
        return None

    from routes.integrations import place_details as _pd

    # Two of them, because the closest is not always the one she can ring.
    #   nearest      whatever Google knows about it
    #   reachable    the nearest one with a number, if that is a different one
    out = []
    seen = set()
    for cand in hospitals[:4]:
        try:
            d = _pd(cand.get("place_id")) or {}
        except Exception:
            d = {}
        entry = {
            "name": d.get("name") or cand.get("name"),
            "address": d.get("address") or cand.get("address") or "",
            "phone": d.get("phone") or "",
            "kind": kind,
        }
        if not out:
            out.append(entry)                       # the nearest, as it is
            seen.add(entry["name"])
        elif entry["phone"] and entry["name"] not in seen:
            out.append(entry)                       # and one she can ring
            break
        if len(out) == 1 and out[0]["phone"]:
            break                                   # the nearest already has one

    return out



def card(user_id: str) -> Dict:
    """Everything the screen shows. Ordered as she would want it.

    Her people first — a son who knows her history is more use in the first
    minute than any hospital switchboard.
    """
    entries: List[Dict] = []

    for c in _caregivers(user_id):
        label = c["name"]
        if c["relation"]:
            label = f"{c['name']} · {c['relation']}"
        entries.append({"label": label, "number": c["number"],
                        "kind": "caregiver"})

    for n in _NATIONAL:
        entries.append({"label": n["label"], "number": n["number"],
                        "kind": "national"})

    for place in _nearest(user_id,
                          "hospital" if _needs_a_hospital(user_id) else "clinic"):
        entries.append({"label": place["name"],
                        "number": place.get("phone", ""),
                        "address": place.get("address", ""),
                        "kind": "hospital"})

    where = ""
    try:
        from memory.declared import get_declared
        where = get_declared(user_id).place.current or ""
    except Exception:
        pass

    return {"entries": entries, "where": where}

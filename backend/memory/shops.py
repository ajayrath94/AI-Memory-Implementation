"""
SHOPS — where the things on her list can be bought ("Kahan milega?").

She keeps a market list ("sabudana bhi likh lena") and opens it before
leaving the house. What she then needs is where to go: the chemist for the
tablets, the kirana for atta and dal, the sabzi wala for tamatar.

EACH ITEM IS SORTED ONCE
Every item carries the kind of shop it comes from, kept on the item itself
as an app note (fields["_shop"], never shown or read out). Only items with
no note yet — new ones, or one whose name changed — go to the model, in one
call with the list's name and purpose for context and the groups already in
use, so "Kirana" stays "Kirana". Opening the list again costs nothing, a
kept list carries its sorting into next time, and a ten-item list with one
new item is one small call, not a re-read. No word lists: whether a list is
shopping at all ("Shubham ko batana" is not) is the model's judgement from
the whole list, stored per item as "not a thing to buy".

TWO WAYS TO CHOOSE A SHOP
nearest  open shops first, then by distance — for popping out.
best     within a comfortable walk (BEST_KM), open now, ranked by rating
         weighted by how many people rated it (a 5.0 from three people is
         not a 4.6 from nine hundred). And first, when one supermarket near
         her covers two or more of the groups, that one shop for most of the
         list, saying what it will not have.
Both come from the same places search Nancy uses in chat.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

MAX_GROUPS = 6
SHOPS_PER_GROUP = 3
BEST_KM = 1.5            # about 20 minutes at her pace
ONE_STOP_KM = 2.0
PRIOR_RATING = 4.0       # what an unknown shop is assumed to be
PRIOR_WEIGHT = 50        # how many ratings it takes to trust its own

NOTE = "_shop"


def _what(row: Dict) -> str:
    return str((row.get("fields") or {}).get("what") or "").strip()


def _lang(user_id: str) -> str:
    try:
        from memory.profile_store import get_user_profile
        return str((get_user_profile(user_id) or {}).get("language_pref") or "hinglish").lower()
    except Exception:
        return "hinglish"


def _first_json(raw: str):
    starts = [k for k in ((raw or "").find("{"), (raw or "").find("[")) if k >= 0]
    if not starts:
        return None
    return json.JSONDecoder().raw_decode(raw[min(starts):])[0]


def _note_of(row: Dict) -> Optional[Dict]:
    """The item's shop note, if it was made for the item as it is now."""
    raw = (row.get("fields") or {}).get(NOTE)
    if not raw:
        return None
    try:
        n = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return None
    if str(n.get("for") or "").strip().lower() != _what(row).lower():
        return None              # renamed since: sort it again
    return n


_LABEL_LANG = {
    "english": "English",
    "hindi":   "Hindi in Devanagari script",
}


def _sort_items(lst: Dict, rows: List[Dict], known: List[Dict], lang: str) -> Dict[str, Dict]:
    """One model call for the items with no note. {item id: note}."""
    from llm import ask
    lines = []
    for r in rows:
        f = {k: v for k, v in (r.get("fields") or {}).items()
             if k != "what" and not str(k).startswith("_") and str(v).strip()}
        extra = ", ".join(f"{k}: {v}" for k, v in f.items())
        lines.append(f"- {_what(r)}" + (f" ({extra})" if extra else ""))
    groups_in_use = "; ".join(sorted({f"{g['label']} = {g['search']}" for g in known})) or "none yet"
    label_lang = _LABEL_LANG.get(lang, "Hinglish (Hindi in Roman letters)")

    prompt = f"""An older woman in India keeps a list on her phone.

List name: {lst.get('name') or ''}
What it is for: {lst.get('purpose') or ''}
Kinds of shop already used on this list: {groups_in_use}
Items to sort:
{chr(10).join(lines)}

For each item decide: is it something she will BUY from a shop? Things on
a packing list, a to-do list, people to call or things to tell someone are
not. If it is, which kind of shop in an Indian neighbourhood sells it
(chemist, kirana, vegetable seller, sweet shop, puja items shop, bakery,
dairy...). Reuse a kind already used above when it fits. If she named a shop
for the item, that shop is its kind and its search is that shop's name.
Also say whether a big supermarket (Reliance Smart, DMart, More) would
normally have it.

Reply with JSON only, one entry per item, in the same order:
[{{"item": "the item exactly as written",
   "buy": true or false,
   "search": "what to search on a map, in English: a shop name she gave, or a short kind of shop such as 'pharmacy', 'kirana store', 'vegetable shop', 'puja store', 'bakery'",
   "label": "that kind of shop as she would say it, in {label_lang}, two or three words",
   "supermarket": true or false}}]"""
    raw = ask(prompt, max_tokens=1500)
    try:
        out = _first_json(raw)
    except Exception:
        out = None
    if not isinstance(out, list):
        print(f"[Shops] sorting unreadable: {str(raw)[:160]!r}")
        return {}
    by_name = {}
    for e in out:
        if isinstance(e, dict) and str(e.get("item") or "").strip():
            by_name[str(e["item"]).strip().lower()] = e
    notes = {}
    for r in rows:
        e = by_name.get(_what(r).lower())
        if not e:
            continue
        if e.get("buy") and str(e.get("search") or "").strip():
            n = {"for": _what(r),
                 "search": str(e["search"]).strip()[:80],
                 "label": str(e.get("label") or e["search"]).strip()[:40],
                 "super": bool(e.get("supermarket"))}
        else:
            n = {"for": _what(r), "none": True}
        notes[r["id"]] = n
    return notes


def plan(user_id: str, list_id: str) -> Dict:
    """{buying, groups:[{search, label, items, super}]} for one of her lists.

    Items not sorted yet are sorted now (one model call) and the notes kept
    on them. A failed call leaves those items out this time and sorts them
    next time; it is never saved as an answer.
    """
    from memory import lists as L
    lst = L.get(user_id, list_id)
    if not lst:
        return {"buying": False, "groups": []}
    rows = [r for r in L._items_of(lst["id"], include_done=False) if _what(r)]
    if not rows:
        return {"buying": False, "groups": []}

    notes = {r["id"]: _note_of(r) for r in rows}
    todo = [r for r in rows if notes[r["id"]] is None]
    if todo:
        known = [n for n in notes.values() if n and not n.get("none")]
        fresh = _sort_items(lst, todo, known, _lang(user_id))
        for item_id, n in fresh.items():
            notes[item_id] = n
            L.note_on_item(item_id, NOTE, json.dumps(n, ensure_ascii=False))
        print(f"[Shops] {user_id} {lst.get('name')!r}: sorted {len(fresh)}/{len(todo)} new items")

    groups: Dict[str, Dict] = {}
    for r in rows:
        n = notes.get(r["id"])
        if not n or n.get("none"):
            continue
        k = n["search"].lower()
        g = groups.setdefault(k, {"search": n["search"], "label": n["label"],
                                  "items": [], "super": True})
        g["items"].append(_what(r))
        g["super"] = g["super"] and bool(n.get("super"))
    out = sorted(groups.values(), key=lambda g: -len(g["items"]))[:MAX_GROUPS]
    return {"buying": bool(out), "groups": out}


def _score(p: Dict) -> float:
    """Rating, pulled towards PRIOR_RATING when few people have rated it."""
    r = p.get("rating")
    v = p.get("reviews") or 0
    if r is None:
        return PRIOR_RATING - 0.5
    return (float(r) * v + PRIOR_RATING * PRIOR_WEIGHT) / (v + PRIOR_WEIGHT)


def _shop(p: Dict) -> Dict:
    return {
        "name":        p.get("name"),
        "address":     p.get("address"),
        "distance_km": p.get("distance_km"),
        "walk_min":    p.get("walk_min"),
        "open":        p.get("open"),
        "rating":      p.get("rating"),
        "reviews":     p.get("reviews"),
        "map_url":     p.get("map_url"),
    }


def _candidates(user_id: str, search: str) -> List[Dict]:
    from routes.integrations import get_nearby_places
    try:
        r = get_nearby_places(user_id, search, with_phone=False, keep=10) or {}
    except Exception as e:
        print(f"[Shops] places failed for {search!r}: {e}")
        return []
    return r.get("places") or []


def _far(p: Dict) -> float:
    d = p.get("distance_km")
    return d if d is not None else 1e9


def _nearest(places: List[Dict]) -> List[Dict]:
    return sorted(places, key=lambda p: (p.get("open") is False, _far(p)))[:SHOPS_PER_GROUP]


def _best(places: List[Dict], within: float = BEST_KM) -> List[Dict]:
    ok = [p for p in places if p.get("open") is not False and _far(p) <= within]
    if not ok:
        return _nearest(places)
    return sorted(ok, key=lambda p: (-_score(p), _far(p)))[:SHOPS_PER_GROUP]


def where(user_id: str, list_id: str, mode: str = "nearest") -> Dict:
    """The plan, with shops for each group: the nearest, or the best."""
    mode = "best" if mode == "best" else "nearest"
    p = plan(user_id, list_id)
    if not p.get("buying"):
        return {"buying": False, "mode": mode, "groups": [], "one_stop": None}
    groups = [dict(g) for g in p["groups"]]
    supers = [g for g in groups if g.get("super")]
    want_one_stop = mode == "best" and len(supers) >= 2

    searches = [g["search"] for g in groups] + (["supermarket"] if want_one_stop else [])
    with ThreadPoolExecutor(max_workers=min(6, len(searches))) as ex:
        found = list(ex.map(lambda s: _candidates(user_id, s), searches))

    pickf = _best if mode == "best" else _nearest
    for g, places in zip(groups, found):
        g["shops"] = [_shop(x) for x in pickf(places)]

    one_stop = None
    if want_one_stop:
        top = _best(found[-1], within=ONE_STOP_KM)
        top = [x for x in top if _far(x) <= ONE_STOP_KM and x.get("open") is not False]
        if top:
            missing = [i for g in groups if not g.get("super") for i in g["items"]]
            one_stop = {
                "shop":    _shop(top[0]),
                "covers":  [g["label"] for g in supers],
                "missing": missing,
            }
    return {"buying": True, "mode": mode, "groups": groups, "one_stop": one_stop}

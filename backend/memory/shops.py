"""
SHOPS — where the things on her list can be bought.

She keeps a market list ("sabudana bhi likh lena") and opens it before
leaving the house. What she then needs is where to go for it: the chemist
for the tablets, the kirana for atta and dal, the sabzi wala for tamatar.

TWO STEPS
plan()   reads the list and decides, in one model call, whether it is a
         list of things to BUY at all, and if so which kind of shop each
         thing comes from. No word lists: "Shubham ke liye baatein" or a
         packing list is not shopping, and that is the model's judgement
         from the whole list, not a match on words. A shop she named on an
         item ("yeh Big Bazaar se") is used as it is.
where()  the plan, plus the nearest few real shops for each group, from the
         same places search Nancy uses in chat (distance from where she is,
         open now, a map link).

Only what is still to get is read; ticked items are done. The plan is
kept in memory for a day, keyed on the list's name and what is left on it,
so opening the list again costs nothing and a changed list is read afresh.
"""
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

PLAN_TTL = 24 * 3600
MAX_GROUPS = 5
SHOPS_PER_GROUP = 3

_PLANS: Dict[str, tuple] = {}     # key -> (saved_at, plan)


def _what(row: Dict) -> str:
    f = row.get("fields") or {}
    return str(f.get("what") or "").strip()


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


def _key(lst: Dict, rows: List[Dict]) -> str:
    body = json.dumps([lst.get("id"), lst.get("name"), lst.get("purpose"),
                       sorted(json.dumps(r.get("fields") or {}, sort_keys=True) for r in rows)],
                      ensure_ascii=False)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()


_LABEL_LANG = {
    "english":  "English",
    "hindi":    "Hindi in Devanagari script",
}


def _ask_plan(lst: Dict, rows: List[Dict], lang: str) -> Optional[Dict]:
    from llm import ask
    items = []
    for r in rows:
        f = dict(r.get("fields") or {})
        what = str(f.pop("what", "") or "").strip()
        if not what:
            continue
        extra = ", ".join(f"{k}: {v}" for k, v in f.items() if str(v).strip())
        items.append(f"- {what}" + (f" ({extra})" if extra else ""))
    if not items:
        return {"buying": False, "groups": []}

    label_lang = _LABEL_LANG.get(lang, "Hinglish (Hindi in Roman letters)")
    prompt = f"""An older woman in India keeps this list on her phone.

List name: {lst.get('name') or ''}
What it is for: {lst.get('purpose') or ''}
Still to do:
{chr(10).join(items)}

1. Is this a list of things she will BUY from shops? A packing list, a
   to-do list, people to call or things to tell someone are not.
2. If it is, group the items by the kind of shop in an Indian
   neighbourhood where she would buy them (chemist, kirana, vegetable
   seller, sweet shop, puja items shop, bakery, supermarket...). Use as few
   groups as make sense; at most {MAX_GROUPS}. If she named a shop for an
   item, that shop is its own group and its search is that shop's name.

Reply with JSON only:
{{"buying": true or false,
  "groups": [{{"search": "what to search on a map, in English: a shop name she gave, or a short kind of shop such as 'pharmacy', 'kirana store', 'vegetable shop', 'supermarket', 'puja store', 'bakery'",
              "label": "the kind of shop as she would say it, in {label_lang}, two or three words",
              "items": ["each item exactly as written in the list"]}}]}}
Every item goes in exactly one group. If buying is false, groups is []."""
    raw = ask(prompt, max_tokens=1200)
    try:
        out = _first_json(raw)
    except Exception:
        out = None
    if not isinstance(out, dict):
        print(f"[Shops] plan unreadable: {str(raw)[:160]!r}")
        return None

    have = {_what(r).lower(): _what(r) for r in rows if _what(r)}
    groups = []
    for g in (out.get("groups") or [])[:MAX_GROUPS]:
        if not isinstance(g, dict):
            continue
        search = str(g.get("search") or "").strip()[:80]
        label = str(g.get("label") or search).strip()[:40]
        its = [have.get(str(i).strip().lower(), str(i).strip())
               for i in (g.get("items") or []) if str(i).strip()]
        if search and its:
            groups.append({"search": search, "label": label, "items": its})
    buying = bool(out.get("buying")) and bool(groups)
    return {"buying": buying, "groups": groups if buying else []}


def plan(user_id: str, list_id: str) -> Dict:
    """{buying, groups:[{search, label, items}]} for one of her lists.

    {buying: false} for a list that is not shopping, an empty list, or a
    list that is not hers. A failed model call is not cached and also
    answers false, so the button simply does not appear this time.
    """
    from memory import lists as L
    lst = L.get(user_id, list_id)
    if not lst:
        return {"buying": False, "groups": []}
    rows = [r for r in L._items_of(lst["id"], include_done=False) if _what(r)]
    if not rows:
        return {"buying": False, "groups": []}

    k = _key(lst, rows)
    hit = _PLANS.get(k)
    if hit and time.time() - hit[0] < PLAN_TTL:
        return hit[1]

    p = _ask_plan(lst, rows, _lang(user_id))
    if p is None:
        return {"buying": False, "groups": []}
    _PLANS[k] = (time.time(), p)
    print(f"[Shops] {user_id} {lst.get('name')!r}: buying={p['buying']} "
          f"groups={[g['label'] for g in p['groups']]}")
    return p


def _nearest(user_id: str, search: str) -> List[Dict]:
    from routes.integrations import get_nearby_places
    try:
        r = get_nearby_places(user_id, search, with_phone=False) or {}
    except Exception as e:
        print(f"[Shops] places failed for {search!r}: {e}")
        return []
    out = []
    for p in (r.get("places") or [])[:SHOPS_PER_GROUP]:
        out.append({
            "name":        p.get("name"),
            "address":     p.get("address"),
            "distance_km": p.get("distance_km"),
            "walk_min":    p.get("walk_min"),
            "open":        p.get("open"),
            "map_url":     p.get("map_url"),
        })
    return out


def where(user_id: str, list_id: str) -> Dict:
    """The plan, with the nearest shops for each group."""
    p = plan(user_id, list_id)
    if not p.get("buying"):
        return {"buying": False, "groups": []}
    groups = [dict(g) for g in p["groups"]]
    with ThreadPoolExecutor(max_workers=min(5, len(groups))) as ex:
        found = list(ex.map(lambda g: _nearest(user_id, g["search"]), groups))
    for g, shops in zip(groups, found):
        g["shops"] = shops
    return {"buying": True, "groups": groups}

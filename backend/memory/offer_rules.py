"""
OFFER RULES AND WHAT SHE CAN DO — standing facts from her own answers.

A "never" is a rule, not a low score. "Bahar ka khana kabhi nahi mangwati"
does not make her like dosa less; it means food is never offered from
outside, while a dish to make at home still is. And a "not on Tuesdays" or
"ekadashi hai" is a rule with a condition, not a dislike.

Abilities are facts, not rules: "phone chalana nahi aata" says how she can
take an offer up, and flips back when she says she has learnt.

Both live in user_profile.life_context, under keys nothing else writes:

    life_context.offer_rules = [
      {"kind": "khana", "way": "outside", "mode": "never", "when": null,
       "said": "bahar ka khana kabhi nahi mangwati", "on": "2026-10-16"},
      {"kind": "khana", "way": null, "mode": "never",
       "when": {"weekday": "Tue"}, "said": "Mangalvar ko nahi", ...}]

    life_context.abilities = {
      "uses_phone": {"value": false, "source": "she_said",
                     "said": "phone chalana nahi aata", "on": "2026-10-16"}}

Ways, per kind of offer:
    khana    outside (a place near her: eat out or order)  | home (cook / recipe)
    sangeet  phone (a link to play)                        | any
    dekhna   phone / tv                                     | any
"""
from datetime import datetime
from typing import Dict, List, Optional

WAYS = {"khana": ("outside", "home")}
ABILITIES = ("uses_phone", "cooks", "orders_herself", "goes_out_alone")
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _db():
    from supabase_store import get_client
    return get_client()


def _life(user_id: str) -> Dict:
    try:
        rows = (_db().table("user_profile").select("life_context")
                .eq("user_id", user_id).limit(1).execute()).data or []
        lc = rows[0].get("life_context") if rows else None
        return lc if isinstance(lc, dict) else {}
    except Exception as e:
        print(f"[Rules] read failed: {e}")
        return {}


def _write_life(user_id: str, lc: Dict) -> bool:
    try:
        _db().table("user_profile").update({"life_context": lc}) \
            .eq("user_id", user_id).execute()
        return True
    except Exception as e:
        print(f"[Rules] write failed: {e}")
        return False


def rules(user_id: str) -> List[Dict]:
    r = _life(user_id).get("offer_rules")
    return [x for x in r if isinstance(x, dict)] if isinstance(r, list) else []


def abilities(user_id: str) -> Dict:
    a = _life(user_id).get("abilities")
    return a if isinstance(a, dict) else {}


def _norm_day(d) -> Optional[str]:
    s = str(d or "").strip()[:3].title()
    return s if s in _DAYS else None


def add_rule(user_id: str, kind: str, way: Optional[str], mode: str = "never",
             when: Optional[Dict] = None, said: str = "",
             from_suggestion: Optional[str] = None) -> Optional[Dict]:
    """Add one rule; the same rule twice is kept once (the newer words)."""
    kind = (kind or "").strip().lower() or None
    way = (way or "").strip().lower() or None
    if way and kind in WAYS and way not in WAYS[kind]:
        way = None
    if not kind and not way:
        return None
    w = None
    if isinstance(when, dict):
        w = {}
        if when.get("weekday"):
            d = _norm_day(when["weekday"])
            if d:
                w["weekday"] = d
        if when.get("fast_day"):
            w["fast_day"] = True
        w = w or None
    rule = {"kind": kind, "way": way, "mode": mode, "when": w,
            "said": (said or "")[:200], "on": datetime.now().date().isoformat()}
    if from_suggestion:
        rule["from_suggestion"] = from_suggestion
    lc = _life(user_id)
    cur = [x for x in (lc.get("offer_rules") or []) if isinstance(x, dict)]
    cur = [x for x in cur if not (x.get("kind") == kind and x.get("way") == way
                                  and x.get("when") == w)]
    cur.append(rule)
    lc["offer_rules"] = cur
    if _write_life(user_id, lc):
        print(f"[Rules] {user_id}: {describe(rule)}")
        return rule
    return None


def set_ability(user_id: str, key: str, value: bool, said: str = "",
                source: str = "she_said") -> bool:
    if key not in ABILITIES:
        return False
    lc = _life(user_id)
    ab = lc.get("abilities") if isinstance(lc.get("abilities"), dict) else {}
    ab[key] = {"value": bool(value), "source": source, "said": (said or "")[:200],
               "on": datetime.now().date().isoformat()}
    lc["abilities"] = ab
    ok = _write_life(user_id, lc)
    if ok:
        print(f"[Rules] {user_id}: {key} = {bool(value)} ({said[:50]!r})")
    return ok


def _applies_now(rule: Dict, moment: Dict) -> bool:
    w = rule.get("when")
    if not w:
        return True
    if w.get("weekday") and w["weekday"] != moment.get("weekday"):
        return False
    if w.get("fast_day") and not moment.get("fast_day"):
        return False
    return True


def blocked(rules_: List[Dict], kind: str, way: Optional[str] = None,
            moment: Optional[Dict] = None) -> Optional[Dict]:
    """The rule that stops this kind (offered this way) right now, or None.

    A rule with no way blocks the whole kind; a rule with a way blocks only
    that way, so "no food from outside" still lets a dish to cook through.
    """
    moment = moment or {}
    kind = (kind or "").lower()
    for r in rules_:
        if r.get("mode") not in ("never", "rest"):
            continue
        if r.get("kind") and r["kind"] != kind:
            continue
        if r.get("way") and r["way"] != (way or ""):
            continue
        if _applies_now(r, moment):
            return r
    return None


def moment_now(user_id: str) -> Dict:
    """The parts of now that rules can depend on: weekday, and whether she
    is keeping a fast today."""
    m = {}
    try:
        from zoneinfo import ZoneInfo
        from memory.declared import get_declared
        tz = ZoneInfo(get_declared(user_id).place.timezone or "Asia/Kolkata")
    except Exception:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Kolkata")
    m["weekday"] = datetime.now(tz).strftime("%a")
    try:
        from memory.offers import _keeping_fast
        m["fast_day"] = bool(_keeping_fast(user_id))
    except Exception:
        m["fast_day"] = False
    return m


def describe(rule: Dict) -> str:
    """A plain sentence, for logs, the picker and a caregiver."""
    kind = {"khana": "food", "sangeet": "music", "dekhna": "films and shows",
            "shauk": "hobbies", "bhakti": "devotional things"}.get(rule.get("kind") or "",
                                                                  rule.get("kind") or "offers")
    way = {"outside": " from outside", "home": " to make at home",
           "phone": " on the phone"}.get(rule.get("way") or "", "")
    w = rule.get("when") or {}
    when = (f" on {w['weekday']}" if w.get("weekday") else "") + \
           (" on fast days" if w.get("fast_day") else "")
    said = f' (she said: "{rule["said"]}")' if rule.get("said") else ""
    return f"Never offer {kind}{way}{when}{said}"

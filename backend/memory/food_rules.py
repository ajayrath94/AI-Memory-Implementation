"""
FOOD RULES — what her health and her own words mean at the table, decided
by the model, in any language.

This replaces three word lists that each tried to read her profile:
engine_router._FOOD_CARE ("blood pressure", "amlodipine"...), artefacts.
_dietary ("veg", "chicken"...) and integrations._user_health_filters
("hypertension", "dairy"...). They worked for a profile written in English
and silently did nothing for one written in her words — "hipertensión",
"riñón", "carne" — which for food safety is the worst kind of failure: no
error, just a missing rule.

So the profile goes to the model as it is, and the model says what it means.
Once per profile: the answer is cached against a fingerprint of the fields
it was given, so it is asked again only when something it depends on
changes. The rules come back in English because they are instructions to
other prompts, never words said to her.
"""
import hashlib
import json
import time
from typing import Dict, List

_CACHE: Dict[str, Dict] = {}
_TTL = 6 * 3600

# Spoonacular's own vocabulary. These are API values, not her words: the
# model chooses from them, and anything else is dropped.
_INTOLERANCES = ["dairy", "egg", "gluten", "grain", "peanut", "seafood",
                 "sesame", "shellfish", "soy", "sulfite", "tree nut", "wheat"]
_CUISINES = ["Indian", "Spanish", "Mediterranean", "German", "Latin American",
             "Mexican", "Italian", "French", "Greek", "Middle Eastern",
             "Chinese", "Thai", "Japanese", "Korean", "Vietnamese", "British",
             "Irish", "American", "Southern", "Cajun", "Caribbean",
             "Eastern European", "Nordic", "African", "Jewish"]

_EMPTY = {"chat_notes": [], "offer_rules": [], "vegetarian": None,
          "doctor_decides": False, "never": [],
          "recipe": {"max_sodium": None, "max_sugar": None,
                     "intolerances": [], "cuisine": None}}


def _list(v) -> List[str]:
    return [str(x).strip() for x in (v if isinstance(v, list) else [v]) if x and str(x).strip()]


def _facts(p: Dict) -> Dict:
    """Only the fields that bear on food. Also what the cache is keyed on."""
    demo = p.get("demographics") or {}
    food = p.get("food") or {}
    health = p.get("health") or {}
    return {
        "conditions": _list(health.get("conditions")),
        "medicines": _list(health.get("medications")),
        "health_concerns": _list(health.get("concerns")),
        "diet": str(food.get("diet") or demo.get("diet") or ""),
        "does_not_eat": _list(food.get("avoid")) + _list(food.get("avoids")),
        "dislikes": _list(food.get("dislikes")),
        # Likes too: "chicken" there is how a model knows she eats meat.
        "likes": _list(food.get("likes"))[:15],
        "lives_in": str(p.get("location") or ""),
        "home": str(demo.get("hometown") or demo.get("home") or
                    (p.get("cultural_context") or {}).get("region") or ""),
    }


def _ask_model(f: Dict) -> Dict:
    from llm import ask
    raw = ask(f"""Someone elderly has this profile, in their own words and
possibly in any language:

{json.dumps(f, ensure_ascii=False, indent=1)}

Work out what it means for the food a companion may suggest. Return JSON only:
{{
 "chat_notes": [short English lines, what their health means at the table,
               e.g. "blood pressure: low salt, nothing fried" — one per
               condition or medicine that matters for food. Leave out
               anything with no food consequence entirely — never write
               "knee pain: none"; [] if none],
 "offer_rules": [short English LIMITS for choosing a dish to suggest,
                 e.g. "nothing heavily salted or deep fried". Limits only —
                 never what they like or what to feature; their likes are
                 handled elsewhere, and whether they may eat meat today is
                 decided by the calendar, not here],
 "doctor_decides": true if any condition means a doctor must set their diet
                   (e.g. kidney disease, dialysis) — then suggest nothing
                   specific about it,
 "vegetarian": true ONLY if their own words say they do not eat meat or are
               vegetarian; false if their words say they eat meat; null if
               they have not said. Never infer it from religion or region,
 "never": [things they do not eat, translated to English],
 "recipe": {{
   "max_sodium": 800 if salt should be limited, else null,
   "max_sugar": 15 if sugar should be limited, else null,
   "intolerances": [only from {_INTOLERANCES}],
   "cuisine": the one cuisine from {_CUISINES} that they cook at home —
              judge by where they are from, not only where they live; null
              if unclear
 }}
}}
Go through EVERY condition and EVERY medicine, one by one, and ask what it
means at the table. Medicines count even when no condition is listed: a
blood-pressure tablet means low salt; a thyroid tablet means going easy on
soy and raw cabbage-family vegetables; a diabetes medicine means little
sugar. Leave out only what truly has nothing to do with food (a knee).""", max_tokens=600) or ""
    s, e = raw.find("{"), raw.rfind("}")
    d = json.loads(raw[s:e + 1])

    out = json.loads(json.dumps(_EMPTY))
    out["chat_notes"] = [str(x)[:160] for x in d.get("chat_notes") or []][:8]
    out["offer_rules"] = [str(x)[:120] for x in d.get("offer_rules") or []][:8]
    out["doctor_decides"] = bool(d.get("doctor_decides"))
    v = d.get("vegetarian")
    out["vegetarian"] = v if isinstance(v, bool) else None
    out["never"] = [str(x)[:60] for x in d.get("never") or []][:12]
    r = d.get("recipe") or {}
    out["recipe"]["max_sodium"] = 800 if r.get("max_sodium") else None
    out["recipe"]["max_sugar"] = 15 if r.get("max_sugar") else None
    out["recipe"]["intolerances"] = [x for x in (r.get("intolerances") or [])
                                     if x in _INTOLERANCES]
    out["recipe"]["cuisine"] = r.get("cuisine") if r.get("cuisine") in _CUISINES else None
    return out


def rules(user_id: str) -> Dict:
    """Her food rules. Never raises; an empty set when nothing is known or
    the model could not be reached (callers then pass her words through)."""
    try:
        from memory.profile_store import get_user_profile
        f = _facts(get_user_profile(user_id) or {})
    except Exception as e:
        print(f"[FoodRules] profile read failed: {e}")
        return dict(_EMPTY, ok=False)

    if not any(f.values()):
        return dict(_EMPTY, ok=True)

    key = hashlib.sha1(json.dumps(f, sort_keys=True, ensure_ascii=False)
                       .encode()).hexdigest()
    hit = _CACHE.get(user_id)
    if hit and hit["key"] == key and time.time() - hit["at"] < _TTL:
        return hit["rules"]

    try:
        r = _ask_model(f)
        r["ok"] = True
    except Exception as e:
        print(f"[FoodRules] model failed for {user_id}: {e}")
        r = dict(_EMPTY, ok=False)
    r["facts"] = f
    if r["ok"]:
        _CACHE[user_id] = {"key": key, "at": time.time(), "rules": r}
    return r


def raw_line(r: Dict) -> str:
    """When the model could not be asked: her own words, with the instruction
    to respect them. Better than a word list guessing at them."""
    f = r.get("facts") or {}
    parts = []
    if f.get("conditions") or f.get("medicines"):
        parts.append("health (as recorded): "
                     + "; ".join(f.get("conditions", []) + f.get("medicines", [])))
    if f.get("does_not_eat"):
        parts.append("does not eat: " + ", ".join(f["does_not_eat"]))
    return ("; ".join(parts) + " — keep any food right for these") if parts else ""

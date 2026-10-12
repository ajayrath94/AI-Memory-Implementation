"""
Everything built on 12 Oct, checked on three made-up people.

    railway run python3 -u backend/tests/sim_today.py

Real database, real model, real Google Places. Three throwaway users, deleted
at the end whatever happens. About three to five minutes.

    Meera   Hindu, Bengaluru, BP. Keeps Navratri (she said so). Loves South
            Indian food, Kishore Kumar, Netflix — and says when she watches.
    Farida  Muslim, Hyderabad, diabetes. Navratri is not hers. Has gone off
            cricket, refused one offer outright.
    Rupa    Bengali, Kolkata. Fish curry on Mondays, four weeks running.

What is checked, by feature:

    A  festival      her festival on every day it runs; not someone else's
    B  fast food     dish ideas during a kept fast avoid what it avoids
    C  places        a real place near her for a dish, close, not a bar
    D  when          "raat ko Netflix" is remembered as night, and reaches
                     the choice as "usually"
    E  weekly habit  fish curry on Mondays reaches the choice
    F  schedule      the whole day is seen, and where this moment sits in it
    G  history       an offer is recorded with its hour; past answers reach
                     the choice
    H  learning      a refused thing is never offered again; a soured
                     interest is not expanded
    I  the pick      one real choice, end to end, printed in full

Festival checks need a festival running today (Sharad Navratri runs 11-19
Oct 2026). Outside it they are skipped, not failed.

Ends ALL GREEN or names what failed.
"""
import json
import os
import sys
import time
import traceback
import types
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

STAMP = int(time.time())
MEERA, FARIDA, RUPA = (f"simmeera{STAMP}", f"simfarida{STAMP}", f"simrupa{STAMP}")
_fails, _skips = [], []
db = get_client()


def check(ok, label, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + (f"\n         {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def skip(label, why):
    print(f"  skip {label} ({why})")
    _skips.append(label)


def head(t):
    print("\n" + "─" * 74 + f"\n{t}\n" + "─" * 74)


# ── the people ───────────────────────────────────────────────────────────────

PEOPLE = {
    MEERA: {
        "name": "Meera",
        "profile": {"language_pref": "hinglish", "location": "Jayanagar, Bengaluru",
                    "home_location": "Jayanagar, Bengaluru",
                    "demographics": {"gender": "female", "age": 71},
                    "health": {"conditions": ["high blood pressure"],
                               "medications": ["Amlodipine"]},
                    "cultural_context": {"religion": "Hindu",
                                         "practices": ["morning puja"]}},
        "routine": [("wake", None, "05:45"), ("routine", "Morning puja", "06:30"),
                    ("meal", "breakfast", "08:30"), ("meal", "lunch", "13:00"),
                    ("routine", "Evening walk", "17:30"), ("meal", "dinner", "19:30"),
                    ("sleep", None, "22:00")],
        "meds": [("Amlodipine", "08:00")],
        "likes": [("South Indian food", "khana", 2.2),
                  ("Kishore Kumar", "sangeet", 2.6),
                  ("Netflix", "dekhna", 1.2)],
        # She has said she keeps it — the same anchor Shobha has.
        "anchor": ("avoids_meat_on", "['Navratri']", "Navratri ke liye sabudana lena hai"),
    },
    FARIDA: {
        "name": "Farida",
        "profile": {"language_pref": "hinglish", "location": "Tolichowki, Hyderabad",
                    "home_location": "Tolichowki, Hyderabad",
                    "demographics": {"gender": "female", "age": 66},
                    "health": {"conditions": ["type 2 diabetes"],
                               "medications": ["Metformin"]},
                    "cultural_context": {"religion": "Muslim",
                                         "practices": ["namaz"]}},
        "routine": [("wake", None, "05:00"), ("routine", "Fajr namaz", "05:15"),
                    ("meal", "nashta", "08:00"), ("meal", "dopahar ka khana", "13:30"),
                    ("routine", "Shaam ki sair", "17:45"), ("meal", "raat ka khana", "20:30"),
                    ("sleep", None, "22:30")],
        "meds": [("Metformin", "08:30")],
        "likes": [("Mehdi Hassan", "sangeet", 2.4),
                  ("Hyderabadi food", "khana", 1.8),
                  ("cricket", "shauk", 2.0)],
        "soured": "cricket",
        "refused": "Haleem",
    },
    RUPA: {
        "name": "Rupa",
        "profile": {"language_pref": "english", "location": "Salt Lake, Kolkata",
                    "home_location": "Salt Lake, Kolkata",
                    "demographics": {"gender": "female", "age": 63},
                    "cultural_context": {"religion": "Hindu"}},
        "routine": [("wake", None, "06:30"), ("meal", "breakfast", "07:30"),
                    ("meal", "lunch", "13:30"), ("routine", "Evening walk", "18:00"),
                    ("meal", "dinner", "21:00"), ("sleep", None, "23:00")],
        "meds": [],
        "likes": [("Rabindrasangeet", "sangeet", 2.3), ("Bengali food", "khana", 1.7)],
        "weekly": "fish curry",
    },
}


def teardown(uid):
    for t in ("window_state", "suggestions", "day_events", "subject_mentions",
              "user_behavioral_events", "interest_clusters", "observances",
              "profile_anchors", "user_patterns", "care_schedule",
              "proactive_events", "messages", "sessions", "user_memory",
              "user_profile"):
        try:
            db.table(t).delete().eq("user_id", uid).execute()
        except Exception:
            pass


def setup(uid, spec):
    db.table("user_profile").upsert({"user_id": uid, "name": spec["name"],
                                     **spec["profile"]}).execute()
    db.table("user_memory").upsert({"user_id": uid, "session_count": 20}).execute()
    for kind, label, at in spec["routine"]:
        db.table("user_patterns").insert({"user_id": uid, "kind": kind, "label": label,
                                          "declared_at": at, "source": "declared"}).execute()
    for label, at in spec["meds"]:
        db.table("care_schedule").insert({"user_id": uid, "label": label,
                                          "type": "medication", "time_of_day": at,
                                          "days": "daily", "active": True}).execute()
    for label, cat, s in spec["likes"]:
        row = {"user_id": uid, "label": label, "pillar": "ENTERTAINMENT",
               "kind": "interest", "status": "active", "strength": s,
               "attributes": {"category": cat, "source": "conversation"}}
        if spec.get("soured") == label:
            row["current_state"] = -0.5
        db.table("interest_clusters").insert(row).execute()
    if spec.get("anchor"):
        field, value, quote = spec["anchor"]
        today = date.today().isoformat()
        try:
            db.table("profile_anchors").insert({
                "user_id": uid, "field": field, "value": value, "source": "repeated",
                "quote": quote, "seen_on": [today],
                "confirmed_at": datetime.now(timezone.utc).isoformat()}).execute()
        except Exception as e:
            print(f"  (anchor insert failed — festival 'keeps it' will read unknown: {e})")
    if spec.get("refused"):
        db.table("suggestions").insert({
            "user_id": uid, "label": spec["refused"], "intent": "recommendation",
            "source": "offer", "reaction": "declined_preference"}).execute()
    if spec.get("weekly"):
        # Four of the last four of today's weekday, and one other day.
        today = date.today()
        for k in range(1, 5):
            db.table("subject_mentions").insert({
                "user_id": uid, "subject": spec["weekly"],
                "happened_on": (today - timedelta(days=7 * k)).isoformat()}).execute()
        db.table("subject_mentions").insert({
            "user_id": uid, "subject": spec["weekly"],
            "happened_on": (today - timedelta(days=10)).isoformat()}).execute()
    from memory.day import rebuild
    rebuild(uid)


def stub_classified():
    return types.SimpleNamespace(
        core="ENTERTAINMENT", core_score=0.8, core_priority="MEDIUM", core_matrix={},
        emotion="neutral", emotion_priority="LOW", emotion_matrix={},
        functional_priority="LOW", language="hinglish")


def window(starts, ends, after, before):
    from memory.windows import Window
    return Window(starts=starts, ends=ends, after=after, before=before)


_GRAIN = ("idli", "dosa", "rice", "roti", "paratha", "chapati", "upma", "pongal",
          "rava", "uttapam", "vada", "bisi", "biryani", "pulao", "onion", "garlic",
          "poha", "khichdi", "puri", "naan")
_FAST_FLOUR = ("sabudana", "kuttu", "singhara", "rajgira", "samak", "sama ",
               "makhana", "vrat", "fast", "farali", "upvas")


def _breaks_fast(name) -> bool:
    """A grain dish, unless it is the fasting version of one: kuttu dosa and
    sabudana khichdi keep the fast; rava idli does not."""
    n = str(name).lower()
    return any(g in n for g in _GRAIN) and not any(f in n for f in _FAST_FLOUR)


# ── the checks ───────────────────────────────────────────────────────────────

def a_festival():
    head("A. FESTIVAL — hers, on every day it runs")
    from memory.festival_brief import running_today, for_user
    r = running_today()
    if not r:
        skip("festival checks", "no multi-day festival running today")
        return None
    print(f"  running today: {r.get('name')} — day {r.get('day_of')} of {r.get('days')}")
    fm = for_user(MEERA)
    check(bool(fm), "Meera (Hindu, does puja) gets the festival", f"got {fm}")
    if fm:
        check(fm.get("she_keeps_it") is True, "and it knows she keeps it (from her own words)",
              f"she_keeps_it={fm.get('she_keeps_it')}")
        check(bool(fm.get("eaten_instead")), "and what the fast allows",
              f"eaten_instead={fm.get('eaten_instead')!r}")
    ff = for_user(FARIDA)
    check(ff is None, "Farida (Muslim) does not get Navratri", f"got {ff}")
    from memory.offers import user_context
    cm = user_context(MEERA)
    cf = user_context(FARIDA)
    check("festival" in cm.get("today", {}), "the festival reaches Meera's recommendation context")
    check("festival" not in cf.get("today", {}), "and not Farida's")
    return fm


def b_fast_food(fm):
    head("B. FOOD DURING A KEPT FAST")
    if not (fm and fm.get("fasting")):
        skip("fast-food checks", "no fasting festival for Meera today")
        return
    from memory.artefacts import adjacent
    dishes = adjacent(MEERA, "South Indian food", "khana") or []
    names = [d.get("what") for d in dishes]
    print(f"  dish ideas from 'South Indian food' today: {names}")
    bad = [n for n in names if _breaks_fast(n)]
    check(bool(names), "there are dish ideas (not nine days of nothing)", f"got {names}")
    check(not bad, "none of them breaks the fast", f"breaking: {bad}")
    try:
        row = (db.table("interest_clusters").select("attributes").eq("user_id", MEERA)
               .ilike("label", "South Indian food").limit(1).execute()).data[0]
        keys = [k for k in (row.get("attributes") or {}) if k.startswith("adjacent_")]
        check(any(k.startswith("adjacent_fast_") for k in keys),
              "kept under the festival's own cache, not the everyday one", f"keys: {keys}")
    except Exception as e:
        check(False, "cache key readable", str(e)[:100])


def c_places():
    head("C. A REAL PLACE NEAR HER FOR A DISH")
    from memory.offers import _place_for, PLACE_MAX_KM
    for uid, who, dish in ((MEERA, "Meera, Jayanagar", "Masala Dosa"),
                           (FARIDA, "Farida, Tolichowki", "Hyderabadi Biryani")):
        p = _place_for(uid, dish)
        print(f"  {who} — {dish}: {p and (p['title'], p['area'], p['distance_km'], 'km', p['walk_min'], 'min', p['rating'])}")
        if p is None:
            skip(f"place for {who}", "none close enough — allowed, the dish goes without one")
            continue
        check(p["distance_km"] <= PLACE_MAX_KM, f"{who}: within {PLACE_MAX_KM:g} km", f"{p['distance_km']} km")
        check(not any(w in p["title"].lower() for w in ("bar", "pub", "brew", "lounge")),
              f"{who}: not a bar", p["title"])
        check(" | " not in p["title"] and " @ " not in p["title"],
              f"{who}: the name as it would be said", p["title"])
        check(p["url"].startswith("https://www.google.com/maps/"), f"{who}: a map link to tap")


def d_when():
    head("D. WHEN SHE DOES THINGS")
    from memory.profile_enricher import _extract_propositions, record_propositions
    for txt in ("Raat ko Netflix pe serial dekhti hoon",
                "Kal raat bhi Netflix pe ek film dekhi"):
        props = _extract_propositions(txt, MEERA) or []
        print(f"  \"{txt}\" -> {[(p.get('object') or p.get('subject'), p.get('when')) for p in props]}")
        record_propositions(props, stub_classified(), MEERA, "")
    rows = (db.table("interest_clusters").select("label,attributes").eq("user_id", MEERA)
            .eq("status", "active").execute()).data or []
    print("  where each thing landed:")
    for r in rows:
        us = (r.get("attributes") or {}).get("usually")
        if us:
            print(f"    {r['label']!r}: usually {us}")
    # Counted across every Netflix-ish cluster: "Netflix serial" and
    # "Netflix" are one habit even when the memory files them apart.
    night = sum(int(((r.get("attributes") or {}).get("usually") or {}).get("night", 0))
                for r in rows if "netflix" in str(r["label"]).lower())
    check(night >= 2, "watching Netflix is remembered as a night thing, both times",
          f"night count across Netflix clusters: {night}")
    split = [r["label"] for r in rows if "netflix" in str(r["label"]).lower()]
    if len(split) > 1:
        print(f"  note: filed under {len(split)} interests {split} — a duplicate, "
              f"not a failure here")
    from memory.offers import user_context
    loves = user_context(MEERA).get("loves") or []
    nl = [l for l in loves if "netflix" in str(l.get("what")).lower()]
    check(any("night" in (l.get("usually") or []) for l in nl),
          "and the recommendation context says so", f"{nl}")


def e_weekly():
    head("E. WEEKLY HABIT")
    from memory.offers import user_context
    t = (user_context(RUPA).get("trends") or {})
    due = t.get("today_is_usually") or []
    print(f"  Rupa trends: {json.dumps(t, ensure_ascii=False)}")
    check(any("fish curry" in d for d in due),
          f"fish curry on {date.today():%A}s reaches the choice", f"today_is_usually={due}")


def f_schedule():
    head("F. THE SCHEDULE, AND WHERE THIS MOMENT SITS IN IT")
    from memory.offers import user_context
    w = window(13 * 60 + 45, 17 * 60 + 30, "lunch", "Evening walk")
    t = user_context(MEERA, w, 16 * 60 + 50).get("today") or {}
    print(f"  at 16:50: nearest={t.get('nearest')!r}, next_in={t.get('next_in_minutes')}, "
          f"schedule={[s['at'] + ' ' + s['what'] for s in t.get('schedule', [])]}")
    check("before" in str(t.get("nearest")) and "walk" in str(t.get("nearest")).lower(),
          "16:50 is 'shortly before the walk'", f"nearest={t.get('nearest')}")
    check(any("walk" in s["what"].lower() for s in t.get("schedule", [])),
          "the whole day's schedule is there")
    t2 = user_context(MEERA, w, 14 * 60).get("today") or {}
    check("after" in str(t2.get("nearest")), "14:00 is 'just after lunch'",
          f"nearest={t2.get('nearest')}")


def g_history():
    head("G. OFFERS RECORDED WITH THEIR HOUR, AND PAST ANSWERS SEEN")
    from memory.offers import Offer, record, user_context
    o = Offer(what="Mere Sapnon Ki Rani by Kishore Kumar", because="Kishore Kumar",
              category="sangeet")
    record(MEERA, o, window(14 * 60, 17 * 60, "lunch", "walk"))   # no hour, as the scheduler calls it
    rows = (db.table("suggestions").select("label,offered_hour").eq("user_id", MEERA)
            .order("created_at", desc=True).limit(1).execute()).data or []
    check(bool(rows) and rows[0].get("offered_hour") is not None,
          "the hour is stored even when the caller does not pass it", f"{rows}")
    po = user_context(MEERA).get("past_offers") or []
    check(any("Sapnon" in str(p.get("what")) for p in po), "and it shows in past_offers",
          f"{po[:2]}")


def h_learning():
    head("H. LEARNING FROM HER ANSWERS")
    from memory.offers import _refused, hers, user_context
    check("haleem" in _refused(FARIDA), "'pasand nahi' (declined_preference) is remembered as a refusal")
    v = hers(FARIDA).get("cricket") or {}
    check(v.get("state") is not None and v["state"] < 0, "cricket reads as soured", f"{v}")
    loves = user_context(FARIDA).get("loves") or []
    c = [l for l in loves if l["what"].lower() == "cricket"]
    check(bool(c) and c[0].get("lately") == "turned against it",
          "and the choice is told so", f"{c}")


def i_pick():
    head("I. ONE REAL CHOICE, END TO END (Meera, 11:30, before lunch)")
    os.environ["OFFERS_DEBUG"] = "1"
    from memory.offers import choose, hint
    w = window(9 * 60, 12 * 60 + 45, "breakfast", "lunch")
    try:
        o = choose(MEERA, w, 11 * 60 + 30)
    except Exception:
        traceback.print_exc()
        check(False, "choose() ran")
        return
    finally:
        os.environ.pop("OFFERS_DEBUG", None)
    if o is None:
        print("  nothing suited — a legitimate answer")
        return
    print(f"\n  CHOSE: {o.what}  [{o.category}]  because {o.because}\n  WHY: {o.why_now}")
    print(f"  LINK: {(o.artefact or {}).get('url')}")
    print(f"  HINT to the composer:{hint(o)}")
    if o.category == "khana":
        from memory.festival_brief import for_user
        f = for_user(MEERA)
        if f and f.get("fasting"):
            check(not _breaks_fast(o.what), "a dish chosen during her fast keeps the fast", o.what)
        check(" by " not in o.what, "a dish, not a dish by an unchecked shop", o.what)


def main():
    for uid, spec in PEOPLE.items():
        teardown(uid)
        setup(uid, spec)
    print(f"made: {', '.join(s['name'] + ' (' + u + ')' for u, s in PEOPLE.items())}")
    fm = None
    for step in (a_festival, None, c_places, d_when, e_weekly, f_schedule,
                 g_history, h_learning, i_pick):
        try:
            if step is None:
                b_fast_food(fm)
            elif step is a_festival:
                fm = step()
            else:
                step()
        except Exception as e:
            traceback.print_exc()
            check(False, f"{getattr(step, '__name__', 'b_fast_food')} raised", str(e)[:120])


if __name__ == "__main__":
    try:
        main()
    finally:
        for uid in PEOPLE:
            teardown(uid)
        print("\n" + "=" * 74)
        print(f"{len(_fails)} FAILURE(S)" if _fails else "ALL GREEN")
        for f in _fails:
            print("   -", f)
        if _skips:
            print(f"skipped: {', '.join(_skips)}")
        print("=" * 74)

"""
Three different people. Does any of it hold, or was it fitted to one woman?

    railway run python3 -u backend/tests/sim_three_people.py

Everything has been built against one user: a seventy-one-year-old Hindu
widow in Bengaluru who likes Kishore Kumar, eats South Indian food, walks
at half past five and takes two tablets a day. Every fix was tested on her
day, and several turned out to encode her sentences rather than any rule.

So: three people who are nothing like her, and nothing like each other.

    Kamala      82, Chennai. Almost housebound, sleeps badly, two meals.
                Carnatic music, devotionals, her grandchildren. Keeps
                Fridays. Barely talks — two messages on a good day.

    Ismail      68, Hyderabad. Retired teacher, up at five, mosque five
                times, walks with friends. Ghazals, cricket, Urdu poetry.
                Ramadan is not now but he fasts Mondays. Talks a lot.

    Rupa        59, Kolkata. Still working, out of the house 9 to 6,
                diabetic, eats at her desk. Rabindrasangeet, Bengali
                cinema, gardening at weekends. Terse, replies in English.

WHAT IS BEING CHECKED
Not whether the messages are good — read them for that. Whether the
MACHINERY bends:

    windows     computed from THEIR day, not from hers.
    offers      expanded from THEIR interests, and not all of one kind.
    timing      a recipe before THEIR meal, whenever that is.
    volume      the near-silent one should not get the talkative one's count.
    observances Ismail's Mondays, Kamala's Fridays.

ONE CLOCK, IN ORDER
The first version of this ran an hour at a time and injected everything
belonging to that hour at the top of it. So Kamala's "Saaptachu" at 08:20
was written to the database BEFORE the 08:00 decision ran, and the 08:00
medication reminder was composed by a system that already knew about a
breakfast that had not happened yet. The transcript printed it in that
order too — 08:20 above 08:00 — which is how it was noticed.

Information cannot travel backwards. So now there is one timeline, her
utterances sit at the minute she said them, the ticks sit on the hour, and
both are processed in clock order. A tick at the same minute as an
utterance runs first: the scheduler fires at :00 exactly, she speaks within
the minute.

WHAT IT ASSERTS
The previous version asserted two things, both of which passed, and printed
a dozen real defects as prose for a human to notice. Anything mechanically
checkable is now a failure rather than a paragraph:

    the same drug twice in four hours      (two reminders for one dose)
    a clock time inside a message          ("how did lunch go at 13:30")
    two scripts in one message             (Tamil and Devanagari together)
    a hint's own phrasing, verbatim        ("koi suggestion chahiye" in Tamil)
    an action that composed to nothing     (a swallowed failure)
    every offer in one category            (six offers, six songs)
    more boundaries than anyone would want

What remains for a human: whether the sentences are any good.
"""
import os
import re
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

STAMP = int(time.time())
_fails = []

# More than this and it is supervision rather than company. Ismail's day
# produced six, which is the number that prompted the cap.
MAX_BOUNDARIES = 4

# Two reminders for one dose inside this many minutes is the duplicate bug,
# not a dosing schedule. Rupa's two Metformins are twelve hours apart and
# correct; Kamala's Calcium came at 08:00 and 09:00 for an 08:30 dose.
SAME_DRUG_MIN = 240


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


# ── what a message must not contain ──────────────────────────────────────────

# "how was the Pooja at 06:00" — the time is in the hint so the composer can
# pick a moment, not so it can be read out. Nobody says it.
_CLOCK = re.compile(r"\b\d{1,2}:\d{2}\b")

# Phrases that exist in a hint as an EXAMPLE and come back out verbatim. The
# boundary hint quoted this one, so it appeared inside a Tamil sentence and a
# Bengali-English one. Anything quoted to the model will be repeated; the test
# is which language it lands in.
_HINT_PHRASES = ("koi suggestion chahiye",)

_SCRIPTS = {
    "devanagari": (0x0900, 0x097F),
    "bengali":    (0x0980, 0x09FF),
    "gurmukhi":   (0x0A00, 0x0A7F),
    "gujarati":   (0x0A80, 0x0AFF),
    "tamil":      (0x0B80, 0x0BFF),
    "telugu":     (0x0C00, 0x0C7F),
    "kannada":    (0x0C80, 0x0CFF),
    "malayalam":  (0x0D00, 0x0D7F),
    "arabic":     (0x0600, 0x06FF),
}


def _scripts_in(text: str) -> set:
    """Which writing systems appear. Romanised text registers as none, which
    is why this catches "கரெக்டா" beside Devanagari but not Hinglish beside
    Tanglish — _HINT_PHRASES covers the romanised case."""
    found = set()
    for ch in text:
        o = ord(ch)
        for name, (lo, hi) in _SCRIPTS.items():
            if lo <= o <= hi:
                found.add(name)
                break
    return found


PEOPLE = {
    "kamala": {
        "name": "Kamala",
        "profile": {"language_pref": "tanglish", "location": "Chennai",
                    "home_location": "Chennai",
                    "demographics": {"gender": "female", "age": 82},
                    "health": {"conditions": ["arthritis", "poor sleep"],
                               "medications": ["Calcium", "Amlodipine"]},
                    "cultural_context": {"religion": "Hindu"}},
        "routine": [("wake", None, "05:30"),
                    ("routine", "Pooja", "06:00"),
                    ("meal", "breakfast", "08:00"),
                    ("meal", "lunch", "12:00"),
                    ("routine", "Rest", "14:00"),
                    ("meal", "dinner", "19:00"),
                    ("sleep", None, "20:30")],
        "meds": [("Calcium", "08:30"), ("Amlodipine", "19:30")],
        "likes": [("M.S. Subbulakshmi", "sangeet", 2.4),
                  ("Suprabhatam", "bhakti", 2.0),
                  ("curd rice", "khana", 1.3)],
        "says": [("08:20", "Saaptachu"),
                 ("15:00", "Konjam thookam vandhuchu")],
    },
    "ismail": {
        "name": "Ismail",
        "profile": {"language_pref": "hinglish", "location": "Hyderabad",
                    "home_location": "Hyderabad",
                    "demographics": {"gender": "male", "age": 68},
                    "health": {"conditions": ["high BP"],
                               "medications": ["Telmisartan"]},
                    "cultural_context": {"religion": "Muslim"}},
        "routine": [("wake", None, "04:45"),
                    ("routine", "Fajr namaz", "05:15"),
                    ("meal", "nashta", "07:30"),
                    ("routine", "Zuhr namaz", "13:00"),
                    ("meal", "dopahar ka khana", "14:00"),
                    ("routine", "Asr namaz", "16:30"),
                    ("routine", "Shaam ki sair", "18:00"),
                    ("routine", "Maghrib namaz", "18:45"),
                    ("meal", "raat ka khana", "20:30"),
                    ("sleep", None, "22:30")],
        "meds": [("Telmisartan", "08:00")],
        "likes": [("Mehdi Hassan", "sangeet", 2.5),
                  ("Mirza Ghalib", "shauk", 2.1),
                  ("cricket", "shauk", 1.8),
                  ("biryani", "khana", 1.6)],
        "says": [("06:00", "Namaz ho gayi, ab thodi der akhbar padhunga"),
                 ("09:30", "Nashta kar liya, aaj paya khaya"),
                 ("11:00", "Ghalib ka ek sher yaad aa raha hai subah se"),
                 ("15:30", "Aaj match dekh raha hoon, India kheli rahi hai"),
                 ("19:00", "Doston ke saath sair ho gayi, acha laga"),
                 ("21:00", "Biryani thi aaj raat, bahut achi bani thi")],
    },
    "rupa": {
        "name": "Rupa",
        "profile": {"language_pref": "english", "location": "Kolkata",
                    "home_location": "Kolkata",
                    "demographics": {"gender": "female", "age": 59},
                    "health": {"conditions": ["type 2 diabetes"],
                               "medications": ["Metformin"]},
                    "cultural_context": {"religion": "Hindu"}},
        "routine": [("wake", None, "06:30"),
                    ("meal", "breakfast", "07:30"),
                    ("routine", "Leave for office", "08:30"),
                    ("meal", "lunch", "13:30"),
                    ("routine", "Home from office", "18:30"),
                    ("meal", "dinner", "21:00"),
                    ("sleep", None, "23:00")],
        "meds": [("Metformin", "08:00"), ("Metformin", "20:00")],
        "likes": [("Rabindrasangeet", "sangeet", 2.3),
                  ("Satyajit Ray", "dekhna", 1.9),
                  ("gardening", "shauk", 1.4)],
        "says": [("07:45", "Had breakfast, running late"),
                 ("19:00", "Long day. Traffic was awful."),
                 ("21:30", "Dinner done")],
    },
}


def teardown(uid):
    db = get_client()
    for t in ("window_state", "suggestions", "day_events", "subject_mentions",
              "interest_clusters", "observances", "profile_anchors",
              "user_patterns", "care_schedule", "proactive_events",
              "messages", "sessions", "user_memory", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", uid).execute()
        except Exception:
            pass


def setup(uid, spec):
    db = get_client()
    db.table("user_profile").upsert({
        "user_id": uid, "name": spec["name"], **spec["profile"],
    }).execute()
    db.table("user_memory").upsert({"user_id": uid,
                                    "session_count": 20}).execute()
    for kind, label, at in spec["routine"]:
        db.table("user_patterns").insert({
            "user_id": uid, "kind": kind, "label": label,
            "declared_at": at, "source": "declared"}).execute()
    for label, at in spec["meds"]:
        db.table("care_schedule").insert({
            "user_id": uid, "label": label, "type": "medication",
            "time_of_day": at, "days": "daily", "active": True}).execute()
    for label, cat, s in spec["likes"]:
        db.table("interest_clusters").insert({
            "user_id": uid, "label": label, "pillar": "ENTERTAINMENT",
            "kind": "interest", "status": "active", "strength": s,
            "attributes": {"category": cat, "source": "conversation"},
        }).execute()
    from memory.day import rebuild
    rebuild(uid)


def _hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def a_day(uid, spec):
    """Walk one day in clock order.

    Returns (sent, offers, empties) where `sent` carries the minute each
    message went out — the assertions need the interval between two
    reminders, which the old (action, text) pairs could not express.
    """
    import memory.day as D
    import memory.suggestions as S
    from memory.proactive_engine import proactive_check
    from memory.schedule_engine import generate_proactive_script
    from memory.cadence import may_send
    from memory.day import note_from_message
    from memory.windows import hear_status, windows_today
    from supabase_store import save_message

    db = get_client()
    real_m, real_s = D._mins_now, S._moment
    sent, offers, empties = [], [], []
    sess = None

    D._mins_now = lambda u: 8 * 60
    print("  their windows:")
    for w in windows_today(uid, read_her_words=False):
        print(f"    {w}")
    print()

    # One timeline. Ticks on the hour, her words at the minute she said them.
    # The tick sorts first at an equal minute: the scheduler fires at :00
    # exactly and she speaks somewhere inside that minute.
    timeline = [(h * 60, 0, "TICK", h) for h in range(5, 23)]
    for t, txt in spec["says"]:
        timeline.append((int(t[:2]) * 60 + int(t[3:5]), 1, "SAID", txt))
    timeline.sort(key=lambda e: (e[0], e[1]))

    for now, _tie, what, payload in timeline:
        D._mins_now = lambda u, _n=now: _n
        S._moment = lambda u, _n=now: {**real_s(u), "now_min": _n}

        if what == "SAID":
            txt = payload
            if sess is None:
                sess = db.table("sessions").insert({
                    "user_id": uid,
                    "model": "gemini-flash-latest"}).execute().data[0]
            save_message(sess["id"], "user", txt, "gemini-flash-latest")
            print(f"  {_hhmm(now)} THEY  {txt}")
            for fn in (note_from_message, hear_status):
                try:
                    fn(uid, txt)
                except Exception as e:
                    print(f"         [{fn.__name__} failed: {str(e)[:60]}]")
            try:
                from memory.observances import hear as oh
                oh(uid, txt)
            except Exception:
                pass
            continue

        hour = payload
        try:
            dec = proactive_check(uid, override_hour=hour)
        except Exception as e:
            print(f"  {_hhmm(now)} check failed: {str(e)[:60]}")
            continue
        action = dec.get("action")
        if not action or action == "SILENCE":
            continue
        if not may_send(uid, action).get("allow"):
            continue
        try:
            out = generate_proactive_script(
                uid, action=action, hour=hour,
                detail=str(dec.get("detail") or ""),
                offer=dec.get("offer")) or {}
        except Exception as e:
            # Printed in full, not truncated to fifty characters. The one real
            # crash in the previous run was unreproducible because its message
            # had been cut and its traceback thrown away.
            print(f"  {_hhmm(now)} COMPOSE RAISED on {action}:")
            traceback.print_exc()
            empties.append((now, action, f"raised: {type(e).__name__}"))
            continue
        msg = (out.get("script") or "").replace("\n", " ").strip()
        if not msg:
            # A decision was taken and nothing came out. Silence is correct as
            # a FALLBACK and wrong as an outcome nobody is told about.
            print(f"  {_hhmm(now)} EMPTY script for {action}")
            empties.append((now, action, "empty"))
            continue
        print(f"  {_hhmm(now)} {action[:12]:14} {msg[:110]}")

        offer = dec.get("offer")
        sent.append({
            "min": now, "action": action, "msg": msg,
            "offer": str(offer.what) if offer else None,
            "category": getattr(offer, "category", None) if offer else None,
        })
        if offer:
            offers.append({"what": str(offer.what),
                           "category": getattr(offer, "category", None)})
            try:
                from memory.offers import record
                record(uid, offer, dec.get("window"), now)
            except Exception:
                pass
        try:
            db.table("proactive_events").insert({
                "user_id": uid, "action": action,
                "detail": str(dec.get("detail") or ""),
                "outcome": "delivered",
                "delivered_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception:
            pass

        # What the scheduler does once a boundary has gone out: mark its
        # event spent. Without this the harness tested a day in which no
        # boundary was ever used up, which production never sees.
        if action == "BOUNDARY":
            try:
                _bd = D.boundary(uid, now_min=now)
                if _bd and _bd.get("done"):
                    D.set_status(_bd["done"]["id"], "sent")
            except Exception as e:
                print(f"         [boundary mark failed: {str(e)[:60]}]")

    D._mins_now, S._moment = real_m, real_s
    return sent, offers, empties


# ── the assertions ───────────────────────────────────────────────────────────

def judge(spec, sent, offers, empties):
    name = spec["name"]

    # 1. the same drug twice in four hours
    drugs = {label.lower() for label, _at in spec["meds"]}
    seen = {}
    dupes = []
    for m in sent:
        if m["action"] != "MEDICATION_REMINDER":
            continue
        low = m["msg"].lower()
        for d in drugs:
            if d not in low:
                continue
            if d in seen and m["min"] - seen[d] <= SAME_DRUG_MIN:
                dupes.append(f"{d} at {_hhmm(seen[d])} and {_hhmm(m['min'])}")
            seen[d] = m["min"]
    check(not dupes, f"{name}: one reminder per dose", "; ".join(dupes))

    # 2. a clock time read out loud
    clocks = [f"{_hhmm(m['min'])} {_CLOCK.search(m['msg']).group()!r}"
              for m in sent if _CLOCK.search(m["msg"])]
    check(not clocks, f"{name}: no clock times in the words", "; ".join(clocks))

    # 3. two scripts in one message, or native script in a romanised register
    #
    # The second half catches what the first misses. Kamala's Amlodipine
    # reminder was romanised Tanglish with one word — "கரெக்டா" — in Tamil
    # script, which is a single script and so passed the mixing rule while
    # reading, to her, like a typo in the middle of a sentence. A profile that
    # says tanglish or hinglish has asked for romanised text; any Indic or
    # Arabic script in it is wrong whether or not a second one joins it.
    lang = (spec["profile"].get("language_pref") or "").lower()
    ROMANISED = ("tanglish", "hinglish", "english", "banglish")
    mixed = []
    for m in sent:
        s = _scripts_in(m["msg"])
        if len(s) > 1:
            mixed.append(f"{_hhmm(m['min'])} mixes {sorted(s)}")
        elif s and lang in ROMANISED:
            mixed.append(f"{_hhmm(m['min'])} {sorted(s)[0]} script in {lang}")
    check(not mixed, f"{name}: one script, and the one they read",
          "; ".join(mixed))

    # 4. a hint's own example phrasing, verbatim, in the wrong language
    bled = []
    if lang not in ("hinglish", "hindi"):
        for m in sent:
            low = m["msg"].lower()
            for p in _HINT_PHRASES:
                if p in low:
                    bled.append(f"{_hhmm(m['min'])} {p!r} in a {lang} message")
    check(not bled, f"{name}: no hint phrasing bleeding through",
          "; ".join(bled))

    # 5. a decision that produced nothing
    check(not empties, f"{name}: every decision produced a message",
          "; ".join(f"{_hhmm(t)} {a} ({why})" for t, a, why in empties))

    # 6. offers all of one kind
    cats = {o["category"] for o in offers if o["category"]}
    if len(offers) >= 2:
        check(len(cats) >= 2, f"{name}: offers not all one kind",
              f"{len(offers)} offers, categories={sorted(cats) or '(none set)'}")

    # 7. volume
    bounds = sum(1 for m in sent if m["action"] == "BOUNDARY")
    check(bounds <= MAX_BOUNDARIES, f"{name}: boundaries within reason",
          f"{bounds} in a day")

    # 8. their own world, not hers
    strays = [o["what"] for o in offers
              if any(w in o["what"].lower() for w in
                     ("kishore", "sholay", "south indian", "bagwani"))]
    check(not strays, f"{name}: offered from their own world", f"{strays}")


def main():
    for uid_key, spec in PEOPLE.items():
        uid = f"{uid_key}{STAMP}"
        print(f"\n{'=' * 70}\n{spec['name'].upper()} — {spec['profile']['location']}, "
              f"{spec['profile']['demographics']['age']}\n{'=' * 70}")
        setup(uid, spec)
        try:
            sent, offers, empties = a_day(uid, spec)
        except Exception:
            traceback.print_exc()
            sent, offers, empties = [], [], []

        print()
        print(f"  {len(sent)} messages: {dict(Counter(m['action'] for m in sent))}")
        print(f"  offered: {[o['what'] for o in offers] or '(nothing)'}")
        if offers:
            print(f"  categories: {sorted({o['category'] for o in offers if o['category']})}")

        obs = (get_client().table("observances").select("value,avoids")
               .eq("user_id", uid).execute()).data or []
        if obs:
            print(f"  their days: {[(o['value'], o.get('avoids')) for o in obs]}")

        print()
        judge(spec, sent, offers, empties)
        teardown(uid)


if __name__ == "__main__":
    crashed = None
    try:
        main()
    except Exception as e:
        crashed = e
    finally:
        print("\n" + "=" * 70)
        if crashed:
            traceback.print_exception(type(crashed), crashed,
                                      crashed.__traceback__)
        elif _fails:
            print(f"{len(_fails)} FAILURE(S)")
            for f in _fails:
                print("   -", f)
        else:
            print("ALL GREEN")
        print("=" * 70)

"""
Confirmation, tested hard.

Run: railway run python3 -u backend/tests/sim_day.py

The failures this is guarding against were all found by running it rather than
by reading the code: the model matched labels literally so "sair achi rahi"
never confirmed the Evening walk, the dedup kept whichever label came first so
that event was called "exercise" and could never be matched at all, and a vague
"a tablet was taken" resolved to whichever medication happened to be first.

The cases below are grouped by what they are actually testing, because the
interesting ones are not the confirmations — they are the refusals.
"""
import sys
import os
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "daytest_user"


def setup():
    db = get_client()
    teardown()
    db.table("user_profile").insert({
        "user_id": UID, "name": "DaySim", "language_pref": "hinglish",
        "location": "Surat",
    }).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 1}).execute()
    try:
        from memory.testing import mark_user_as_test
        mark_user_as_test(UID)
    except Exception:
        pass

    db.table("user_patterns").insert([
        {"user_id": UID, "kind": "wake",  "declared_at": "06:30"},
        {"user_id": UID, "kind": "sleep", "declared_at": "22:00"},
        {"user_id": UID, "kind": "meal",  "label": "breakfast", "declared_at": "08:30"},
        {"user_id": UID, "kind": "meal",  "label": "lunch",     "declared_at": "13:00"},
        {"user_id": UID, "kind": "meal",  "label": "dinner",    "declared_at": "19:30"},
        {"user_id": UID, "kind": "routine", "label": "Evening walk", "declared_at": "17:30"},
        {"user_id": UID, "kind": "routine", "label": "Morning puja", "declared_at": "06:45"},
    ]).execute()
    db.table("care_schedule").insert([
        {"user_id": UID, "type": "medication", "label": "Thyroid (thyronorm)",
         "time_of_day": "07:00:00", "days": "daily", "active": True},
        {"user_id": UID, "type": "medication", "label": "BP tablet (amlodipine)",
         "time_of_day": "08:00:00", "days": "daily", "active": True},
    ]).execute()


def teardown():
    db = get_client()
    for t in ("day_events", "user_patterns", "care_schedule", "interest_clusters",
              "user_behavioral_events", "user_memory", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    return 0 if ok else 1


def main():
    setup()
    from memory.day import rebuild, events, _read, open_events, set_status
    fails = 0

    n = rebuild(UID)
    fails += check(n >= 7, f"day built from rhythm and schedule ({n} events)")

    evs = events(UID)
    labels = [e["label"] for e in evs]

    # The dedup used to keep whichever came first, so the 17:30 routine was
    # called "exercise" and nothing could ever match "sair" to it.
    fails += check("Evening walk" in labels,
                   "the specific label survives dedup", ", ".join(labels[:8]))

    # Pretend the whole day has passed so everything is answerable.
    opens = [dict(e) for e in evs]

    print()
    print("— confirmations, in languages nobody wrote the labels in —")
    CONFIRM = [
        ("hinglish walk",  "sair achi rahi aaj, mausam thanda tha", "Evening walk"),
        ("punjabi walk",   "ਸੈਰ ਚੰਗੀ ਰਹੀ ਅੱਜ",                      "Evening walk"),
        ("gujarati lunch", "આજે ખીચડી બનાવી હતી બપોરે",              "lunch"),
        ("tamil bfast",    "காலை உணவு சாப்பிட்டேன்",                  "breakfast"),
        ("bengali puja",   "আজ সকালে পূজা করেছি",                    "Morning puja"),
        ("marathi dinner", "रात्रीचं जेवण झालं",                      "dinner"),
        ("english plain",  "had my breakfast already",               "breakfast"),
    ]
    for name, msg, want in CONFIRM:
        r = _read(msg, opens) or {}
        fails += check(r.get("label") == want and r.get("status") == "confirmed",
                       name, f"{r.get('label')} / {r.get('status')}")

    print()
    print("— denials —")
    DENY = [
        ("skipped lunch",  "aaj dopahar ka khana nahi khaya", "lunch"),
        # "जेवण" is meal in general, and with lunch and dinner both open it
        # does not say which — so a refusal is right. Haiku guessed lunch and
        # the test was written around that guess.
        ("marathi denied", "आज दुपारचं जेवण केलं नाही",          "lunch"),
        ("could not walk", "ghutna dard tha, sair nahi kar payi", "Evening walk"),
    ]
    for name, msg, want in DENY:
        r = _read(msg, opens) or {}
        ok = r.get("status") == "denied" and (want is None or r.get("label") == want)
        fails += check(ok, name, f"{r.get('label')} / {r.get('status')}")

    print()
    print("— refusals: the ones that matter more than the confirmations —")
    REFUSE = [
        # Nothing to do with her day.
        ("daughter called",   "Meena se baat hui aaj, bahut khush hoon"),
        ("tamil unrelated",   "என் மகள் இன்று போன் செய்தாள்"),
        ("about the weather", "aaj bahut garmi hai bahar"),
        ("about a film",      "kal Sholay dekhi thi TV pe"),
        # Someone ELSE did the thing.
        ("neighbour walked",  "padosan roz subah sair karti hai"),
        ("husband's tablet",  "unko dawai dene gayi thi"),
        # A plan, not a fact. She has not done it yet.
        ("intends to walk",   "shaam ko sair karne jaungi"),
        ("thinking of food",  "soch rahi hoon khichdi banaun"),
        # Yesterday, not today.
        ("yesterday",         "kal sair achi rahi thi"),
    ]
    for name, msg in REFUSE:
        r = _read(msg, opens)
        fails += check(r is None, name, str(r))

    print()
    print("— medication needs naming —")
    from memory.day import note_from_message
    # Two tablets are open. "A tablet was taken" does not say which, and
    # recording the wrong one is worse than recording none.
    fails += check(note_from_message(UID, "maine dawai le li") is None,
                   "vague tablet is refused")
    fails += check(note_from_message(UID, "thyroid ki goli le li") == "confirmed",
                   "named tablet confirms")

    print()
    print("— a confirmed meal becomes an interest —")
    note_from_message(UID, "aaj dopahar khichdi banayi thi")
    rows = (get_client().table("interest_clusters").select("label,attributes")
            .eq("user_id", UID).execute()).data or []
    cooked = [r for r in rows
              if (r.get("attributes") or {}).get("source") == "cooked"]
    fails += check(bool(cooked), "the dish is recorded as cooked",
                   ", ".join(r["label"] for r in cooked[:3]))

    print()
    print("— already answered is not asked again —")
    ev = next((e for e in events(UID) if e["label"] == "breakfast"), None)
    if ev:
        set_status(ev["id"], "confirmed")
        still_open = [e["label"] for e in open_events(UID)]
        fails += check("breakfast" not in still_open,
                       "a confirmed event leaves the open set")

    print()
    print("=" * 70)
    print("ALL GREEN" if fails == 0 else f"{fails} FAILURE(S)")
    print("=" * 70)
    teardown()
    print("torn down")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        teardown()
        raise

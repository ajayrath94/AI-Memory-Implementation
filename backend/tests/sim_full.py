"""
Six weeks, through everything.

    railway run python3 -u backend/tests/sim_full.py
    railway run python3 -u backend/tests/sim_full.py --keep

Every piece has been tested on its own. This runs one woman's six weeks
through the whole pipeline and asks whether what it ends up knowing is
recognisably her.

WHAT IT EXERCISES

    topics          what she talked about, and how she felt about each
    mentions        the dates, which outlive the days they were on
    clusters        what she likes, built from conversation
    events          what happened, with the day it happened
    the thread      cache, the day's note, and compression by neglect
    promotion       a habit at three distinct days; an operation at one

THE SHAPE OF THE SIX WEEKS

    khichdi         cooked five times, spread out — a habit, should promote
    lemon rice      cooked twice — should NOT promote, it is two lunches
    Kishore Kumar   mentioned often — already a cluster, should not re-promote
    her knee        worsens across the weeks, then a doctor and an operation
    Arjun           steady through, then a visit

WHAT WOULD BE A FAILURE
Promoting lemon rice. Missing the operation. Losing khichdi's early dates when
the first weeks compress — that last one is why subject_mentions exists, and
it is the thing that would go wrong silently.
"""
import os
import sys
from datetime import date, datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "fullsim"
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def teardown():
    db = get_client()
    for t in ("subject_mentions", "memory_cache", "memory_stm", "memory_ltm",
              "entity_relations", "user_behavioral_events", "interest_clusters",
              "messages", "sessions", "user_memory", "user_profile",
              "suggestions", "day_events", "care_alerts"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def setup():
    teardown()
    db = get_client()
    db.table("user_profile").insert({
        "user_id": UID, "name": "Kamala", "language_pref": "hinglish",
        "location": "Jaipur",
    }).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 0}).execute()
    try:
        from memory.testing import mark_user_as_test
        mark_user_as_test(UID)
    except Exception:
        pass


# (days ago, what she said). Six weeks, most days quiet, a few that matter.
DAYS = [
    (42, "Namaste, main Kamala. Jaipur mein rehti hoon."),
    (40, "Aaj khichdi banayi thi, achi bani"),
    (38, "Kishore Kumar ke gaane sune shaam ko"),
    (36, "Beta Rajesh ka phone aaya"),
    (34, "Ghutne mein thoda dard hai aajkal"),

    (31, "Khichdi banayi phir se, mann tha"),
    (29, "Lemon rice banaya aaj, alag try kiya"),
    (27, "Kishore da ke purane gaane sunti rahi"),
    (25, "Ghutne ka dard badh gaya hai, chalne mein dikkat"),

    (21, "Rajesh ne bataya wo Diwali pe aayega"),
    (19, "Khichdi hi banayi, halka khana acha lagta hai"),
    (17, "Doctor ke paas gayi thi, ghutne ke liye"),

    (14, "Doctor ne kaha operation karana padega ghutne ka"),
    (12, "Lemon rice banaya, Rajesh ko pasand hai"),
    (10, "Kishore Kumar sunte hue aaram kiya"),

    (7,  "Khichdi banayi, operation ki soch rahi hoon"),
    (5,  "Rajesh aaya tha, do din ruka"),
    (3,  "Rajesh chala gaya, ghar khali lag raha hai"),
    (1,  "Khichdi banayi aaj bhi. Ghutna waisa hi hai."),
]


def live(days_ago: int, text: str):
    """One conversation, through the real session-end path."""
    from supabase_store import save_message
    from memory.user_memory_store import process_session_end

    db = get_client()
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    today = datetime.now(timezone.utc).date().isoformat()
    d = when.date().isoformat()

    s = db.table("sessions").insert({
        "user_id": UID, "model": "gemini-flash-latest",
        "created_at": when.isoformat(), "updated_at": when.isoformat(),
    }).execute().data[0]
    save_message(s["id"], "user", text, "gemini-flash-latest")
    save_message(s["id"], "assistant", "Achha.", "gemini-flash-latest")
    db.table("messages").update({"timestamp": when.isoformat()}) \
      .eq("session_id", s["id"]).execute()

    try:
        process_session_end(s["id"], UID)
    except Exception as e:
        print(f"      session end: {str(e)[:70]}")

    # The writes stamp today; move them to the day they belong to.
    for t, col in (("memory_stm", "happened_on"),
                   ("memory_cache", "happened_on"),
                   ("subject_mentions", "happened_on")):
        try:
            db.table(t).update({col: d}).eq("user_id", UID) \
              .eq(col, today).execute()
        except Exception:
            pass


def main():
    from memory.promotion import review
    from memory.mentions import count_for
    from memory.thread import sweep, recall

    setup()
    print(f"{len(DAYS)} conversations across six weeks\n")
    for ago, text in DAYS:
        print(f"  -{ago:2}d  {text[:56]}")
        live(ago, text)

    db = get_client()

    # ── compression, which is where dates get lost ───────────────────────
    print("\n— sweeping —")
    print(sweep(UID))

    stm = (db.table("memory_stm").select("happened_on,text")
           .eq("user_id", UID).order("happened_on").execute()).data or []
    ltm = (db.table("memory_ltm").select("period,text")
           .eq("user_id", UID).order("period").execute()).data or []
    print(f"\n{len(stm)} days in stm, {len(ltm)} months in ltm")
    for r in ltm:
        print(f"  {r['period']}  {str(r['text'])[:72]}")

    # ── the count has to survive that ────────────────────────────────────
    print("\n— what she talked about, and when —")
    for subject in ("khichdi", "lemon rice", "Kishore", "ghutn", "Rajesh"):
        c = count_for(UID, subject)
        print(f"  {subject:14} {c['days']} days  {', '.join(d[5:] for d in c['dates'][:6])}")

    khichdi = count_for(UID, "khichdi")
    check(khichdi["days"] >= 4,
          "khichdi's early dates survived compression",
          f"{khichdi['days']} days, first {khichdi.get('first')}")

    # ── promotion ────────────────────────────────────────────────────────
    print("\n— what would be promoted —")
    r = review(UID)
    names = [h["subject"].lower() for h in r["habits"]]

    check(any("khichdi" in n for n in names),
          "khichdi is a habit", f"{len(r['habits'])} found")
    check(not any("lemon" in n for n in names),
          "lemon rice is two lunches, not a habit")

    # ── what it ended up knowing ─────────────────────────────────────────
    rows = (db.table("interest_clusters").select("label,kind,attributes,strength")
            .eq("user_id", UID).order("strength", desc=True).execute()).data or []
    print(f"\n— clusters, {len(rows)} —")
    for x in rows:
        a = x.get("attributes") or {}
        print(f"  {str(x['label'])[:26]:28} {str(x.get('kind')):9} "
              f"{str(a.get('category') or '-'):8} {round(float(x.get('strength') or 0), 1)}")

    evs = [x for x in rows if x.get("kind") == "event"]
    check(len(evs) >= 2, "events were recorded", f"{len(evs)}")

    knee = [x for x in rows if "ghutn" in str(x["label"]).lower()
            or "knee" in str(x["label"]).lower()]
    check(bool(knee), "her knee is known")

    # ── and the thread still reads ───────────────────────────────────────
    print("\n— asked about her son —")
    print(recall(UID, "Rajesh ka kya haal hai") or "  (nothing)")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        try:
            main()
        finally:
            print("\n" + "=" * 68)
            if _fails:
                print(f"{len(_fails)} FAILURE(S)")
                for f in _fails:
                    print("   -", f)
            else:
                print("ALL GREEN")
            print("=" * 68)
            if "--keep" not in sys.argv:
                teardown()
                print("torn down")

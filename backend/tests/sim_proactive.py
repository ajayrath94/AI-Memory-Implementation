"""
PROACTIVE SIMULATION HARNESS

The proactive path was verified once, by hand, for one user at one moment. This
seeds users engineered to land in each branch of proactive_check(), runs the
decision across simulated hours, and prints the actual composed message so the
output can be judged rather than just asserted.

Three parts:
  1. DECISION MATRIX — does the engine choose the right action for each state?
  2. MESSAGE REVIEW  — real LLM calls, printed for a human to read.
  3. INVARIANTS      — the things that can be asserted outright.

Users are prefixed simtest_ and torn down in a finally block. There is no test
schema, so this writes to the real database; the teardown is the safety net and
--purge exists if a crash leaves debris.

Run:   railway run python3 backend/tests/sim_proactive.py
       railway run python3 backend/tests/sim_proactive.py --messages
       railway run python3 backend/tests/sim_proactive.py --purge
"""
import sys
import os
import uuid
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

PREFIX = "simtest_"


# ── seeding ───────────────────────────────────────────────────────────────────

def _mins_ago(m):
    return (datetime.now(timezone.utc) - timedelta(minutes=m)).isoformat()


def seed_user(uid, *, last_msg_mins=None, profile=None, memory=None,
              schedule=None, location=None, persona=None):
    """Create one synthetic user. Every table is optional — absence is itself a
    case worth testing (no memory row, no persona, no schedule)."""
    db = get_client()

    db.table("user_profile").insert({
        "user_id": uid,
        "name": (profile or {}).get("name", "Sim"),
        **{k: v for k, v in (profile or {}).items() if k != "name"},
    }).execute()

    if memory is not None:
        db.table("user_memory").insert({"user_id": uid, **memory}).execute()

    if persona is not None:
        db.table("bot_personas").insert({
            "user_id": uid, "voice_type": "preset",
            "slangs": [], "language_mix": {}, "personality": {},
            **persona,
        }).execute()

    if schedule:
        db.table("care_schedule").insert(
            [{"user_id": uid, "active": True, **s} for s in schedule]).execute()

    if location:
        db.table("user_context").insert({"user_id": uid, **location}).execute()

    if last_msg_mins is not None:
        sid = str(uuid.uuid4())
        db.table("sessions").insert({
            "id": sid, "user_id": uid, "model": "sim", "title": "SIM",
        }).execute()
        db.table("messages").insert({
            "session_id": sid, "role": "user", "model": "sim",
            "content": "sim seed message",
            "timestamp": _mins_ago(last_msg_mins),
        }).execute()
        # The silence signal is sessions.updated_at, NOT the message timestamp —
        # inserting the row sets it to now, so without this every seeded user
        # looks like they just spoke. Backdate it as a second write, since the
        # insert would otherwise override whatever we passed.
        db.table("sessions").update(
            {"updated_at": _mins_ago(last_msg_mins)}).eq("id", sid).execute()


def teardown():
    db = get_client()
    for table, col in (("messages", None), ("sessions", "user_id"),
                       ("care_schedule", "user_id"), ("user_context", "user_id"),
                       ("bot_personas", "user_id"), ("user_memory", "user_id"),
                       ("proactive_events", "user_id"), ("user_profile", "user_id")):
        try:
            if table == "messages":
                sess = (db.table("sessions").select("id")
                        .like("user_id", f"{PREFIX}%").execute()).data or []
                for s in sess:
                    db.table("messages").delete().eq("session_id", s["id"]).execute()
            else:
                db.table(table).delete().like(col, f"{PREFIX}%").execute()
        except Exception as e:
            print(f"  teardown {table}: {str(e)[:70]}")


# ── the cases ─────────────────────────────────────────────────────────────────
# Each is engineered so exactly one branch of proactive_check should fire.

HEALTH = {"health": {"conditions": ["knee pain"], "medications": ["BP tablet"]}}

# A realistic profile. The thin one above is the floor — worth testing, but on
# its own it only shows what the composer does with nothing, and every message
# comes back as the same generic fallback. Real users have a routine, interests,
# and a summary to draw on; that is where the composer earns its cost.
RICH = {
    "name": "Lakshmi",
    "age_group": "70-80",
    "location": "Surat",
    "language_pref": "hinglish",
    "health": {
        "conditions": ["knee pain", "high blood pressure"],
        "medications": ["Amlodipine", "Thyronorm"],
        "concerns": ["knee pain worse in cold weather"],
    },
    "interests": {
        "music": ["Lata Mangeshkar", "old Hindi film songs"],
        "hobbies": ["gardening", "listening to bhajans"],
        "entertainment": ["Dilip Kumar films"],
    },
    "family": {"children": ["Arjun"], "grandchildren": ["Ananya"]},
}

RICH_MEMORY = {
    "summary": ("Lakshmi lives in Surat and manages knee pain that worsens in "
                "cold weather. She listens to Lata Mangeshkar most afternoons "
                "and tends her garden in the mornings. Her son Arjun calls on "
                "Sundays; her granddaughter Ananya is learning to walk."),
    "key_facts": [
        "Lives in Surat",
        "Knee pain worse in cold weather",
        "Listens to Lata Mangeshkar in the afternoons",
        "Son Arjun calls on Sundays",
    ],
    "session_count": 24,
}

RICH_SCHEDULE = [
    {"time_of_day": "06:30:00", "type": "routine",    "label": "Morning puja"},
    {"time_of_day": "07:00:00", "type": "medication", "label": "Thyronorm"},
    {"time_of_day": "08:30:00", "type": "meal",       "label": "Breakfast"},
    {"time_of_day": "13:00:00", "type": "meal",       "label": "Lunch"},
    {"time_of_day": "17:30:00", "type": "routine",    "label": "Evening walk"},
    {"time_of_day": "19:30:00", "type": "meal",       "label": "Dinner"},
    {"time_of_day": "20:00:00", "type": "medication", "label": "Amlodipine"},
]

CASES = [
    dict(uid=PREFIX + "med_due",
         desc="medication due at the test hour",
         seed=dict(last_msg_mins=30, profile=HEALTH,
                   schedule=[{"time_of_day": "14:00:00", "type": "medication",
                              "label": "BP tablet"}]),
         hours=[14], expect="MEDICATION_REMINDER"),

    dict(uid=PREFIX + "late_night",
         desc="silent 8h, but it is 2am — they are asleep, not silent",
         seed=dict(last_msg_mins=480, profile=HEALTH),
         hours=[2], expect="SILENCE"),

    dict(uid=PREFIX + "away_night",
         desc="away from home at 2am — safety overrides the quiet gate",
         seed=dict(last_msg_mins=60, profile=HEALTH,
                   location={"home_lat": 21.17, "home_lng": 72.83,
                             "last_lat": 28.61, "last_lng": 77.20,
                             "timezone": "Asia/Kolkata"}),
         hours=[2], expect="SAFETY_INFO"),

    dict(uid=PREFIX + "quiet_day",
         desc="silent 7h in the afternoon, full profile — the realistic case",
         seed=dict(last_msg_mins=420, profile=RICH, memory=RICH_MEMORY,
                   schedule=RICH_SCHEDULE),
         hours=[14], expect="CHECK_IN"),

    dict(uid=PREFIX + "active",
         desc="spoke 10 minutes ago — do not interrupt",
         seed=dict(last_msg_mins=10, profile=HEALTH),
         hours=[14], expect="SILENCE"),

    dict(uid=PREFIX + "just_under",
         desc="silent 5h50m — just under the 6h threshold",
         seed=dict(last_msg_mins=350, profile=HEALTH),
         hours=[14], expect="SILENCE"),

    dict(uid=PREFIX + "no_memory",
         desc="profile but no memory row — must not crash",
         seed=dict(last_msg_mins=420, profile=HEALTH, memory=None),
         hours=[14], expect="CHECK_IN"),

    dict(uid=PREFIX + "familial",
         desc="companion is a son named Shubham",
         seed=dict(last_msg_mins=420, profile=RICH, memory=RICH_MEMORY,
                   schedule=RICH_SCHEDULE,
                   persona={"bot_name": "Shubham", "relationship": "son",
                            "bot_name_history": ["Shubham"]}),
         hours=[14], expect="CHECK_IN"),
]


# ── part 1: decision matrix ───────────────────────────────────────────────────

def run_decisions():
    from memory.proactive_engine import proactive_check

    print("=" * 78)
    print("PART 1 — DECISION MATRIX")
    print("=" * 78)
    passed = failed = 0

    for case in CASES:
        for hour in case["hours"]:
            d = proactive_check(case["uid"], override_hour=hour)
            got = d.get("action")
            ok = got == case["expect"]
            passed += ok
            failed += not ok
            mark = "ok  " if ok else "FAIL"
            print(f"{mark} {case['uid'][len(PREFIX):]:14} {hour:02d}h  "
                  f"{got:22} want {case['expect']}")
            print(f"     {case['desc']}")
            if not ok:
                print(f"     reason={d.get('reason')} slot={d.get('slot')} "
                      f"away={d.get('away_from_home')}")
    print(f"\n{passed} passed, {failed} failed")
    return failed


# ── part 2: message review ────────────────────────────────────────────────────

def run_messages():
    from memory.proactive_engine import proactive_check
    from memory.schedule_engine import generate_proactive_script

    print()
    print("=" * 78)
    print("PART 2 — MESSAGE REVIEW  (read these; no assertion can judge warmth)")
    print("=" * 78)

    for case in CASES:
        for hour in (8, 13, 20):
            d = proactive_check(case["uid"], override_hour=hour)
            if d.get("action") == "SILENCE":
                continue
            r = generate_proactive_script(case["uid"], hour=hour,
                                          action=d.get("action")) or {}
            script = (r.get("script") or "").replace("\n", " ")
            print(f"\n── {case['uid'][len(PREFIX):]} @ {hour:02d}h  "
                  f"[{d.get('action')} / {r.get('priority')}]")
            print(f"   {script[:300] or '(empty)'}")

            # Assert what can be asserted. Eyeballing thirteen messages catches
            # today's bug and misses next week's.
            from memory.intent_spec import run_checks
            intent = {"MEDICATION_REMINDER": "medication",
                      "SAFETY_INFO": "safety",
                      "EXPLORE_OFFER": "recommendation"}.get(d.get("action"), "check_in")
            seed = case["seed"]
            routine = seed.get("schedule") or []
            meds = [s.get("label") for s in routine if s.get("type") == "medication"]
            due = [s.get("label") for s in routine
                   if s.get("type") == "medication"
                   and str(s.get("time_of_day", ""))[:2].isdigit()
                   and abs(int(str(s["time_of_day"])[:2]) - hour) <= 1]
            for problem in run_checks(script, intent,
                                      due_labels=due, all_medications=meds,
                                      current_hour=hour, routine=routine):
                print(f"   !! {problem}")


# ── part 3: invariants ────────────────────────────────────────────────────────

def run_invariants():
    from memory.proactive_engine import proactive_check
    from memory.proactive_log import log_decision

    print()
    print("=" * 78)
    print("PART 3 — INVARIANTS")
    print("=" * 78)
    fails = []

    # never contacts at 3am unless it is medication or a safety issue
    for case in CASES:
        d = proactive_check(case["uid"], override_hour=3)
        act = d.get("action")
        if act not in ("SILENCE", "MEDICATION_REMINDER", "SAFETY_INFO"):
            fails.append(f"{case['uid']} returned {act} at 3am")

    # one decision per user/day/action, however often the pass runs
    uid = CASES[3]["uid"]          # quiet_day
    d = proactive_check(uid, override_hour=14)
    first  = log_decision(d)
    second = log_decision(d)
    if not first.get("logged"):
        fails.append("first log_decision did not log")
    if not second.get("duplicate"):
        fails.append("second log_decision was not deduped")

    for f in fails:
        print("FAIL", f)
    print(f"\n{len(fails)} invariant failure(s)")
    return len(fails)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if "--purge" in sys.argv:
        teardown()
        print("purged")
        return

    print(f"seeding {len(CASES)} synthetic users…")
    try:
        teardown()          # clear anything a previous crash left
        for case in CASES:
            seed_user(case["uid"], **case["seed"])
        print("seeded\n")

        failed = run_decisions()
        if "--messages" in sys.argv:
            run_messages()
        failed += run_invariants()

        print("\n" + "=" * 78)
        print("ALL GREEN" if failed == 0 else f"{failed} FAILURE(S)")
        print("=" * 78)
    finally:
        teardown()
        print("\ntorn down")


if __name__ == "__main__":
    main()

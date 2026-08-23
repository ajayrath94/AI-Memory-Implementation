"""
ALERT SIMULATION HARNESS

This is the feature where a silent failure has real consequences: a daughter is
not told her mother has been withdrawn for a week. It was silently broken for
its whole life — every session in the database had soft_flags=[], because mood
extraction sat behind `if not session_summary: return` and short conversations
produce no summary. The most concerning exchanges were exactly the ones that
generated no signal.

So this tests each stage separately rather than only "did an email arrive":

  1. STAGES      — flags extracted, flags stored, pattern counted, LLM confirms
  2. THRESHOLDS  — both directions. A single "tired" must NOT alert; that false
                   positive is what teaches a caregiver to ignore the emails.
  3. DELIVERY    — caregiver linked, no caregiver, cooldown. Stops at the send
                   boundary; use --send once to see a real email render.
  4. ACUTE       — bypasses everything. The most consequential branch and it has
                   never run.
  5. MESSAGE     — printed for a human. "Would a daughter find this useful" is
                   not assertable.

Users are prefixed alerttest_ and torn down in a finally block.

Run:  railway run python3 backend/tests/sim_alerts.py
      railway run python3 backend/tests/sim_alerts.py --messages
      railway run python3 backend/tests/sim_alerts.py --purge
"""
import sys
import os
import uuid
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

PREFIX = "alerttest_"


# ── seeding ───────────────────────────────────────────────────────────────────

def seed_sessions(uid, convos, with_profile=True):
    """Create a user with N past conversations, each run through the real
    session-end path so mood and flags are produced the way production does."""
    db = get_client()
    if with_profile:
        db.table("user_profile").insert({
            "user_id": uid, "name": "AlertSim",
            "health": {"conditions": ["knee pain"]},
        }).execute()

    from memory.user_memory_store import process_session_end
    for i, turns in enumerate(convos):
        sid = str(uuid.uuid4())
        db.table("sessions").insert({
            "id": sid, "user_id": uid, "model": "sim", "title": "SIM",
        }).execute()
        db.table("messages").insert(
            [{"session_id": sid, "role": "user", "content": t, "model": "sim"}
             for t in turns]).execute()
        process_session_end(sid, uid)


def link_caregiver(uid, email="sim@example.invalid"):
    db = get_client()
    cg = (db.table("caregivers").insert({
        "name": "Sim Caregiver", "email": email, "org_type": "family",
    }).execute()).data
    cid = cg[0]["id"] if cg else None
    db.table("care_relationships").insert({
        "user_id": uid, "caregiver_id": cid, "active": True,
    }).execute()
    return cid


def teardown():
    db = get_client()
    try:
        users = (db.table("user_profile").select("user_id")
                 .like("user_id", f"{PREFIX}%").execute()).data or []
        for u in users:
            uid = u["user_id"]
            sess = (db.table("sessions").select("id")
                    .eq("user_id", uid).execute()).data or []
            for s in sess:
                db.table("messages").delete().eq("session_id", s["id"]).execute()
            for t in ("sessions", "care_relationships", "alerts",
                      "user_behavioral_events", "interest_clusters",
                      "user_memory", "suggestions", "user_context",
                      "bot_personas", "user_profile"):
                try:
                    db.table(t).delete().eq("user_id", uid).execute()
                except Exception:
                    pass
        db.table("caregivers").delete().eq("name", "Sim Caregiver").execute()
    except Exception as e:
        print(f"  teardown: {str(e)[:80]}")


# ── transcripts ───────────────────────────────────────────────────────────────

DECLINING = [
    ["aaj bahut thak gayi hoon", "kuch karne ka mann nahi ho raha"],
    ["akela lagta hai ghar mein", "koi baat karne wala nahi hai"],
    ["neend nahi aa rahi raat ko", "thakan lagti hai din bhar"],
]

ONE_BAD_DAY = [
    ["aaj thodi thak gayi hoon", "bas neend puri nahi hui"],
    ["aaj mausam accha hai", "bagiche mein kaam kiya subah"],
    ["Kishore Kumar ke gaane sune aaj", "bahut accha laga"],
]

FINE = [
    ["aaj accha din raha", "beta ne phone kiya tha"],
    ["mandir gayi thi subah", "acha laga"],
]

ACUTE = [
    ["seene mein bahut dard ho raha hai", "saans lene mein takleef hai"],
]


# ── 1 & 2: stages and thresholds ──────────────────────────────────────────────

def run_detection():
    from memory.alert_engine import detect_alerts

    print("=" * 78)
    print("PARTS 1-2 — STAGES AND THRESHOLDS")
    print("=" * 78)
    cases = [
        (PREFIX + "declining", DECLINING,  True,
         "fatigue and loneliness across three sessions"),
        (PREFIX + "one_bad",   ONE_BAD_DAY, False,
         "one tired day then two good ones — must NOT alert"),
        (PREFIX + "fine",      FINE,        False,
         "nothing wrong at all"),
        (PREFIX + "acute",     ACUTE,       True,
         "chest pain — must alert immediately, no pattern needed"),
    ]

    failures = 0
    for uid, convos, expect_alert, desc in cases:
        seed_sessions(uid, convos)

        # stage check: did flags actually reach the session rows?
        rows = (get_client().table("sessions").select("valence,soft_flags,acute")
                .eq("user_id", uid).execute()).data or []
        flagged = sum(1 for r in rows if r.get("soft_flags"))
        alerts = detect_alerts(uid)
        got = bool(alerts)
        ok = got == expect_alert
        failures += not ok

        print(f"\n{'ok  ' if ok else 'FAIL'} {uid[len(PREFIX):]:12} "
              f"alert={got} want={expect_alert}")
        print(f"     {desc}")
        print(f"     {len(rows)} session(s), {flagged} with flags")
        for r in rows:
            print(f"       valence={str(r.get('valence')):6} "
                  f"acute={r.get('acute')} flags={r.get('soft_flags')}")
        for a in alerts:
            print(f"     -> [{a['severity']}] {a['alert_type']}: {a['message'][:90]}")

    print(f"\n{len(cases) - failures}/{len(cases)} correct")
    return failures


# ── 3: delivery boundaries ────────────────────────────────────────────────────

def run_delivery(really_send=False):
    from memory.alert_engine import run_alert_engine
    import memory.alert_engine as AE

    print()
    print("=" * 78)
    print("PART 3 — DELIVERY")
    print("=" * 78)
    failures = 0

    # Intercept at the send boundary. Asserting the call is made with the right
    # arguments is the useful test; actually sending is a separate decision.
    sent = []
    if not really_send:
        original = AE.send_email_alert
        AE.send_email_alert = lambda *a, **k: (sent.append((a, k)), True)[1]

    try:
        # a) no caregiver — detected, not sent, no crash
        uid = PREFIX + "nocaregiver"
        seed_sessions(uid, DECLINING)
        r = run_alert_engine(uid)
        ok = r.get("sent") == 0 and r.get("reason") == "no_caregivers"
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'} no caregiver linked -> {r}")

        # b) caregiver linked — sends
        uid2 = PREFIX + "withcaregiver"
        seed_sessions(uid2, DECLINING)
        link_caregiver(uid2)
        r2 = run_alert_engine(uid2)
        ok2 = (r2.get("sent") or 0) >= 1
        failures += not ok2
        print(f"{'ok  ' if ok2 else 'FAIL'} caregiver linked   -> {r2}")
        if sent:
            args, _ = sent[-1]
            print(f"     would email: to={args[0]} user={args[2]} "
                  f"alerts={len(args[3])}")

        # c) same pattern again — 24h cooldown must suppress it, or a scheduler
        #    running every fifteen minutes emails a daughter four times an hour
        r3 = run_alert_engine(uid2)
        ok3 = (r3.get("sent") or 0) == 0
        failures += not ok3
        print(f"{'ok  ' if ok3 else 'FAIL'} second run (cooldown) -> {r3}")
    finally:
        if not really_send:
            AE.send_email_alert = original

    print(f"\n{3 - failures}/3 correct")
    return failures


# ── 5: the message a caregiver actually receives ──────────────────────────────

def run_messages():
    from memory.alert_engine import detect_alerts

    print()
    print("=" * 78)
    print("PART 5 — WHAT THE CAREGIVER READS  (no assertion can judge this)")
    print("=" * 78)
    for uid, convos, label in ((PREFIX + "msg_decline", DECLINING, "gradual decline"),
                               (PREFIX + "msg_acute", ACUTE, "acute")):
        seed_sessions(uid, convos)
        for a in detect_alerts(uid):
            print(f"\n── {label} [{a['severity']}] {a['alert_type']}")
            print(f"   {a['message']}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if "--purge" in sys.argv:
        teardown()
        print("purged")
        return

    really_send = "--send" in sys.argv
    if really_send:
        print("!! --send given: this will deliver real email\n")

    try:
        teardown()
        failures = run_detection()
        failures += run_delivery(really_send)
        if "--messages" in sys.argv:
            run_messages()

        print("\n" + "=" * 78)
        print("ALL GREEN" if failures == 0 else f"{failures} FAILURE(S)")
        print("=" * 78)
    finally:
        teardown()
        print("\ntorn down")


if __name__ == "__main__":
    main()

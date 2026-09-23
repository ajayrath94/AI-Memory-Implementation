"""
The same conversation, twice.

    railway run python3 -u backend/tests/sim_stable.py
    railway run python3 -u backend/tests/sim_stable.py --keep

Thirteen sentences run twice gave different answers: fourteen clusters then
twelve, Rafi as a person then as an interest, Mughal-e-Azam as dekhna then as
sangeet. Three assertions flipped between runs.

Nothing downstream can be measured against that. A threshold tuned against a
test that answers differently each time is tuned against noise, and every
"fix" after it is a coin toss that happened to land.

WHAT THIS DOES
Runs one conversation through the real path twice, as two users, and diffs
what each ended up knowing. No assertions about whether the answers are RIGHT
— only whether they are the SAME.

WHAT DRIFT MEANS

    a cluster in one run and not the other     the resolver merged it one
                                               time and not the other
    the same cluster, different kind           the type is being guessed
    the same cluster, different category       it will be offered at a
                                               different hour, or never
    strengths far apart                        the ranking is unstable, and
                                               the picker draws from it

A little drift is expected — these are model calls, not arithmetic. A lot
means the pipeline is not yet measurable.
"""
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

RUNS = ("stableA", "stableB")

# Ordinary sentences, each on its own day. Deliberately the same shape as
# sim_interests, so drift found here explains failures found there.
SAID = [
    "Lata Mangeshkar ke gaane sunti hoon roz shaam ko",
    "Mughal-e-Azam meri favourite film hai",
    "Aaj phir Mohammed Rafi ke gaane sune",
    "Rafi saab ki awaaz mein kuch alag hi baat hai",
    "Bagwani karti hoon subah subah",
    "Ghutne mein dard rehta hai aajkal",
    "Mera beta Rajesh Mumbai mein rehta hai",
    "BP ki dawai roz subah leti hoon",
    "Rajma chawal bahut pasand hai mujhe",
]


def teardown():
    db = get_client()
    for uid in RUNS:
        for t in ("subject_mentions", "memory_cache", "memory_stm",
                  "memory_ltm", "entity_relations", "user_behavioral_events",
                  "interest_clusters", "messages", "sessions", "user_memory",
                  "user_profile"):
            try:
                db.table(t).delete().eq("user_id", uid).execute()
            except Exception:
                pass


def setup(uid):
    db = get_client()
    db.table("user_profile").insert({
        "user_id": uid, "name": "Kamala", "language_pref": "hinglish",
        "location": "Jaipur",
    }).execute()
    db.table("user_memory").insert({"user_id": uid, "session_count": 0}).execute()
    try:
        from memory.testing import mark_user_as_test
        mark_user_as_test(uid)
    except Exception:
        pass


async def live(uid):
    from supabase_store import save_message
    from memory.user_memory_store import process_session_end

    db = get_client()
    for i, text in enumerate(SAID):
        when = datetime.now(timezone.utc) - timedelta(days=len(SAID) - i)
        s = db.table("sessions").insert({
            "user_id": uid, "model": "gemini-flash-latest",
            "created_at": when.isoformat(), "updated_at": when.isoformat(),
        }).execute().data[0]
        save_message(s["id"], "user", text, "gemini-flash-latest")
        save_message(s["id"], "assistant", "Achha.", "gemini-flash-latest")
        db.table("messages").update({"timestamp": when.isoformat()}) \
          .eq("session_id", s["id"]).execute()
        try:
            process_session_end(s["id"], uid)
        except Exception as e:
            print(f"     {uid}: session end: {str(e)[:60]}")


def snapshot(uid):
    """What this run ended up knowing, keyed by label."""
    db = get_client()
    rows = (db.table("interest_clusters")
            .select("label,kind,pillar,strength,event_count,attributes")
            .eq("user_id", uid).neq("kind", "event").execute()).data or []
    out = {}
    for r in rows:
        a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        out[str(r["label"]).strip().lower()] = {
            "label": r["label"],
            "kind": r.get("kind"),
            "category": a.get("category"),
            "strength": round(float(r.get("strength") or 0), 1),
            "events": r.get("event_count"),
        }
    return out


def main():
    teardown()
    for uid in RUNS:
        setup(uid)
        print(f"— {uid} —")
        asyncio.run(live(uid))

    a, b = snapshot(RUNS[0]), snapshot(RUNS[1])
    keys = sorted(set(a) | set(b))

    print(f"\n{'':28} {'run A':22} {'run B':22}")
    drift = {"missing": [], "kind": [], "category": [], "strength": []}

    for k in keys:
        ra, rb = a.get(k), b.get(k)
        if not ra or not rb:
            drift["missing"].append(k)
            side = "A only" if ra else "B only"
            r = ra or rb
            print(f"  {r['label'][:26]:28} {side:22} "
                  f"{r['kind']}/{r['category'] or '–'}")
            continue

        same_kind = ra["kind"] == rb["kind"]
        same_cat = ra["category"] == rb["category"]
        gap = abs(ra["strength"] - rb["strength"])
        if not same_kind:
            drift["kind"].append(k)
        if not same_cat:
            drift["category"].append(k)
        if gap > 1.0:
            drift["strength"].append(k)

        flag = "" if (same_kind and same_cat and gap <= 1.0) else "  <-"
        left = f"{ra['kind']}/{ra['category'] or '–'} {ra['strength']}"
        right = f"{rb['kind']}/{rb['category'] or '–'} {rb['strength']}"
        print(f"  {ra['label'][:26]:28} {left:22} {right:22}{flag}")

    print()
    print(f"  {len(a)} clusters in A, {len(b)} in B")
    print(f"  in one run only : {len(drift['missing'])}  {drift['missing']}")
    print(f"  different kind  : {len(drift['kind'])}  {drift['kind']}")
    print(f"  different class : {len(drift['category'])}  {drift['category']}")
    print(f"  strength > 1.0  : {len(drift['strength'])}  {drift['strength']}")

    total = sum(len(v) for v in drift.values())
    print()
    if total == 0:
        print("  STABLE — the same conversation recorded the same way twice.")
    elif total <= 2:
        print(f"  {total} differences. Model calls are not arithmetic; this is")
        print("  about what a stable pipeline looks like.")
    else:
        print(f"  {total} differences. Not yet measurable — a threshold tuned")
        print("  against this is tuned against noise.")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        try:
            main()
        finally:
            if "--keep" not in sys.argv:
                print()
                teardown()
                print("torn down")

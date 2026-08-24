"""
PATTERN SIMULATION HARNESS

The anchor everything else will be measured against. If wake time is wrong,
every deviation read from it is wrong, and the errors are silent — a companion
asking "aaj puja nahi ki?" at the wrong hour looks like it is not paying
attention rather than like a bug.

Two failures were found writing these routes, both invisible without a test:

  - Wrapping a bare label in a sentence to help the extractor did the opposite.
    With a full sentence it reads the SPEAKER as the subject, so Punjabi came
    back "self" where the bare label gave "morning prayer".
  - Keying the upsert on the canonical label turned an edit into a duplicate,
    because canonicalisation is a model call and drifts between runs. One puja
    became two rows.

Both are the kind of thing that looks fine in the code and only shows up when
you count what actually landed.

Run:  railway run python3 backend/tests/sim_patterns.py
      railway run python3 backend/tests/sim_patterns.py --purge
"""
import sys
import os
import uuid
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

PREFIX = "pattest_"


# ── helpers ───────────────────────────────────────────────────────────────────

def make_user(uid):
    get_client().table("user_profile").insert({
        "user_id": uid, "name": "PatSim", "language_pref": "hinglish",
    }).execute()


def seed_pairs(uid, pairs):
    """Seed explicit (first, last) local minute-of-day pairs, one per day."""
    from zoneinfo import ZoneInfo
    db, IST = get_client(), ZoneInfo("Asia/Kolkata")
    for d, (first, last) in enumerate(pairs):
        for mins in (first, last):
            local = (datetime.now(IST) - timedelta(days=d + 1)).replace(
                hour=(mins // 60) % 24, minute=mins % 60, second=0, microsecond=0)
            sid = str(uuid.uuid4())
            when = local.astimezone(timezone.utc).isoformat()
            db.table("sessions").insert({
                "id": sid, "user_id": uid, "model": "sim", "title": "SIM",
                "updated_at": when}).execute()
            db.table("messages").insert({
                "session_id": sid, "role": "user", "model": "sim",
                "content": "x", "timestamp": when}).execute()


def run_midnight():
    """A day does not end at midnight. Grouping on the calendar date put a
    00:20 message at the START of the next day, so someone waking at 07:00 and
    sleeping around midnight derived as wake 03:40, sleep 15:15."""
    from memory.patterns import observe

    print()
    print("=" * 78)
    print("PART 6 — MIDNIGHT WRAPAROUND")
    print("=" * 78)

    uid = PREFIX + "midnight"
    make_user(uid)
    seed_pairs(uid, [(7 * 60, 23 * 60 + 40), (7 * 60, 24 * 60 + 20),
                     (7 * 60, 23 * 60 + 50), (7 * 60, 24 * 60 + 10),
                     (7 * 60, 23 * 60 + 30), (7 * 60, 24 * 60 + 15)])
    observe(uid)

    failures = 0
    wake  = next((r for r in rows_for(uid, "wake")), None)
    sleep = next((r for r in rows_for(uid, "sleep")), None)

    ok = wake and str(wake["observed_at"]).startswith("07:")
    failures += not ok
    print(f"{'ok  ' if ok else 'FAIL'} wake  {wake['observed_at'] if wake else None} "
          f"spread={wake['spread_min'] if wake else None} (expected ~07:00)")

    ok2 = sleep and (str(sleep["observed_at"])[:2] in ("23", "00")) \
          and (sleep.get("spread_min") or 0) < 120
    failures += not ok2
    print(f"{'ok  ' if ok2 else 'FAIL'} sleep {sleep['observed_at'] if sleep else None} "
          f"spread={sleep['spread_min'] if sleep else None} (expected ~00:00, tight)")

    print(f"\n{2 - failures}/2 correct")
    return failures


def seed_days(uid, hours, days=6):
    """Sessions and messages at a given local hour each day, so the observation
    pass has something to derive a wake time from."""
    db = get_client()
    for d in range(days):
        for h in hours:
            # Seed in LOCAL time. observe() converts UTC to Asia/Kolkata, so
            # setting hour=7 on a UTC stamp lands at 12:30 IST and every seeded
            # user came out with the same nonsense wake time.
            from zoneinfo import ZoneInfo
            local = (datetime.now(ZoneInfo("Asia/Kolkata"))
                     - timedelta(days=d + 1)).replace(hour=h, minute=10,
                                                      second=0, microsecond=0)
            when = local.astimezone(timezone.utc)
            sid = str(uuid.uuid4())
            db.table("sessions").insert({
                "id": sid, "user_id": uid, "model": "sim", "title": "SIM",
                "updated_at": when.isoformat(),
            }).execute()
            db.table("messages").insert({
                "session_id": sid, "role": "user", "model": "sim",
                "content": "sim message", "timestamp": when.isoformat(),
            }).execute()


def rows_for(uid, kind=None):
    q = get_client().table("user_patterns").select("*").eq("user_id", uid)
    if kind:
        q = q.eq("kind", kind)
    return q.execute().data or []


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
            for t in ("sessions", "user_patterns", "user_behavioral_events",
                      "interest_clusters", "user_memory", "user_profile"):
                try:
                    db.table(t).delete().eq("user_id", uid).execute()
                except Exception:
                    pass
    except Exception as e:
        print(f"  teardown: {str(e)[:80]}")


# ── 1: declared and observed coexist ──────────────────────────────────────────

def run_coexist():
    from routes.care import set_patterns, PatternsIn
    from memory.patterns import observe

    print("=" * 78)
    print("PART 1 — DECLARED AND OBSERVED DO NOT OVERWRITE EACH OTHER")
    print("=" * 78)
    failures = 0

    uid = PREFIX + "coexist"
    make_user(uid)
    seed_days(uid, hours=[7, 12, 20])
    set_patterns(uid, PatternsIn(wake="06:30", sleep="22:00"))
    observe(uid)

    wake = next((r for r in rows_for(uid, "wake")), None)
    ok = bool(wake and wake.get("declared_at") and wake.get("observed_at"))
    failures += not ok
    print(f"{'ok  ' if ok else 'FAIL'} wake: declared={wake.get('declared_at') if wake else None} "
          f"observed={wake.get('observed_at') if wake else None}")

    # and the other way round: observing first, then declaring
    uid2 = PREFIX + "reverse"
    make_user(uid2)
    seed_days(uid2, hours=[7, 20])
    observe(uid2)
    set_patterns(uid2, PatternsIn(wake="06:30"))
    wake2 = next((r for r in rows_for(uid2, "wake")), None)
    ok2 = bool(wake2 and wake2.get("declared_at") and wake2.get("observed_at"))
    failures += not ok2
    print(f"{'ok  ' if ok2 else 'FAIL'} observed first, then declared: "
          f"declared={wake2.get('declared_at') if wake2 else None} "
          f"observed={wake2.get('observed_at') if wake2 else None}")

    print(f"\n{2 - failures}/2 correct")
    return failures


# ── 2: canonicalisation across scripts ────────────────────────────────────────

def run_canon():
    from routes.care import set_patterns, PatternsIn, RoutineItem

    print()
    print("=" * 78)
    print("PART 2 — CANONICALISATION")
    print("=" * 78)

    uid = PREFIX + "canon"
    make_user(uid)
    natives = ["ਸਵੇਰ ਦੀ ਪੂਜਾ", "सुबह की पूजा", "shaam ki sair", "evening walk"]
    set_patterns(uid, PatternsIn(routines=[
        RoutineItem(label=n, at=f"{6 + i}:00") for i, n in enumerate(natives)]))

    failures = 0
    for r in rows_for(uid, "routine"):
        native, label = r.get("label_native"), r.get("label")
        # The label must exist and the native text must survive verbatim. A
        # label that is still in the original script is a soft miss, not a
        # failure — falling back to their own words is better than nothing.
        ok = bool(label) and native in natives
        failures += not ok
        canon = label != native
        print(f"{'ok  ' if ok else 'FAIL'} {str(native):16} -> {str(label):18} "
              f"{'(canonicalised)' if canon else '(kept as written)'}")

    print(f"\n{len(natives) - failures}/{len(natives)} correct")
    return failures


# ── 3: submitting twice must not duplicate ────────────────────────────────────

def run_idempotent():
    from routes.care import set_patterns, PatternsIn, RoutineItem

    print()
    print("=" * 78)
    print("PART 3 — RESUBMITTING IS AN EDIT, NOT A DUPLICATE")
    print("=" * 78)
    failures = 0

    uid = PREFIX + "idem"
    make_user(uid)
    body = PatternsIn(
        wake="06:30",
        meals={"lunch": "13:00"},
        routines=[RoutineItem(label="ਸਵੇਰ ਦੀ ਪੂਜਾ", at="06:45")],
    )
    set_patterns(uid, body)
    set_patterns(uid, body)
    set_patterns(uid, body)

    counts = {k: len(rows_for(uid, k)) for k in ("wake", "meal", "routine")}
    ok = counts == {"wake": 1, "meal": 1, "routine": 1}
    failures += not ok
    print(f"{'ok  ' if ok else 'FAIL'} three identical submissions -> {counts}")

    # changing the time edits the row rather than adding one
    set_patterns(uid, PatternsIn(
        routines=[RoutineItem(label="ਸਵੇਰ ਦੀ ਪੂਜਾ", at="07:15")]))
    routines = rows_for(uid, "routine")
    ok2 = len(routines) == 1 and str(routines[0].get("declared_at")).startswith("07:15")
    failures += not ok2
    print(f"{'ok  ' if ok2 else 'FAIL'} changing the time edits in place -> "
          f"{len(routines)} row(s) at {routines[0].get('declared_at') if routines else None}")

    print(f"\n{2 - failures}/2 correct")
    return failures


# ── 4: drift — the whole point of the feature ─────────────────────────────────

def run_drift():
    from routes.care import set_patterns, PatternsIn, get_patterns
    from memory.patterns import observe

    print()
    print("=" * 78)
    print("PART 4 — DRIFT DETECTION")
    print("=" * 78)
    failures = 0

    # says 6:30, actually talks at 9 — a real divergence
    uid = PREFIX + "drift"
    make_user(uid)
    set_patterns(uid, PatternsIn(wake="06:30"))
    seed_days(uid, hours=[9, 20])
    observe(uid)
    wake = next((r for r in rows_for(uid, "wake")), None)
    drift = wake.get("drift_min") if wake else None
    ok = drift is not None and abs(drift) >= 45
    failures += not ok
    print(f"{'ok  ' if ok else 'FAIL'} declared 06:30, observed "
          f"{wake.get('observed_at') if wake else None} -> drift {drift} min")

    # says 7:00, talks at 7:10 — inside their own variability, not a drift
    uid2 = PREFIX + "nodrift"
    make_user(uid2)
    set_patterns(uid2, PatternsIn(wake="07:00"))
    seed_days(uid2, hours=[7, 20])
    observe(uid2)
    wake2 = next((r for r in rows_for(uid2, "wake")), None)
    drift2 = wake2.get("drift_min") if wake2 else None
    ok2 = not drift2
    failures += not ok2
    print(f"{'ok  ' if ok2 else 'FAIL'} declared 07:00, observed "
          f"{wake2.get('observed_at') if wake2 else None} -> drift {drift2} "
          f"(small gaps must not count)")

    surfaced = get_patterns(uid).get("drifting") or []
    ok3 = len(surfaced) >= 1
    failures += not ok3
    print(f"{'ok  ' if ok3 else 'FAIL'} drift surfaced on the read route: {surfaced}")

    print(f"\n{3 - failures}/3 correct")
    return failures


# ── 5: input validation ───────────────────────────────────────────────────────

def run_validation():
    from routes.care import set_patterns, PatternsIn, RoutineItem

    print()
    print("=" * 78)
    print("PART 5 — BAD AND PARTIAL INPUT")
    print("=" * 78)
    failures = 0

    uid = PREFIX + "valid"
    make_user(uid)

    cases = [
        ("hour out of range", PatternsIn(wake="25:00"), 0),
        ("not a time",        PatternsIn(wake="abc"), 0),
        ("minutes invalid",   PatternsIn(wake="06:99"), 0),
        ("empty string",      PatternsIn(wake=""), 0),
        ("blank routine",     PatternsIn(routines=[RoutineItem(label="  ", at="06:00")]), 0),
        ("valid, seconds",    PatternsIn(wake="06:30:00"), 1),
        ("only sleep",        PatternsIn(sleep="22:00"), 1),
    ]
    for desc, body, expect in cases:
        try:
            res = set_patterns(uid, body)
            got = res.get("written")
            ok = got == expect
        except Exception as e:
            ok, got = False, f"raised {type(e).__name__}"
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {desc:20} wrote {got}, expected {expect}")

    # a partial submission must not wipe what is already there
    before = len(rows_for(uid))
    set_patterns(uid, PatternsIn(wake="06:30"))
    after = len(rows_for(uid))
    ok = after >= before
    failures += not ok
    print(f"{'ok  ' if ok else 'FAIL'} partial submission preserves the rest "
          f"({before} rows -> {after})")

    print(f"\n{len(cases) + 1 - failures}/{len(cases) + 1} correct")
    return failures


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if "--purge" in sys.argv:
        teardown()
        print("purged")
        return
    try:
        teardown()
        failures = run_coexist()
        failures += run_canon()
        failures += run_idempotent()
        failures += run_drift()
        failures += run_validation()
        failures += run_midnight()
        print("\n" + "=" * 78)
        print("ALL GREEN" if failures == 0 else f"{failures} FAILURE(S)")
        print("=" * 78)
    finally:
        teardown()
        print("\ntorn down")


if __name__ == "__main__":
    main()

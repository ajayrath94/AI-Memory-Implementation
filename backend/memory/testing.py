"""
TESTING — telling probe data apart from real use.

Three sessions created within four minutes during a push test read, for a
while, as runaway session creation in production. They were ours. That is a
cheap mistake to make repeatedly: the dashboard counts synthetic users beside
real ones, the alert engine would happily email a caregiver about a fabricated
decline, and "is this a bug or did we just do that" costs several minutes every
time it comes up.

The mechanism is an environment variable rather than an argument threaded
through every call site. NANCY_TEST is set when running probes locally; the
deployed container never has it, so production cannot accidentally mark itself
as test data. The cost is that it is process-wide — a probe that calls into the
scheduler marks everything that run touches — which is the right trade for
something whose only job is to keep two kinds of data apart.

WHAT FILTERS ON IT
  dashboard      — yes. Synthetic users beside real ones is the problem.
  alert engine   — yes. Nobody should be emailed about a fabricated pattern.
  scheduler      — no. Exercising it against test users is the point.
  observation    — no. Deriving patterns from seeded data is harmless.
"""
import os
from typing import Optional


def is_test_run() -> bool:
    """Whether this process is a probe rather than the live service."""
    return os.getenv("NANCY_TEST", "").strip().lower() in ("1", "true", "yes")


def session_source() -> str:
    return "test" if is_test_run() else "app"


def mark_user_as_test(user_id: str) -> bool:
    """Flag a user as synthetic. Harnesses call this after seeding.

    Separate from the NANCY_TEST variable because the two answer different
    questions: the variable says how this process is running, the flag says
    what this row is. A user seeded by a harness stays test data long after
    that process has exited.
    """
    try:
        from supabase_store import get_client
        get_client().table("user_profile").update(
            {"is_test": True}).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        print(f"[Testing] could not mark {user_id}: {e}")
        return False


def test_user_ids() -> set:
    """Everyone marked synthetic, for excluding from reads."""
    try:
        from supabase_store import get_client
        rows = (get_client().table("user_profile").select("user_id")
                .eq("is_test", True).execute()).data or []
        return {r["user_id"] for r in rows}
    except Exception as e:
        print(f"[Testing] test-user read failed: {e}")
        return set()


def looks_like_test_id(user_id: str) -> bool:
    """Fallback for users seeded before the flag existed.

    The harnesses have always prefixed their users — simtest_, pattest_,
    alerttest_ — which worked as a convention and was never queryable. This
    catches those without a backfill.
    """
    prefixes = ("simtest_", "pattest_", "alerttest_", "sugtest_",
                "cattest", "rectest", "viewtest", "looptest", "distest",
                "statetest", "wraptest", "wkndtest", "tztest_", "sp_",
                "edge_", "segtest", "probe")
    uid = (user_id or "").lower()
    return uid.startswith(prefixes) or uid in ("test_user", "shobha_demo")


def exclude_test(user_ids) -> list:
    """Filter a list of user ids down to real people."""
    marked = test_user_ids()
    return [u for u in user_ids
            if u not in marked and not looks_like_test_id(u)]

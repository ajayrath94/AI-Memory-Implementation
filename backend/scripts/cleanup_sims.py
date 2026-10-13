"""
Remove users left behind by test runs.

    railway run python3 backend/scripts/cleanup_sims.py            # preview
    railway run python3 backend/scripts/cleanup_sims.py --go       # delete
    railway run python3 backend/scripts/cleanup_sims.py --go shobha_test test_user
                                                                   # also these, by name

A test user is letters followed by a ten-digit timestamp: kamala1791635169,
week1791433360, simmeera1791824888. Test scripts make them and delete them at
the end; a run that is killed halfway leaves them behind, and production then
treats them as people. On 13 Oct twenty of them held up the scheduler for an
hour and the real user's breakfast question never went out.

Named users are deleted only when listed explicitly on the command line, and
"default" never.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

PROTECTED = {"default"}
TABLES = ("window_state", "suggestions", "day_events", "subject_mentions",
          "user_behavioral_events", "interest_clusters", "observances",
          "profile_anchors", "user_patterns", "care_schedule", "proactive_events",
          "weather_log", "user_context", "user_memory", "calendar_events",
          "push_tokens", "lists", "list_items")


def main():
    db = get_client()
    go = "--go" in sys.argv
    named = {a for a in sys.argv[1:] if not a.startswith("--")} - PROTECTED

    ids = set()
    for t in ("user_profile", "user_memory"):
        try:
            ids |= {r["user_id"] for r in db.table(t).select("user_id")
                    .limit(5000).execute().data or [] if r.get("user_id")}
        except Exception as e:
            print(f"(cannot list {t}: {str(e)[:80]})")

    sims = sorted(u for u in ids if re.fullmatch(r"[a-z_]+\d{10}", u))
    doomed = sorted((set(sims) | (named & ids)) - PROTECTED)
    print(f"{'DELETING' if go else 'WOULD DELETE'} {len(doomed)}:")
    for u in doomed:
        print("   ", u)
    print("keeping:", sorted(ids - set(doomed)))
    missing = named - ids
    if missing:
        print("not found (ignored):", sorted(missing))
    if not go:
        print("\nPreview only. Add --go to delete.")
        return

    for u in doomed:
        try:
            sess = [s["id"] for s in db.table("sessions").select("id")
                    .eq("user_id", u).execute().data or []]
            for i in range(0, len(sess), 100):
                db.table("messages").delete().in_("session_id", sess[i:i + 100]).execute()
            db.table("sessions").delete().eq("user_id", u).execute()
        except Exception as e:
            print(f"  {u}: sessions: {str(e)[:80]}")
        for t in TABLES:
            try:
                db.table(t).delete().eq("user_id", u).execute()
            except Exception:
                pass                     # a table without user_id, or absent
        try:
            db.table("user_profile").delete().eq("user_id", u).execute()
        except Exception as e:
            print(f"  {u}: profile: {str(e)[:80]}")
        print("  removed", u)
    print(f"\nremoved {len(doomed)}")


if __name__ == "__main__":
    main()

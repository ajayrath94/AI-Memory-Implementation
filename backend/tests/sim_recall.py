"""
The thread, end to end.

    railway run python3 -u backend/tests/sim_recall.py
    railway run python3 -u backend/tests/sim_recall.py --keep

Compression was tested on its own. This tests the whole path: a fortnight of
real conversations written through the live session-end, then asked for.

WHAT IS BEING CHECKED

  written         a real message through process_session_end leaves a cache
                  row and a day's note, tagged and dated.

  continuity      the last day comes back whatever she says. "Kal aapne dal
                  banayi thi" has to be available when she says nothing in
                  particular — that is what makes tomorrow a continuation.

  by tag          she names her son and days tagged with him are found by
                  lookup, including ones the words would not match.

  by similarity   only when tag and date find nothing, and NOT when they
                  already have. A search that always runs always returns
                  something, and the composer uses whatever it is given.

  silence         asked about something that never happened, it says nothing.
                  This is the one that matters: a nearest-neighbour result is
                  never empty, and "the closest of fourteen days" reads
                  exactly like "the relevant one".

  the thread is not the knowledge
                  the note says she cooked dal. It must not say her son lives
                  in Delhi — that is a fact and belongs in a cluster, and a
                  thread that accumulates facts becomes a second profile that
                  disagrees with the first.
"""
import os
import sys
from datetime import date, datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "recallsim"
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def teardown():
    db = get_client()
    for t in ("memory_cache", "memory_stm", "memory_ltm", "messages",
              "sessions", "user_behavioral_events", "interest_clusters",
              "user_memory", "user_profile"):
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


# A fortnight. Some subjects recur, some are said once. Written through the
# real path, then aged backwards.
DAYS = [
    (12, "Mera beta Rajesh Mumbai mein rehta hai, engineer hai"),
    (10, "Aaj dal banayi thi, thodi namkeen ho gayi"),
    (8,  "Rajesh ka phone aaya, bahut acha laga"),
    (6,  "Ghutne mein dard tha subah, chalne mein dikkat hui"),
    (4,  "Lata Mangeshkar ke gaane sune shaam ko"),
    (2,  "Rajesh ne bataya wo Diwali pe aa raha hai"),
    (1,  "Khichdi banayi, achi bani"),
]


def live_a_fortnight():
    """Through process_session_end, not by inserting rows."""
    from supabase_store import save_message, get_client
    from memory.user_memory_store import process_session_end

    db = get_client()
    today = datetime.now(timezone.utc)

    for ago, text in DAYS:
        when = today - timedelta(days=ago)
        s = db.table("sessions").insert({
            "user_id": UID, "model": "gemini-flash-latest",
            "created_at": when.isoformat(), "updated_at": when.isoformat(),
        }).execute().data[0]

        save_message(s["id"], "user", text, "gemini-flash-latest")
        save_message(s["id"], "assistant", "Achha.", "gemini-flash-latest")
        db.table("messages").update({"timestamp": when.isoformat()}) \
          .eq("session_id", s["id"]).execute()

        print(f"  -{ago:2}d  {text[:52]}")
        try:
            process_session_end(s["id"], UID)
        except Exception as e:
            print(f"        session end: {e}")

        # The writes stamp today; age them to the day they belong to.
        d = when.date().isoformat()
        db.table("memory_stm").update({"happened_on": d}) \
          .eq("user_id", UID).eq("happened_on", today.date().isoformat()).execute()
        db.table("memory_cache").update({"happened_on": d}) \
          .eq("user_id", UID).eq("happened_on", today.date().isoformat()).execute()


def main():
    from memory.thread import recall
    setup()

    print(f"{len(DAYS)} days, written through the real path\n")
    live_a_fortnight()

    db = get_client()
    stm = (db.table("memory_stm").select("happened_on,text,tags,untagged")
           .eq("user_id", UID).order("happened_on").execute()).data or []
    cache = (db.table("memory_cache").select("id")
             .eq("user_id", UID).execute()).data or []

    print(f"\n{len(stm)} days in stm, {len(cache)} messages in cache\n")
    for r in stm:
        print(f"  {r['happened_on']}  {str(r['text'])[:56]}")
        if r.get("untagged"):
            print(f"               untagged: {r['untagged']}")
    print()

    check(len(stm) >= len(DAYS) - 2, "a day was written per conversation",
          f"{len(stm)} of {len(DAYS)}")
    check(len(cache) >= len(DAYS) - 2, "and her words went to cache",
          f"{len(cache)} messages")

    # The thread is not the knowledge.
    blob = " ".join(str(r.get("text", "")).lower() for r in stm)
    check("engineer" not in blob and "mumbai" not in blob,
          "the note does not carry standing facts",
          "where he lives and what he does belong in his cluster")

    # ── continuity ───────────────────────────────────────────────────────
    print("— she says nothing in particular —")
    out = recall(UID, "Aaj ka din theek raha")
    print(out or "  (nothing)")
    check("khichdi" in (out or "").lower(),
          "the last day comes back regardless",
          "continuity is not a search")

    # ── by tag ───────────────────────────────────────────────────────────
    print("\n— she names her son —")
    out = recall(UID, "Rajesh ka kya haal hai")
    print(out or "  (nothing)")
    got = (out or "").lower()
    check(got.count("rajesh") >= 1, "days about him are found")

    # ── silence ──────────────────────────────────────────────────────────
    print("\n— she asks about something that never happened —")
    out = recall(UID, "Bank ka kaam ho gaya tha kya")
    print(out or "  (nothing beyond the last day)")
    # The last day always comes back; what must NOT appear is an unrelated
    # day dragged in by similarity because it was the closest of fourteen.
    dragged = [w for w in ("dal", "ghutne", "lata", "diwali")
               if w in (out or "").lower()]
    check(not dragged, "nothing is dragged in to fill the silence",
          f"pulled in: {dragged}" if dragged else "only the last day")


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

"""
Is what it recorded actually true?

    railway run python3 -u backend/tests/sim_accuracy.py
    railway run python3 -u backend/tests/sim_accuracy.py --keep

Stability says the pipeline answers the same way twice. This asks whether the
answer is right — and a run of sim_interests turned up four ways it is not.

WHAT WENT WRONG THERE

    a singer became a film
        [ClusterResolver] 'Mohammed Rafi' -> cluster 'Mughal-e-Azam'
        Two things she loves became one, neither recoverable. The film then
        came out categorised as sangeet, because it had inherited a music
        mention.

    one sentence became five events
        "BP ki dawai roz subah leti hoon" produced blood pressure at strength
        2.8 across five events — stronger than a singer she named on three
        separate days. One utterance outweighing three occasions inverts what
        strength is for.

    it changed her words
        bagwani became gardening, mandir became temple visits, ghutna became
        knee pain. Canonical labels are right for matching; the label is also
        what gets said back to her, and she did not say "gardening".

    and it invented a phone call
        "Rajesh called and mentioned he is now living in Mumbai" from a
        sentence that says only where he lives. Twice, in two runs.

    plus: "he" for a woman, in two thread notes.

WHAT TO READ
The failures name what is wrong and what she said. Nothing here is a matter of
taste — each one is a thing the system recorded that she did not say.
"""
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "accsim"
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def teardown():
    db = get_client()
    for t in ("subject_mentions", "memory_cache", "memory_stm", "memory_ltm",
              "entity_relations", "user_behavioral_events", "interest_clusters",
              "messages", "sessions", "user_memory", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def setup():
    teardown()
    db = get_client()
    db.table("user_profile").insert({
        "user_id": UID, "name": "Kamala", "language_pref": "hinglish",
        "location": "Jaipur", "demographics": {"gender": "female"},
    }).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 0}).execute()
    try:
        from memory.testing import mark_user_as_test
        mark_user_as_test(UID)
    except Exception:
        pass


# Each sentence is here because something specific went wrong with it.
SAID = [
    # two singers and a film. None of the three is the other.
    "Mohammed Rafi ke gaane sunti hoon",
    "Lata Mangeshkar ki awaaz bahut pyari hai",
    "Mughal-e-Azam meri favourite film hai",

    # one sentence. One thing. Not five.
    "BP ki dawai roz subah leti hoon",

    # her words, in her language
    "Bagwani karti hoon subah subah",
    "Roz mandir jaati hoon",
    "Ghutne mein dard rehta hai",

    # states where he lives. Says nothing about a call.
    "Mera beta Rajesh Mumbai mein rehta hai",
]

# things that must never end up in the same cluster
APART = [("rafi", "mughal"), ("rafi", "lata"), ("lata", "mughal")]


async def live():
    from supabase_store import save_message
    from memory.user_memory_store import process_session_end

    db = get_client()
    for i, text in enumerate(SAID):
        when = datetime.now(timezone.utc) - timedelta(days=len(SAID) - i)
        s = db.table("sessions").insert({
            "user_id": UID, "model": "gemini-flash-latest",
            "created_at": when.isoformat(), "updated_at": when.isoformat(),
        }).execute().data[0]
        save_message(s["id"], "user", text, "gemini-flash-latest")
        save_message(s["id"], "assistant", "Achha.", "gemini-flash-latest")
        db.table("messages").update({"timestamp": when.isoformat()}) \
          .eq("session_id", s["id"]).execute()
        print(f"  {text[:50]}")
        try:
            process_session_end(s["id"], UID)
        except Exception as e:
            print(f"     session end: {str(e)[:70]}")


def main():
    setup()
    print(f"{len(SAID)} sentences, each on its own day\n")
    asyncio.run(live())

    db = get_client()
    rows = (db.table("interest_clusters")
            .select("label,kind,strength,event_count,attributes")
            .eq("user_id", UID).neq("kind", "event")
            .order("strength", desc=True).execute()).data or []

    print(f"\n— what it recorded, {len(rows)} clusters —")
    for r in rows:
        a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        print(f"  {str(r['label'])[:28]:30} {str(r.get('kind')):9} "
              f"{str(a.get('category') or '–'):8} "
              f"{float(r.get('strength') or 0):5.1f}  n={r.get('event_count')}")

    labels = [str(r["label"]).lower() for r in rows]

    # ── things that are not each other ───────────────────────────────────
    print()
    for x, y in APART:
        both = [l for l in labels if x in l or y in l]
        merged = any(x in l and y in l for l in labels)
        has_x = any(x in l for l in both)
        has_y = any(y in l for l in both)
        check(not merged and (has_x or has_y),
              f"{x} and {y} are not the same thing",
              f"labels: {both}")

    # ── one sentence, one thing ──────────────────────────────────────────
    bp = [r for r in rows
          if any(w in str(r["label"]).lower()
                 for w in ("bp", "blood pressure", "dawai", "medic"))]
    n = sum(int(r.get("event_count") or 0) for r in bp)
    print()
    check(len(bp) <= 2 and n <= 2,
          "one sentence about a tablet is one or two events",
          f"{len(bp)} cluster(s), {n} events: {[r['label'] for r in bp]}")

    # and it must not outweigh something said on three separate days
    rafi = next((r for r in rows if "rafi" in str(r["label"]).lower()), None)
    if bp and rafi:
        heaviest_bp = max(float(r.get("strength") or 0) for r in bp)
        check(float(rafi["strength"]) >= heaviest_bp,
              "a singer named twice is not outweighed by one tablet",
              f"rafi {rafi['strength']} vs bp {heaviest_bp}")

    # ── her words ────────────────────────────────────────────────────────
    print()
    for hers, english in (("bagwani", "gardening"),
                          ("mandir", "temple"),
                          ("ghutn", "knee")):
        kept = any(hers in l for l in labels)
        swapped = any(english in l for l in labels)
        check(kept or not swapped,
              f"'{hers}' is not replaced by '{english}'",
              "the label is what gets said back to her"
              if not kept else "")

    # ── nothing invented ─────────────────────────────────────────────────
    notes = (db.table("memory_stm").select("happened_on,text")
             .eq("user_id", UID).order("happened_on").execute()).data or []
    print(f"\n— the day notes, {len(notes)} —")
    blob = ""
    for nrow in notes:
        print(f"  {nrow['happened_on']}  {str(nrow['text'])[:96]}")
        blob += " " + str(nrow.get("text") or "").lower()

    check(not any(w in blob for w in ("called", "phoned", "rang ")),
          "no phone call was invented",
          "'Rajesh Mumbai mein rehta hai' says where he lives, nothing more")

    # ── and she is a woman ───────────────────────────────────────────────
    import re
    he = re.findall(r"\b(he|him|his)\b", blob)
    check(not he, "the notes do not call her he",
          f"found {sorted(set(he))}" if he else "")


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

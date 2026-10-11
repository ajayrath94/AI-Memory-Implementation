"""
Does a conversation become an interest?

    railway run python3 -u backend/tests/sim_interests.py
    railway run python3 -u backend/tests/sim_interests.py --keep

Every interest Shobha has came from a setup form. Nine of them, inflated by
repeated test submissions — Shakira at 7.0 without ever being mentioned. The
form path works; what has never been tested end to end is the one that
matters: she says something, and it becomes knowledge.

WHAT THIS CHECKS

    the extractor     does "Lata Mangeshkar ke gaane sunti hoon" produce a
                      cluster labelled Lata Mangeshkar, categorised sangeet,
                      offerable?

    the category      sangeet, khana, dekhna, bhakti, shauk. A wrong one means
                      the thing is offered at the wrong hour, or never.

    what is NOT an interest
                      her knee, her son, her medicine, a place. Those become
                      clusters too, and must carry no category — the picker
                      filters on it, and "aaj ghutne ka dard try kijiye" is
                      the failure this prevents.

    once is not a favourite
                      a single mention should be weak. Strength is evidence,
                      and one sentence is one piece of it.

    repetition
                      the same subject three times should be clearly stronger
                      than one mentioned once — without being a hundred times
                      stronger, which is what the form produced.

    her own words
                      "ghutna" not "knee joint", "Kishore da" not "Kishore
                      Kumar the playback singer". The label is what she would
                      recognise.

WHAT TO READ
The table at the end. Anything with a category is something she can be offered
on a quiet afternoon; anything without is context. A concern with a category is
the failure that reaches her.
"""
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "intsim"
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
        "location": "Jaipur",
    }).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 0}).execute()
    try:
        from memory.testing import mark_user_as_test
        mark_user_as_test(UID)
    except Exception:
        pass


# Ordinary sentences. Nothing here is a form — it is what someone says.
SAID = [
    # ── things she likes, said once ──────────────────────────────────────
    "Lata Mangeshkar ke gaane sunti hoon roz shaam ko",
    "Mughal-e-Azam meri favourite film hai",
    "Bagwani karti hoon subah subah",
    "Roz subah mandir jaati hoon",
    "Rajma chawal bahut pasand hai mujhe",

    # ── something said three times, on different days ────────────────────
    "Aaj phir Mohammed Rafi ke gaane sune",
    "Rafi saab ki awaaz mein kuch alag hi baat hai",
    "Mohammed Rafi ka 'Chaudhvin Ka Chand' sun rahi thi",

    # ── and things that are NOT interests ────────────────────────────────
    "Ghutne mein dard rehta hai aajkal",
    "Mera beta Rajesh Mumbai mein rehta hai",
    "BP ki dawai roz subah leti hoon",
    "Jaipur mein rehti hoon bachpan se",

    # ── a feeling, which is neither ──────────────────────────────────────
    "Aaj bahut akela lag raha hai",
]

# (fragment to find, what it should be, expected category or None)
EXPECT = [
    ("lata",     "interest", "sangeet"),
    ("mughal",   "interest", "dekhna"),
    ("bagwani",  "interest", "shauk"),
    ("mandir",   "interest", "bhakti"),
    ("rajma",    "interest", "khana"),
    ("rafi",     "interest", "sangeet"),
    ("ghutn",    "concern",  None),
    ("knee",     "concern",  None),
    ("rajesh",   "person",   None),
    ("jaipur",   "place",    None),
]


async def live():
    from supabase_store import save_message
    from memory.user_memory_store import process_session_end

    db = get_client()
    for i, text in enumerate(SAID):
        # Each on its own day, so repetition counts as repetition.
        when = datetime.now(timezone.utc) - timedelta(days=len(SAID) - i)
        s = db.table("sessions").insert({
            "user_id": UID, "model": "gemini-flash-latest",
            "created_at": when.isoformat(), "updated_at": when.isoformat(),
        }).execute().data[0]
        save_message(s["id"], "user", text, "gemini-flash-latest")
        save_message(s["id"], "assistant", "Achha.", "gemini-flash-latest")
        db.table("messages").update({"timestamp": when.isoformat()}) \
          .eq("session_id", s["id"]).execute()

        print(f"  {text[:52]}")
        try:
            process_session_end(s["id"], UID)
        except Exception as e:
            print(f"     session end: {str(e)[:70]}")


def main():
    setup()
    print(f"{len(SAID)} things she said, each on its own day\n")
    asyncio.run(live())

    db = get_client()
    rows = (db.table("interest_clusters")
            .select("label,kind,pillar,strength,event_count,attributes")
            .eq("user_id", UID).neq("kind", "event")
            .order("strength", desc=True).execute()).data or []

    print(f"\n— what it knows, {len(rows)} clusters —")
    print(f"  {'label':26} {'kind':10} {'category':10} {'str':>5}  {'n':>3}")
    for r in rows:
        a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        print(f"  {str(r['label'])[:24]:26} {str(r.get('kind')):10} "
              f"{str(a.get('category') or '–'):10} "
              f"{float(r.get('strength') or 0):5.1f}  {r.get('event_count'):>3}")

    def find(frag):
        for r in rows:
            if frag in str(r["label"]).lower():
                a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
                return r, a
        return None, {}

    print()
    for frag, want_kind, want_cat in EXPECT:
        r, a = find(frag)
        if not r:
            # knee may be stored as ghutna or knee pain — one of the two is
            # enough, so a missing alias is not a failure on its own.
            if frag in ("knee",):
                continue
            check(False, f"{frag} became a cluster")
            continue
        got_cat = a.get("category")
        if want_cat:
            check(got_cat == want_cat,
                  f"{str(r['label'])[:20]} is {want_cat}",
                  f"got {got_cat or 'none'}")
        else:
            check(not got_cat,
                  f"{str(r['label'])[:20]} is never offered",
                  f"kind={r.get('kind')} category={got_cat or 'none'}")

    # ── offerable, and what is not ───────────────────────────────────────
    offerable = [r["label"] for r in rows
                 if (r.get("attributes") or {}).get("category")]
    print(f"\n  offerable: {', '.join(offerable) or 'nothing'}")

    bad = [r["label"] for r in rows
           if (r.get("attributes") or {}).get("category")
           and str(r.get("kind")) in ("concern", "person", "place")]
    check(not bad, "nothing that should be silent is offerable",
          f"{bad}" if bad else "her knee, her son and Jaipur carry no category")

    # ── three mentions beat one ──────────────────────────────────────────
    rafi, _ = find("rafi")
    lata, _ = find("lata")
    if rafi and lata:
        rs, ls = float(rafi["strength"]), float(lata["strength"])
        print(f"\n  Rafi (said 3 times): {rs:.1f}   Lata (said once): {ls:.1f}")
        check(rs > ls, "three mentions outweigh one")
        check(rs < ls * 6, "but not by an order of magnitude",
              "the setup form put Shakira at 7.0 on seven re-saves")

    # ── a feeling is not a thing she likes ───────────────────────────────
    lonely = [r["label"] for r in rows
              if any(w in str(r["label"]).lower()
                     for w in ("akela", "lonely", "alone"))]
    check(not lonely, "a feeling did not become a cluster",
          f"{lonely}" if lonely else "'akela lag raha hai' is a day, not a fact")

    # ── and her words ────────────────────────────────────────────────────
    print("\n  labels, as stored:")
    for r in rows[:8]:
        print(f"    {r['label']}")


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

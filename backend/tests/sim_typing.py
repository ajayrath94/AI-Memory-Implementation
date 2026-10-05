"""
Thirty things she might say, and what each should become.

    railway run python3 -u backend/tests/sim_typing.py
    railway run python3 -u backend/tests/sim_typing.py --keep

Every artist she ever mentioned became a person. Lata Mangeshkar extracted
cleanly as entity_type=artist, and a rule meant to catch "Rajesh lives_in
Mumbai" — where the entity type describes the object, so he came out as a
place — saw a subject_ref that was not self or a pronoun and made her a
person. The picker filters those out.

So conversation could never produce an offerable artist. Four offerable things
from a fortnight of talking, and the only offerable singer came from the setup
form.

It was a missing word in one tuple, and nothing would have caught it except a
test that covers every kind of thing she might name.

WHAT A CATEGORY DECIDES
Everything downstream. A cluster with no category is never offered; one with
the wrong category is offered at the wrong hour — a dish at nine at night, a
film at breakfast. And a concern with a category is the failure that reaches
her: "aaj ghutne ka dard try kijiye".

    sangeet   singers, musicians, kinds of music
    dekhna    films, serials, things watched
    khana     dishes, cuisines, things eaten
    shauk     what she does with her hands and her time
    bhakti    temple, puja, fasting, faith
    NONE      her people, her body, her places, her money, her feelings

THE ASYMMETRY
A thing wrongly given no category is merely never offered. A concern wrongly
given one is offered to her as an afternoon's entertainment. So the failures
are not equal, and the ones that matter are marked.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = f"typesim{int(time.time())}"
_fails, _serious = [], []


def check(ok, label, detail="", serious=False):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)
        if serious:
            _serious.append(label)


# (what she said, the fragment to look for, expected kind, expected category)
# None as a category means it must carry none — those are the ones that would
# otherwise be offered to her.
SAID = [
    # ── music ────────────────────────────────────────────────────────────
    ("Lata Mangeshkar ke gaane sunti hoon", "lata", "interest", "sangeet"),
    ("Rafi saab ki awaaz bahut acchi hai", "rafi", "interest", "sangeet"),
    ("Ghazal sunna pasand hai mujhe", "ghazal", "interest", "sangeet"),
    ("Bhajan roz subah lagati hoon", "bhajan", "interest", None),

    # ── watching ─────────────────────────────────────────────────────────
    ("Mughal-e-Azam meri favourite film hai", "mughal", "interest", "dekhna"),
    ("Ramayan serial dekhti thi roz", "ramayan", "interest", "dekhna"),
    ("Amitabh ki filmein acchi lagti hain", "amitabh", "interest", "dekhna"),

    # ── eating ───────────────────────────────────────────────────────────
    ("Rajma chawal bahut pasand hai", "rajma", "interest", "khana"),
    ("South Indian khana acha lagta hai", "south indian", "interest", "khana"),
    ("Aam ka achar khud banati hoon", "achar", "interest", "khana"),

    # ── doing ────────────────────────────────────────────────────────────
    ("Bagwani karti hoon subah subah", "bagwani", "interest", "shauk"),
    ("Sweater bunti hoon sardiyon mein", "sweater", "interest", "shauk"),
    ("Crossword solve karti hoon roz", "crossword", "interest", "shauk"),

    # ── faith ────────────────────────────────────────────────────────────
    ("Roz subah mandir jaati hoon", "mandir", "interest", "bhakti"),
    ("Mangalvar ko vrat rakhti hoon", "vrat", "interest", "bhakti"),

    # ── and everything that must NEVER be offered ────────────────────────
    ("Mera beta Rajesh Mumbai mein rehta hai", "rajesh", "person", None),
    ("Padosan Sunita ji roz aati hain", "sunita", "person", None),
    ("Devar ji ka phone aaya tha", "devar", "person", None),
    ("Ghutne mein dard rehta hai", "ghutn", "concern", None),
    ("BP ki dawai roz leti hoon", "bp", "concern", None),
    ("Shugar ki report aayi hai", "shugar", "concern", None),
    ("Jaipur mein rehti hoon bachpan se", "jaipur", None, None),
    ("Pension kam pad jaati hai mahine mein", "pension", None, None),
    ("Aaj bahut akela lag raha hai", "akela", None, None),
    ("Bahut thak gayi hoon aaj", "thak", None, None),
]

# Which of those must never carry a category, however they are typed.
NEVER_OFFERED = ("rajesh", "sunita", "devar", "ghutn", "bp", "shugar",
                 "jaipur", "pension", "akela", "thak")


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
    db = get_client()
    db.table("user_profile").upsert({
        "user_id": UID, "name": "Kamala", "language_pref": "hinglish",
        "location": "Jaipur", "home_location": "Jaipur",
    }).execute()
    db.table("user_memory").upsert({"user_id": UID,
                                    "session_count": 0}).execute()


def main():
    from supabase_store import save_message
    from memory.user_memory_store import process_session_end

    setup()
    db = get_client()
    print(f"{len(SAID)} things she might say\n")

    for text, _frag, _k, _c in SAID:
        s = db.table("sessions").insert({
            "user_id": UID, "model": "gemini-flash-latest"}).execute().data[0]
        save_message(s["id"], "user", text, "gemini-flash-latest")
        save_message(s["id"], "assistant", "Achha.", "gemini-flash-latest")
        try:
            process_session_end(s["id"], UID)
        except Exception as e:
            print(f"  {text[:40]:42} session end failed: {str(e)[:50]}")

    rows = (db.table("interest_clusters")
            .select("label,kind,attributes").eq("user_id", UID)
            .neq("kind", "event").execute()).data or []

    print(f"\n— {len(rows)} clusters —")
    for r in sorted(rows, key=lambda x: str(x["label"]).lower()):
        a = r.get("attributes") or {}
        print(f"  {str(r['label'])[:26]:28} {str(r.get('kind')):9} "
              f"{a.get('category') or '–'}")

    def find(frag):
        for r in rows:
            if frag in str(r["label"]).lower():
                a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
                return r, a
        return None, {}

    print()
    for text, frag, want_kind, want_cat in SAID:
        r, a = find(frag)
        if not r:
            # Not everything has to become a cluster — a feeling should not.
            if want_kind is None:
                check(True, f"{frag} is not a cluster at all")
            else:
                check(False, f"{frag} became a cluster", text[:46])
            continue

        got_cat = a.get("category")
        if want_cat:
            check(got_cat == want_cat,
                  f"{str(r['label'])[:18]} is {want_cat}",
                  f"got {got_cat or 'none'} (kind={r.get('kind')})")
        elif frag in NEVER_OFFERED:
            check(not got_cat,
                  f"{str(r['label'])[:18]} is never offered",
                  f"kind={r.get('kind')} category={got_cat}",
                  serious=True)

    # ── the summary that matters ─────────────────────────────────────────
    offerable = [(str(r["label"]), (r.get("attributes") or {}).get("category"))
                 for r in rows if (r.get("attributes") or {}).get("category")]
    print(f"\n  offerable ({len(offerable)}):")
    for lbl, cat in sorted(offerable, key=lambda x: x[1] or ""):
        print(f"    {cat:9} {lbl}")

    bad = [lbl for lbl, _ in offerable
           if any(n in lbl.lower() for n in NEVER_OFFERED)]
    check(not bad, "nothing that should be silent is offerable",
          f"{bad}" if bad else "her people, her body, her money, her feelings",
          serious=True)

    by_cat = {}
    for _lbl, cat in offerable:
        by_cat[cat] = by_cat.get(cat, 0) + 1
    print(f"\n  by category: {by_cat}")
    check(len(by_cat) >= 4, "she has things to be offered across the week",
          f"only {len(by_cat)} categories — an afternoon can only be music")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        crashed = None
        try:
            main()
        except Exception as e:
            crashed = e
        finally:
            print("\n" + "=" * 68)
            if crashed:
                import traceback
                print("CRASHED:")
                traceback.print_exception(type(crashed), crashed, crashed.__traceback__)
            elif _fails:
                print(f"{len(_fails)} FAILURE(S)"
                      + (f", {len(_serious)} SERIOUS" if _serious else ""))
                for f in _fails:
                    print(("   !! " if f in _serious else "   -  ") + f)
            else:
                print("ALL GREEN")
            print("=" * 68)
            if "--keep" not in sys.argv:
                teardown()
                print("torn down")

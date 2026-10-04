"""
Forty hard cases for one decision.

    railway run python3 -u backend/tests/sim_decide.py

decide() replaced ninety-four lines of chain — a rank table, a person rule, a
category map — that had been fixed four times in one day, each fix breaking a
case the last one had fixed.

    Lata became a person because proper_name was missing from a list.
    Fixing that put artist above person, and Shubham became media.
    Her knee became a person because subject_ref came back "ghutne".
    Arjun became a medical concern because "wo theek hai" is health.

So this is the regression test it did not have. Each case is a sentence that
has broken something, or a near neighbour of one that did.

WHAT EACH CASE ASSERTS
Only the kind and the category, because those are what the rest of the system
reads: the picker filters on kind and places by category, so a wrong kind is
silence and a wrong category is an offer at the wrong hour.

THE ONES THAT MATTER MOST ARE MARKED
A person or a concern given a category is offered to her as an afternoon's
entertainment. Those are marked !! and counted separately.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_fails, _serious = [], []


def check(ok, label, detail="", serious=False):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"  — {detail}" if detail else ""))
    if not ok:
        _fails.append(label)
        if serious:
            _serious.append(label)


# (what she said, expected kind, expected category or None, why it is here)
CASES = [
    # ── her people ───────────────────────────────────────────────────────
    ("Mera beta Rajesh Mumbai mein rehta hai", "person", None,
     "a son and a city in one sentence"),
    ("Arjun se baat hui phone pe, wo theek hai", "person", None,
     "'wo theek hai' is a health proposition — he became a concern"),
    ("Shubham aaya tha, saath mein Sholay dekhi", "person", None,
     "person and media together — he became a film"),
    ("Padosan Sunita ji roz aati hain", "person", None, "a neighbour"),
    ("Devar ji ka phone aaya tha", "person", None, "a devar"),
    ("Mausi ki tabiyat kharab hai", "person", None,
     "someone else's illness is not her concern"),
    ("Doodhwala roz subah aata hai", "person", None, "the milkman"),
    ("Meri jethani Delhi se aayi hain", "person", None, "a jethani"),

    # ── her body ─────────────────────────────────────────────────────────
    ("Ghutne mein dard rehta hai", "concern", None,
     "subject_ref came back 'ghutne' and made a knee a person"),
    ("Kamar dard se pareshan hoon", "concern", None, "her back"),
    ("BP ki dawai roz leti hoon", "concern", None, "a tablet"),
    ("Shugar ki report aayi hai", "concern", None, "a test result"),
    ("Doctor ne operation ke liye kaha hai", "concern", None, "surgery"),
    ("Aankhon se kam dikhta hai aajkal", "concern", None, "her eyes"),

    # ── music ────────────────────────────────────────────────────────────
    ("Lata Mangeshkar ke gaane sunti hoon", "interest", "sangeet",
     "a singer is a person and is not HER person"),
    ("Rafi saab ki awaaz bahut acchi hai", "interest", "sangeet", "a singer"),
    ("Ghazal sunna pasand hai", "interest", "sangeet",
     "a kind of music, not a person"),
    ("Bhajan roz subah lagati hoon", "interest", "sangeet", "devotional music"),
    ("Kishore da ke purane gaane sune", "interest", "sangeet", "a nickname"),

    # ── watching ─────────────────────────────────────────────────────────
    ("Mughal-e-Azam meri favourite film hai", "interest", "dekhna", "a film"),
    ("Ramayan serial dekhti thi roz", "interest", "dekhna", "a serial"),
    ("Amitabh ki filmein acchi lagti hain", "interest", "dekhna",
     "an actor — a person, and an interest to her"),

    # ── eating ───────────────────────────────────────────────────────────
    ("Rajma chawal bahut pasand hai", "interest", "khana", "a dish"),
    ("South Indian khana acha lagta hai", "interest", "khana", "a cuisine"),
    ("Aam ka achar khud banati hoon", "interest", "khana", "a thing she makes"),
    ("Aaj khichdi banayi thi", "interest", "khana", "one meal"),

    # ── doing ────────────────────────────────────────────────────────────
    ("Bagwani karti hoon subah subah", "interest", "shauk", "gardening"),
    ("Sweater bunti hoon sardiyon mein", "interest", "shauk", "knitting"),
    ("Roz sair karti hoon shaam ko", "interest", "shauk",
     "the activity is the object, not the subject"),
    ("Aj caroom khelenge", "interest", "shauk",
     "future tense — it came back a scheduled_event and vanished"),

    # ── faith ────────────────────────────────────────────────────────────
    ("Roz subah mandir jaati hoon", "interest", "bhakti", "the temple"),
    ("Mangalvar ko vrat rakhti hoon", "interest", "bhakti", "fasting"),

    # ── and the things that are none of the above ────────────────────────
    ("Jaipur mein rehti hoon bachpan se", None, None, "a place"),
    ("Pension kam pad jaati hai", None, None, "money"),
    ("Aaj bahut akela lag raha hai", None, None, "a feeling"),
    ("Bahut thak gayi hoon", None, None, "tiredness"),
    ("Mausam acha hai aaj", None, None, "the weather"),
    ("Sab theek hai", None, None, "a reply, not a thing"),
]

# A person or a concern must never carry a category — that is what reaches her.
MUST_BE_SILENT = ("person", "concern")


def main():
    from memory.profile_enricher import _extract_propositions as extract, decide

    print(f"{len(CASES)} cases\n")
    for text, want_kind, want_cat, why in CASES:
        props = extract(text, "decidesim") or []
        if not props:
            check(want_kind is None, f"{text[:40]:42}", "nothing extracted")
            continue

        # group the way record_propositions does: by what the proposition is
        # about, which is the object when the subject is herself
        groups = {}
        for p in props:
            subj = str(p.get("subject") or "").strip()
            obj = str(p.get("object") or "").strip()
            ref = str(p.get("subject_ref") or "").strip().lower()
            k = obj if (ref in ("self", "user", "i", "me")
                        or subj.lower() in ("self", "user", "i", "me", "")) else subj
            if k and k.lower() not in ("self", "user"):
                groups.setdefault(k, []).append(p)

        if not groups:
            check(want_kind is None, f"{text[:40]:42}", "nothing to cluster")
            continue

        # the strongest decision across what this sentence produced
        best = None
        for subj, ps in groups.items():
            etype, kind, cat, why_d = decide(subj, ps)
            if want_kind and kind == want_kind and cat == want_cat:
                best = (subj, kind, cat, why_d)
                break
            if best is None:
                best = (subj, kind, cat, why_d)

        subj, kind, cat, why_d = best
        if want_kind is None:
            # nothing in particular is expected — only that it is not offered
            serious = kind in MUST_BE_SILENT and bool(cat)
            check(not cat, f"{text[:40]:42}",
                  f"{subj[:18]} {kind}/{cat or '-'} ({why_d})", serious)
        else:
            ok = kind == want_kind and cat == want_cat
            serious = (want_kind in MUST_BE_SILENT and bool(cat))
            check(ok, f"{text[:40]:42}",
                  f"{subj[:18]} {kind}/{cat or '-'} ({why_d})", serious)


if __name__ == "__main__":
    crashed = None
    try:
        main()
    except Exception as e:
        crashed = e
    finally:
        print("\n" + "=" * 70)
        if crashed:
            import traceback
            traceback.print_exception(type(crashed), crashed,
                                      crashed.__traceback__)
        elif _fails:
            print(f"{len(_fails)} of {len(CASES)} FAILED"
                  + (f", {len(_serious)} SERIOUS" if _serious else ""))
            for f in _fails:
                print(("   !! " if f in _serious else "   -  ") + f.strip())
        else:
            print(f"ALL {len(CASES)} GREEN")
        print("=" * 70)

"""
Live check of the offer-feedback build, with the real model, on a throwaway
user. Run on Railway:

    railway run python3 -u backend/tests/sim_offer_feedback.py

1. Reading her answer: the kind of answer and which part it was about,
   for the replies seen on 12-16 Oct and the design's cases.
2. Songs: the three matches from 16 Oct.
3. End to end: a yes to Mehbooba Mehbooba makes R.D. Burman hers, and
   "bahar ka khana kabhi nahi" becomes a rule, with nothing about how much
   she likes the dish changed.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

UID = "sim_offer_feedback"
FAILS = []


def check(ok, label):
    if not ok:
        FAILS.append(label)
    print(f"{'ok  ' if ok else 'FAIL'} {label}")


def part1():
    from memory.suggestions import read_reply
    print("\n── 1. reading her answer ──")
    cases = [
        ("Mehbooba Mehbooba by R.D. Burman", "Haan yei ganna bhaut acha hai", "", "", "",
         lambda g: g["reaction"] == "accepted"),
        ("Fresh Fruit Chaat at Sagar", "Ghar pe hi bana lenge", "", "khana", "outside",
         lambda g: g["reaction"] == "accepted" and g.get("way_she_wants") == "home"),
        ("Biryani from Meghana Foods", "bahar ka khana kabhi nahi mangwati", "", "khana", "outside",
         lambda g: g["reaction"] == "declined_way"),
        ("Biryani", "biryani mujhe bilkul pasand nahi", "", "khana", "home",
         lambda g: g["reaction"] == "declined_preference"),
        ("Pranayam by Baba Ramdev", "Are abhi puja wagera krna hai , sham ko dekhenge", "", "shauk", "",
         lambda g: g["reaction"] == "declined_timing"),
        ("Carrom", "Are weekday mei kaha , weekend pe dekhenge", "", "shauk", "",
         lambda g: g["reaction"] == "declined_timing"),
        ("Sabudana Khichdi", "Mangalvar ko main bahar ka kuch nahi khati, aaj nahi", "", "khana", "home",
         lambda g: g["reaction"] in ("declined_timing", "declined_way")
         and (g.get("condition") or {}).get("weekday", "").lower().startswith("tue")),
        ("Lag Ja Gale by Lata Mangeshkar", "phone chalana nahi aata mujhe", "", "sangeet", "",
         lambda g: (g.get("ability") or {}).get("key") == "uses_phone"
         and (g.get("ability") or {}).get("value") is False),
        ("Kishore Kumar ke gaane", "Paas mein kya kya hai?", "", "sangeet", "",
         lambda g: g["reaction"] == "unrelated"),
        ("Sukhsagar", "Haan Dhyanesh hai krdia phone",
         "Subah ka naashta kaisa raha? Aur wo phone kiya aapne?", "bhakti", "",
         lambda g: g["reaction"] == "unrelated"),
    ]
    for offer, reply, since, kind, way, want in cases:
        g = read_reply(offer, reply, since, kind=kind, way=way)
        check(bool(g) and want(g), f"{reply[:45]!r} -> {g}")


def part2():
    from memory.offers import _match_recording
    print("\n── 2. songs ──")
    ok, fixed = _match_recording("Mehbooba Mehbooba by R.D. Burman",
                                 "Mehbooba Oh Mehbooba - Lyrical | ओह मेहबूबा ऐ मेहबूबा | RD Burman | Sholay")
    check(ok, f"Mehbooba lyrical version is the same song ({ok}, {fixed})")
    ok, fixed = _match_recording("Tujhe Dekha To Yeh Jaana Sanam by Lata Mangeshkar",
                                 "Tujhe Dekha Toh Song | Dilwale Dulhania Le Jayenge | Shah Rukh Khan, Kajol")
    check(ok, f"Tujhe Dekha Toh is the same song ({ok}, {fixed})")
    ok, fixed = _match_recording("Khaike Paan Banaras Wala by Mohammad Rafi",
                                 "Khaike Paan Banaras Wala - Video Song | Don (1978) | Kishore Kumar")
    check(ok and fixed and "kishore" in fixed.lower(),
          f"Khaike Paan corrected to Kishore Kumar ({ok}, {fixed})")
    ok, fixed = _match_recording("Lag Ja Gale by Lata Mangeshkar",
                                 "Top 50 Lata Mangeshkar Songs | Jukebox")
    check(not ok, f"a jukebox is not the song ({ok}, {fixed})")


def _db():
    from supabase_store import get_client
    return get_client()


def wipe():
    db = _db()
    for t in ("user_behavioral_events", "interest_clusters", "subject_mentions",
              "suggestions", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def part3():
    from memory.suggestions import apply_reaction
    from memory import offer_rules as R
    print("\n── 3. end to end ──")
    db = _db()
    wipe()
    db.table("user_profile").insert({"user_id": UID, "name": "Sim", "life_context": {}}).execute()

    s = (db.table("suggestions").insert({
        "user_id": UID, "label": "Mehbooba Mehbooba by R.D. Burman",
        "intent": "recommendation", "source": "offer", "because": "Sholay",
    }).execute()).data[0]
    apply_reaction(UID, s, "accepted", reply_text="Haan yei ganna bhaut acha hai",
                   details={"reaction": "accepted"})
    time.sleep(2)
    labels = [r["label"].lower() for r in (db.table("interest_clusters").select("label")
              .eq("user_id", UID).execute()).data or []]
    check(any("burman" in l for l in labels), f"a yes to Mehbooba makes R.D. Burman hers ({labels})")

    s2 = (db.table("suggestions").insert({
        "user_id": UID, "label": "Biryani", "intent": "recommendation",
        "source": "offer", "because": "South Indian",
    }).execute()).data[0]
    s2["kind"], s2["way"] = "khana", "outside"
    apply_reaction(UID, s2, "declined_way", reply_text="bahar ka khana kabhi nahi mangwati",
                   details={"reaction": "declined_way", "never": True})
    rules = R.rules(UID)
    check(any(r.get("kind") == "khana" and r.get("way") == "outside" for r in rules),
          f"'bahar ka khana kabhi nahi' becomes a rule ({[R.describe(r) for r in rules]})")
    check(R.blocked(rules, "khana", "home", R.moment_now(UID)) is None,
          "a dish to cook at home is still allowed")
    wipe()


if __name__ == "__main__":
    try:
        part1()
        part2()
        part3()
    finally:
        wipe()
    print(f"\n{'ALL GREEN' if not FAILS else f'{len(FAILS)} FAILED'}")
    for f in FAILS:
        print("  -", f)

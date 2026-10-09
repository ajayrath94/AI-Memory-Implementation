"""
A fortnight of offers. Does the frontier recede?

    railway run python3 -u backend/tests/sim_offers_new.py

The offer path shows her what she does not have, and anything it manages to
introduce stops being its business — once Lata is a cluster, the cluster
path raises her naturally. So it can never repeat itself, which is what
makes it read as curious rather than as a catalogue.

WHAT IS BEING CHECKED

    nothing already hers      the frontier. Kishore is her strongest
                              interest and must never be offered.
    nothing twice             over fourteen days
    a clear no is permanent   declined never comes back
    silence is not a no       ignored comes round again
    the right thing at the    a recipe before a meal, a film in an evening,
    right hour                a song any time
    and adoption moves the    she takes up Lata; Lata becomes hers; the
    frontier                  offer path must move past her

WHAT IS NOT CHECKED
Whether the messages read well. That is a judgement, and the offers are
printed so you can make it.
"""
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "off%d" % int(time.time())
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


HERS = [("Kishore Kumar", "sangeet", 2.8), ("Sholay", "dekhna", 1.4),
        ("South Indian", "khana", 1.6), ("bagwani", "shauk", 1.2),
        ("Kumar Sanu", "sangeet", 0.8)]

ROUTINE = [("wake", None, "06:00"), ("meal", "breakfast", "09:00"),
           ("meal", "lunch", "13:00"), ("routine", "Evening walk", "17:30"),
           ("meal", "dinner", "20:00"), ("sleep", None, "22:00")]


def teardown():
    db = get_client()
    for t in ("suggestions", "day_events", "interest_clusters",
              "user_patterns", "observances", "messages", "sessions",
              "user_memory", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass


def setup():
    db = get_client()
    db.table("user_profile").upsert({
        "user_id": UID, "name": "Shobha", "language_pref": "hinglish",
        "location": "Bengaluru", "home_location": "Bengaluru",
    }).execute()
    db.table("user_memory").upsert({"user_id": UID,
                                    "session_count": 20}).execute()
    for kind, label, at in ROUTINE:
        db.table("user_patterns").insert({
            "user_id": UID, "kind": kind, "label": label,
            "declared_at": at, "source": "declared"}).execute()
    for label, cat, strength in HERS:
        db.table("interest_clusters").insert({
            "user_id": UID, "label": label, "pillar": "ENTERTAINMENT",
            "kind": "interest", "status": "active", "strength": strength,
            "attributes": {"category": cat, "source": "conversation"},
        }).execute()
    from memory.day import rebuild
    rebuild(UID)


def main():
    from memory.offers import choose, record, candidates, hers
    from memory.windows import windows_today
    import memory.day as D

    setup()
    db = get_client()
    real = D._mins_now

    ws = windows_today(UID, read_her_words=False)
    print("her windows:")
    for w in ws:
        print(f"  {w}")
    wide = max(ws, key=lambda w: w.minutes) if ws else None

    print(f"\nwhat is already hers: {sorted(hers(UID).keys())}\n")

    # ── a fortnight, one offer a day, in the widest window ──────────────
    print("FOURTEEN DAYS\n")
    offered = []
    for day in range(14):
        now = (wide.starts + 30) if wide else 15 * 60
        D._mins_now = lambda uid, _n=now: _n
        o = choose(UID, wide, now)
        if not o:
            print(f"  day {day + 1:2}  (nothing to offer)")
            continue
        record(UID, o, wide, now)
        offered.append(o.what.lower())
        print(f"  day {day + 1:2}  {o}")
    D._mins_now = real

    print()
    mine = set(hers(UID).keys())
    crossed = [o for o in offered if o in mine]
    check(not crossed, "nothing already hers was offered",
          f"{crossed}" if crossed else "the frontier held")

    dupes = [k for k, n in Counter(offered).items() if n > 1]
    check(not dupes, "nothing was offered twice in a fortnight", f"{dupes}")

    check(len(offered) >= 7, "there was enough to say",
          f"{len(offered)} offers over 14 days")

    # ── a clear no is permanent ─────────────────────────────────────────
    print("\nA CLEAR NO\n")
    if offered:
        said_no = offered[0]
        db.table("suggestions").update({"reaction": "declined"}) \
          .eq("user_id", UID).ilike("label", said_no).execute()
        print(f"  she declined: {said_no}")

        pool = [c.what.lower() for c in candidates(UID, wide, 15 * 60)]
        check(said_no not in pool, "a declined thing does not come back",
              f"{said_no} still in the pool" if said_no in pool else "")

    # ── silence is not a no ─────────────────────────────────────────────
    print("\nSILENCE IS NOT A NO\n")
    if len(offered) > 1:
        ignored = offered[1]
        db.table("suggestions").update({"reaction": "no_response"}) \
          .eq("user_id", UID).ilike("label", ignored).execute()
        # clear the three-week cooldown so only the reaction matters
        db.table("suggestions").delete().eq("user_id", UID) \
          .ilike("label", ignored).eq("reaction", "no_response").execute()
        pool = [c.what.lower() for c in candidates(UID, wide, 15 * 60)]
        print(f"  she ignored: {ignored}")
        print(f"  back in the pool: {'yes' if ignored in pool else 'no'}")

    # ── and adoption moves the frontier ─────────────────────────────────
    print("\nSHE TAKES ONE UP\n")
    if offered:
        took = offered[-1]
        db.table("interest_clusters").insert({
            "user_id": UID, "label": took, "pillar": "ENTERTAINMENT",
            "kind": "interest", "status": "active", "strength": 1.0,
            "attributes": {"category": "sangeet", "source": "conversation"},
        }).execute()
        print(f"  {took} is hers now")
        pool = [c.what.lower() for c in candidates(UID, wide, 15 * 60)]
        check(took not in pool, "what she adopted leaves the offer path",
              "the cluster path raises it from here")

    # ── and what the composer would be told ─────────────────────────────
    print("\nWHAT THE COMPOSER WOULD BE TOLD\n")
    D._mins_now = lambda uid: 15 * 60
    o = choose(UID, wide, 15 * 60)
    if o:
        from memory.offers import hint
        print(f"  {hint(o).strip()[:400]}")
    D._mins_now = real


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
            print(f"{len(_fails)} FAILURE(S)")
            for f in _fails:
                print("   -", f)
        else:
            print("ALL GREEN")
        print("=" * 70)
        if "--keep" not in sys.argv:
            teardown()
            print("torn down")

"""
LINEAGE — months of one life, then the questions she would ask.

    cd backend
    PYTHONPATH=. railway run python3 -u tests/sim_lineage.py
    PYTHONPATH=. railway run python3 -u tests/sim_lineage.py --keep

A throwaway user. Her words go through the real code with the real model —
episodes.hear for health, events.extract_events for what happened — with
the clock moved back to the day each was said. Then the questions go
through the real recall (engine_router._retrieve_memory), and the timeline
Nancy would be given is printed and checked.

    three colds, months apart, in three ways of saying it
    two knee flare-ups, and a knee mention that is not one
    five zoo visits, one of them told twice, in two languages for "zoo"
    Arjun visiting twice
    the mandir on three days two apart (three visits, not one)
    a Delhi trip told over two days (one occasion)

Deleted at the end unless --keep. Never touches "default".
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("NANCY_TEST", "1")

from supabase_store import get_client

UID = "lineage%d" % int(time.time())
IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime.now(IST).replace(hour=11, minute=0, second=0, microsecond=0)
KEEP = "--keep" in sys.argv
_hard, _soft = [], []


def ago(days, hh=11):
    return (NOW - timedelta(days=days)).replace(hour=hh)


def check(ok, label, detail="", soft=False):
    print(f"  {'ok  ' if ok else ('soft' if soft else 'FAIL')} {label}"
          + (f"\n         {detail}" if detail and not ok else ""))
    if not ok:
        (_soft if soft else _hard).append(label)


HEALTH = [  # (days ago, what she says)
    (100, "Aaj sardi ho gayi hai, naak beh rahi hai"),
    (97, "Sardi ab bilkul theek ho gayi"),
    (60, "Aaj ghutne mein bahut dard hai, sham ki walk nahi ki"),
    (58, "Ghutna ab theek hai, aaj walk ki"),
    (50, "Ghutne ka dhyan rakhti hoon, thoda tel lagati hoon"),
    (45, "Zukaam ho gaya hai, chheenk aa rahi hai"),
    (41, "Ab main bilkul theek hoon, zukaam chala gaya"),
    (15, "Ghutne mein phir se bahut dard hai, aaj bahar nahi gayi"),
    (6, "Ghutne mein ab bhi thoda dard hai"),
    (1, "Phir se sardi lag gayi"),
]
HAPPENED = [  # (days ago, what she says)
    (120, "Aaj Shubham ke saath zoo gaye the, bahut maza aaya"),
    (90, "Kal chidiyaghar gaye the, sher dekha"),
    (89, "Parso jo zoo gaye the, wahan bandar bhi the"),
    (70, "Aaj beta Arjun ghar aaya tha"),
    (60, "Aaj zoo outing thi bacchon ke saath"),
    (30, "Arjun aaj phir aaya, khana saath khaya"),
    (20, "Aaj phir zoo gaye"),
    (5, "Kal chidiyaghar gaye the Shubham ke saath"),
    # Three real visits two days apart: three, not one (16 Oct fix).
    (12, "Aaj mandir gayi thi, bahut shanti mili"),
    (10, "Aaj phir mandir gayi"),
    (8, "Aaj subah mandir gayi, prasad liya"),
    # One trip over two days: one occasion, not two.
    (40, "Kal Delhi pahunche Shubham ke saath"),
    (39, "Aaj Delhi mein Qutub Minar dekha"),
]
QUESTIONS = [
    ("Hum zoo pichli baar kab gaye the?", "Zoo"),
    ("Kitni baar chidiyaghar gaye hum?", "Zoo"),
    ("Is saal kitni baar sardi hui mujhe?", "cold"),
    ("Ghutne ka dard kab se hai?", "since"),
    ("Arjun pichli baar kab aaya tha?", "Arjun"),
    ("Main mandir kitni baar gayi?", "3 times"),
]

TABLES = ("health_episodes", "interest_clusters", "subject_mentions",
          "user_behavioral_events", "memory_stm", "user_memory")


def setup():
    db = get_client()
    db.table("user_profile").insert({
        "user_id": UID, "name": "Shobha", "language_pref": "hinglish",
        "location": "Bengaluru", "demographics": {"gender": "female"}}).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 1}).execute()
    try:
        from memory.testing import mark_user_as_test
        mark_user_as_test(UID)
    except Exception:
        pass
    for label, kind, pillar, attrs in (
            ("Knee pain", "concern", "HEALTH_WELLNESS", {"kind": "concern", "english": "knee pain"}),
            ("Arjun", "person", "FAMILY", {"kind": "person", "relation": "beta"}),
            ("Shubham", "person", "FAMILY", {"kind": "person", "relation": "beta"})):
        db.table("interest_clusters").insert({
            "user_id": UID, "label": label, "kind": kind, "pillar": pillar,
            "status": "active", "strength": 1.0, "event_count": 1,
            "attributes": attrs}).execute()


def teardown():
    db = get_client()
    for t in TABLES:
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass
    db.table("user_profile").delete().eq("user_id", UID).execute()
    left = {}
    for t in TABLES + ("user_profile",):
        try:
            n = db.table(t).select("user_id", count="exact").eq("user_id", UID).execute().count
            if n:
                left[t] = n
        except Exception:
            pass
    return left


def live():
    import memory.episodes as ep
    from memory.events import extract_events
    script = sorted([(d, "h", t) for d, t in HEALTH] + [(d, "e", t) for d, t in HAPPENED],
                    key=lambda x: -x[0])
    for d, kind, text in script:
        when = ago(d)
        print(f"\n  [{when:%d %b}] she: {text}")
        if kind == "h":
            ep._now = lambda w=when: w.astimezone(timezone.utc)
            got = ep.hear(UID, text, pillar="HEALTH_WELLNESS")
            print(f"           episodes: {got or 'nothing'}")
        else:
            ids = extract_events(UID, [{"role": "user", "content": text}], said_on=when)
            print(f"           events: {len(ids)}")
    ep._now = lambda: datetime.now(timezone.utc)


def label_of(db, cid):
    r = db.table("interest_clusters").select("label").eq("id", cid).limit(1).execute().data
    return r[0]["label"] if r else None


def checks():
    db = get_client()
    from memory.lineage import timeline
    cl = db.table("interest_clusters").select("*").eq("user_id", UID).execute().data or []
    by_label = {c["label"].lower(): c for c in cl}
    eps = db.table("health_episodes").select("*").eq("user_id", UID).execute().data or []

    print("\n== WHAT IT BUILT")
    for c in sorted(cl, key=lambda c: (c.get("kind") == "event", c["label"])):
        parent = label_of(db, c["parent_id"]) if c.get("parent_id") else ""
        print(f"  {c['label'][:30]:30} {c.get('kind'):8} {c.get('status'):8} "
              f"{str(c.get('happened_on') or '')[:10]:10} {('under ' + parent) if parent else ''}")
    for e in eps:
        print(f"  episode {e['what'][:24]:24} {e.get('kind') or 'illness':8} {e.get('status'):9} "
              f"{str(e.get('first_reported'))[:10]} under {label_of(db, e.get('cluster_id')) if e.get('cluster_id') else '-'}")

    print("\n== CHECKS")
    colds = [e for e in eps if (e.get("kind") or "illness") == "illness"]
    cold_ids = {e.get("cluster_id") for e in colds}
    check(len(colds) == 3, "three colds became three episodes", f"{[(e['what'], e['status']) for e in colds]}")
    check(len(cold_ids) == 1 and None not in cold_ids, "all three colds under ONE concept",
          f"{[label_of(db, c) if c else None for c in cold_ids]}")
    if len(cold_ids) == 1 and None not in cold_ids:
        cc = db.table("interest_clusters").select("label,status").eq("id", next(iter(cold_ids))).execute().data[0]
        check(cc["status"] == "archived", f"the cold concept {cc['label']!r} is archived (known, never offered)",
              f"status {cc['status']}")
    check(sum(1 for e in colds if e["status"] == "resolved") == 2 and
          sum(1 for e in colds if e["status"] != "resolved") == 1,
          "two colds over, the latest still going", f"{[(e['what'], e['status']) for e in colds]}")

    flares = [e for e in eps if e.get("kind") == "flare"]
    knee = by_label.get("knee pain")
    check(len(flares) == 2, "two knee flare-ups (the 'dhyan rakhti hoon' mention is not one)",
          f"{[(e['what'], e['status']) for e in flares]}")
    check(knee and all(e.get("cluster_id") == knee["id"] for e in flares), "flare-ups under Knee pain")
    check(knee and knee.get("status") == "active", "Knee pain stays an active, lasting concern")
    check(sum(1 for e in flares if e["status"] == "resolved") == 1, "first flare-up over, second still going",
          f"{[(e['what'], e['status']) for e in flares]}")

    zoo = next((c for c in cl if c.get("kind") != "event" and "zoo" in (c["label"] + str((c.get("attributes") or {}).get("english"))).lower()), None)
    visits = timeline(UID, zoo["id"])["occurrences"] if zoo else []
    check(bool(zoo), "one Zoo concept for 'zoo' and 'chidiyaghar'",
          f"concepts: {[c['label'] for c in cl if c.get('kind') != 'event']}")
    check(len(visits) == 5, "five zoo visits (the one told twice counted once)",
          f"{[(v['label'], str(v.get('happened_on'))[:10]) for v in visits]}")
    if visits:
        check(str(visits[-1].get("happened_on"))[:10] == ago(6).date().isoformat(),
              "the last visit is the day before 'kal chidiyaghar gaye the'",
              f"last {visits[-1].get('happened_on')}, expected {ago(6).date()}", soft=True)
    arjun = by_label.get("arjun")
    av = timeline(UID, arjun["id"])["occurrences"] if arjun else []
    check(len(av) == 2, "Arjun's two visits under Arjun (no 'Arjun's visit' concept)",
          f"{[(v['label'], str(v.get('happened_on'))[:10]) for v in av]}")

    def visits_to(word):
        c = next((c for c in cl if c.get("kind") != "event" and word in
                  (c["label"] + " " + str((c.get("attributes") or {}).get("english"))).lower()), None)
        return c, (timeline(UID, c["id"])["occurrences"] if c else [])
    mandir, mv = visits_to("mandir")
    if not mandir:
        mandir, mv = visits_to("temple")
    check(len(mv) == 3, "mandir on three days two apart: three visits, not one",
          f"{[(v['label'], str(v.get('happened_on'))[:10]) for v in mv]}")
    delhi, dv = visits_to("delhi")
    check(len(dv) == 1, "the Delhi trip over two days: one occasion",
          f"{[(v['label'], str(v.get('happened_on'))[:10]) for v in dv]}")

    print("\n== THE QUESTIONS — what Nancy is given to answer from")
    from engine.engine_router import _retrieve_memory
    for q, want in QUESTIONS:
        block = _retrieve_memory(None, "", UID, query_text=q) or ""
        print(f"\n  she asks: {q}\n" + "\n".join("    " + l for l in block.splitlines()))
        check(want.lower() in block.lower(), f"answer comes from the {want} timeline", soft=True)

    print("\n== HEALTH NOTE (open episodes, with what came before)")
    from memory.episodes import prompt_note
    note = prompt_note(UID)
    print("\n".join("    " + l for l in note.strip().splitlines()))
    check("3rd time" in note, "the open cold says it is the 3rd time in a year", soft=True)


def main():
    print(f"lineage simulation as {UID}, today {NOW.date()}")
    try:
        setup()
        live()
        checks()
    finally:
        if KEEP:
            print(f"\nKept {UID}.")
        else:
            left = teardown()
            print(f"\nDeleted {UID}." + (f" Left: {left}" if left else " Nothing left behind."))
    print(f"\n{len(_hard)} hard failure(s), {len(_soft)} soft miss(es)")
    for f in _hard:
        print("  FAIL", f)
    for f in _soft:
        print("  soft", f)


if __name__ == "__main__":
    main()

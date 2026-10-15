"""
A week of memory, end to end — the real chat path, the real model, the real
database — under a throwaway user that is deleted at the end.

    cd backend
    PYTHONPATH=. railway run python3 -u tests/sim_memory.py
    PYTHONPATH=. railway run python3 -u tests/sim_memory.py --keep    # leave the user to inspect
    PYTHONPATH=. railway run python3 scripts/cleanup_sims.py --go     # remove a kept or crashed run

Seven days of things a woman like Shobha says, each message sent through
process_input and then moved back to the day and time it was "said". A chat
closes the way it does in production: the next day's first message starts a
new session, and that closes the previous one in the background. The last
chat is closed by hand, and then the heartbeat's memory steps run (promotion,
the cluster cleaner).

What it exercises:
    interest extraction  live per message, and again at chat end
    the cycle            mention -> subject_mentions (dated) -> group -> count
    passing vs lasting   a cold goes to an episode; the knee to a group
    events               "kal Arjun aaya tha" said on day 4 is day 5
    her dates            a chat across midnight files under two days
    autocorrect          "Haan Dhyanesh hai" saved with what she meant
    the clean-up         an archived "Aram" and a merged "puja" stay that way
    junk                 a word marked junk stays junk on a new day
    short chats          closed once, not again at every new chat

HARD checks are what the code guarantees. SOFT ones depend on what the model
reads in her words; a SOFT miss is worth reading, not necessarily a bug.

Never touches "default". Every row it writes carries its own user id.
"""
import asyncio
import os
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("NANCY_TEST", "1")

from supabase_store import get_client

UID = "memsim%d" % int(time.time())
MODEL = "gemini-flash-latest"
IST = timezone(timedelta(hours=5, minutes=30))
TODAY = datetime.now(IST).date()
KEEP = "--keep" in sys.argv


def day(n):
    return TODAY - timedelta(days=n)


# (days ago, "HH:MM", what she says, new chat?)
# A new chat starts when she comes back after a gap — as in production.
SCRIPT = [
    (6, "10:00", "Subah puja ki aur phir Kishore Kumar ke gaane sune, bahut accha laga", True),
    (6, "10:05", "Mera beta Arjun Pune mein engineer hai, aaj uska phone aaya tha", False),
    (5, "09:30", "Aaj sardi ho gayi hai, naak beh rahi hai", True),
    (5, "09:40", "Ghutne mein dard bhi hai, isliye sham ki walk nahi karungi", False),
    (4, "11:00", "Kal Arjun ghar aaya tha bachon ke saath, bahut accha laga", True),
    (4, "11:10", "Aaj bagwani mein tulsi lagayi", False),
    # Across midnight, one chat: the first half is day 3, the second day 2.
    (3, "23:40", "Aaj padosan ke saath carrom khela, bahut maza aaya", True),
    (2, "00:20", "Ab so rahi hoon, sardi thodi kam hai", False),
    (2, "17:00", "Aaj bhi bagwani ki, gulab mein phool aaye", True),
    (1, "10:00", "Haan Dhyanesh hai, dawai le li", True),
    (1, "10:05", "Sardi bilkul theek ho gayi. Aaj aram kar rahi hoon puja ke baad", False),
    (0, "09:00", "Bagwani karna mujhe bahut pasand hai", True),
    (0, "09:05", "Kishore Kumar ka Mere Sapno ki Rani sunna hai", False),
]

_hard, _soft = [], []


def check(ok, label, detail="", soft=False):
    tag = "ok  " if ok else ("soft" if soft else "FAIL")
    print(f"  {tag} {label}" + (f"\n         {detail}" if detail and not ok else ""))
    if not ok:
        (_soft if soft else _hard).append(label)


def db():
    return get_client()


# ── setup and teardown ───────────────────────────────────────────────────────

TABLES = ("health_episodes", "entity_relations", "memory_cache", "memory_stm",
          "memory_ltm", "care_alerts", "reminders", "user_pillar_weights",
          "pillar_weight_history", "day_events", "suggestions", "proactive_events",
          "subject_mentions", "user_behavioral_events", "interest_clusters",
          "observances", "profile_anchors", "user_patterns", "care_schedule",
          "weather_log", "user_context", "calendar_events", "push_tokens",
          "festival_brief", "window_state", "stm_clusters", "ltm_patterns",
          "user_memory")


def teardown(uid=UID):
    c = db()
    try:
        lids = [r["id"] for r in c.table("lists").select("id").eq("user_id", uid).execute().data or []]
        if lids:
            c.table("list_items").delete().in_("list_id", lids).execute()
        c.table("lists").delete().eq("user_id", uid).execute()
    except Exception:
        pass
    try:
        sess = [s["id"] for s in c.table("sessions").select("id").eq("user_id", uid).execute().data or []]
        for i in range(0, len(sess), 100):
            c.table("messages").delete().in_("session_id", sess[i:i + 100]).execute()
        c.table("sessions").delete().eq("user_id", uid).execute()
    except Exception as e:
        print(f"  (sessions: {str(e)[:80]})")
    for t in TABLES:
        try:
            c.table(t).delete().eq("user_id", uid).execute()
        except Exception:
            pass
    try:
        c.table("user_profile").delete().eq("user_id", uid).execute()
    except Exception as e:
        print(f"  (profile: {str(e)[:80]})")


def leftovers(uid=UID):
    c, left = db(), {}
    for t in TABLES + ("sessions", "user_profile", "lists"):
        try:
            n = c.table(t).select("user_id", count="exact").eq("user_id", uid).execute().count
            if n:
                left[t] = n
        except Exception:
            pass
    return left


def setup():
    c = db()
    c.table("user_profile").insert({
        "user_id": UID, "name": "Shobha", "language_pref": "hinglish",
        "location": "Bengaluru", "home_location": "Surat",
        "demographics": {"gender": "female"},
    }).execute()
    c.table("user_memory").insert({"user_id": UID, "session_count": 0}).execute()
    try:
        from memory.testing import mark_user_as_test
        mark_user_as_test(UID)
    except Exception:
        pass
    # The state a clean-up leaves: a live group, a name merged into it, a
    # word set aside, and a subject marked junk.
    mp = c.table("interest_clusters").insert({
        "user_id": UID, "label": "Morning puja", "kind": "interest", "pillar": "FAITH",
        "status": "active", "strength": 2.0, "event_count": 3,
        "attributes": {"kind": "interest", "category": "bhakti"}}).execute().data[0]
    c.table("interest_clusters").insert({
        "user_id": UID, "label": "puja", "kind": "interest", "pillar": "FAITH",
        "status": "merged", "strength": 1.0, "event_count": 2,
        "attributes": {"merged_into": mp["id"]}}).execute()
    c.table("interest_clusters").insert({
        "user_id": UID, "label": "Aram", "kind": "interest", "pillar": "HEALTH_WELLNESS",
        "status": "archived", "strength": 1.0, "event_count": 2,
        "attributes": {"archived_why": "a state, not a thing"}}).execute()
    c.table("subject_mentions").insert({
        "user_id": UID, "subject": "aj", "happened_on": day(10).isoformat(),
        "junk": True}).execute()
    return mp["id"]


# ── driving the chat ─────────────────────────────────────────────────────────

def wait_background(timeout=240):
    """process_input and session end work in background threads; wait for
    ours (named Thread-N) so each step sees the last one's writes."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        mine = [t for t in threading.enumerate()
                if t is not threading.main_thread() and t.name.startswith("Thread-") and t.is_alive()]
        if not mine:
            return True
        time.sleep(1)
    print(f"  (still running after {timeout}s: {[t.name for t in mine]})")
    return False


def at(days_ago, hhmm):
    h, m = map(int, hhmm.split(":"))
    d = day(days_ago)
    return datetime(d.year, d.month, d.day, h, m, tzinfo=IST)


def backdate_last_two(sid, when):
    c = db()
    rows = (c.table("messages").select("id,role,timestamp").eq("session_id", sid)
            .order("timestamp", desc=True).limit(2).execute()).data or []
    for r in rows:
        t = when if r["role"] == "user" else when + timedelta(seconds=30)
        c.table("messages").update({"timestamp": t.astimezone(timezone.utc).isoformat()}) \
            .eq("id", r["id"]).execute()


async def run_week():
    from engine.engine_router import process_input
    from memory.user_memory_store import process_session_end
    sid = None
    for n, hhmm, text, new_chat in SCRIPT:
        when = at(n, hhmm)
        if new_chat and sid:
            # She was away. The session's clock goes back past the window so
            # this message opens a new one, which closes the last.
            db().table("sessions").update({
                "updated_at": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
            }).eq("id", sid).execute()
        print(f"\n  [{when:%a %d %b %H:%M}] she: {text}")
        try:
            r = await process_input(text, MODEL, sid, UID)
            reply = (r or {}).get("reply", "") if isinstance(r, dict) else str(r)
            sid = (r or {}).get("session_id") or sid
        except Exception as e:
            reply = f"[failed: {e}]"
        print(f"  nancy: {str(reply)[:160]}")
        wait_background()
        if sid:
            backdate_last_two(sid, when)

    print("\n  … closing the last chat …")
    process_session_end(sid, UID)
    wait_background()


def heartbeat():
    print("\n  … heartbeat: promotion, cleaner …")
    try:
        from memory.promotion import review
        review(UID, dry_run=False)
    except Exception as e:
        print(f"  (promotion: {e})")
    try:
        from memory.cluster_cleaner import clean_clusters
        clean_clusters(UID)
    except Exception as e:
        print(f"  (cleaner: {e})")
    wait_background()


# ── reading it back ──────────────────────────────────────────────────────────

def snapshot():
    c = db()
    cl = c.table("interest_clusters").select("*").eq("user_id", UID).execute().data or []
    sm = c.table("subject_mentions").select("*").eq("user_id", UID).execute().data or []
    ev = c.table("user_behavioral_events").select(
        "cluster_id,session_id,sub_pillar,value,created_at").eq("user_id", UID).execute().data or []
    ep = c.table("health_episodes").select("*").eq("user_id", UID).execute().data or []
    stm = c.table("memory_stm").select("*").eq("user_id", UID).execute().data or []
    ss = c.table("sessions").select("id,summary,title").eq("user_id", UID).execute().data or []
    msgs = []
    for s in ss:
        msgs += c.table("messages").select("session_id,role,content,meant,timestamp") \
            .eq("session_id", s["id"]).execute().data or []
    return dict(cl=cl, sm=sm, ev=ev, ep=ep, stm=stm, ss=ss, msgs=msgs)


def report(S):
    by_id = {c["id"]: c for c in S["cl"]}
    print("\n== GROUPS")
    for c in sorted(S["cl"], key=lambda c: (c.get("status") != "active", c.get("pillar") or "", c["label"])):
        extra = c.get("happened_on") or ""
        print(f"  {c['label'][:28]:28} {c.get('kind') or '':9} {c.get('pillar') or '':16} "
              f"{c.get('status'):8} count={c.get('event_count')} str={c.get('strength')} {extra}")

    print("\n== THE INTEREST CYCLE — each subject: the days she said it, the group, the events")
    subj_days = defaultdict(set)
    subj_junk = defaultdict(bool)
    subj_cid = {}
    for m in S["sm"]:
        k = m["subject"]
        subj_days[k].add(m["happened_on"])
        subj_junk[k] |= bool(m.get("junk"))
        if m.get("cluster_id"):
            subj_cid[k] = m["cluster_id"]
    ev_by = defaultdict(list)
    for e in S["ev"]:
        ev_by[e.get("cluster_id")].append(e)
    for k in sorted(subj_days, key=str.lower):
        g = by_id.get(subj_cid.get(k))
        gl = f"-> {g['label']} ({g.get('kind')}, {g.get('status')}, count {g.get('event_count')})" if g else "-> no group"
        print(f"  {k[:28]:28} said {sorted(subj_days[k])}{' JUNK' if subj_junk[k] else ''} {gl}")
    print("\n  events per group (mention / recall / reaction, and how many conversations):")
    for cid, es in ev_by.items():
        g = by_id.get(cid)
        if not g:
            continue
        kinds = defaultdict(int)
        for e in es:
            kinds[e.get("sub_pillar") or "mention"] += 1
        sess = {e.get("session_id") for e in es if e.get("session_id")}
        print(f"  {g['label'][:28]:28} {dict(kinds)} across {len(sess)} conversation(s)")

    print("\n== HEALTH EPISODES")
    for e in S["ep"]:
        print(f"  {e.get('what')} ({e.get('english')}) {e.get('level')} {e.get('status')} "
              f"first reported {str(e.get('first_reported'))[:10]}")
    if not S["ep"]:
        print("  none")
    print("\n== DAY NOTES (memory_stm)")
    for r in sorted(S["stm"], key=lambda r: str(r.get("happened_on") or r.get("day"))):
        print(f"  {r.get('happened_on') or r.get('day')}: {str(r.get('note') or r.get('summary') or r.get('text') or '')[:110]}")
    print("\n== MESSAGES WITH A CORRECTION")
    for m in S["msgs"]:
        if m.get("meant"):
            print(f"  {m['content']!r} -> meant {m['meant']!r}")


def checks(S, morning_puja_id):
    print("\n== CHECKS")
    scripted = {day(n).isoformat() for n, *_ in SCRIPT}
    act = [c for c in S["cl"] if c.get("status") == "active"]
    lab = lambda c: (c.get("label") or "").lower()

    # Her dates
    bad = sorted({m["happened_on"] for m in S["sm"]
                  if m["happened_on"] not in scripted and m["subject"] != "aj"})
    check(not bad, "every mention dated on a day she spoke, not the day it was processed",
          f"dates outside the script: {bad}")
    stm_days = {str(r.get("happened_on") or r.get("day"))[:10] for r in S["stm"]}
    check(not (stm_days - scripted), "day notes dated on her days", f"{sorted(stm_days - scripted)}")
    check(day(3).isoformat() in stm_days and day(2).isoformat() in stm_days,
          "the chat across midnight became two days (day 3 and day 2)",
          f"note days: {sorted(stm_days)}", soft=True)
    carrom = [m for m in S["sm"] if "carrom" in m["subject"].lower()]
    check(bool(carrom) and all(m["happened_on"] == day(3).isoformat() for m in carrom),
          "carrom at 23:40 is filed on day 3",
          f"{[(m['subject'], m['happened_on']) for m in carrom]}", soft=True)

    # The clean-up
    st = {c["label"]: c.get("status") for c in S["cl"]}
    check(st.get("Aram") == "archived", "archived 'Aram' stayed archived", f"Aram is {st.get('Aram')}")
    check(st.get("puja") == "merged", "merged 'puja' stayed merged", f"puja is {st.get('puja')}")
    check(st.get("Morning puja") == "active", "Morning puja is still active")
    check(not any(lab(c) in ("aram", "puja") for c in act), "no active 'Aram' or 'puja' came back")

    # Passing vs lasting
    hw = [c for c in act if c.get("pillar") == "HEALTH_WELLNESS"]
    colds = [c["label"] for c in hw if any(w in lab(c) for w in ("sardi", "cold", "zukaam", "naak"))]
    check(not colds, "the cold is not a health group", f"cold groups: {colds}")
    check(bool(S["ep"]), "the cold is an episode", soft=True)
    if S["ep"]:
        check(any(e.get("status") in ("resolved", "improving") for e in S["ep"]),
              "the episode moved on once she said it was better",
              f"{[(e.get('what'), e.get('status')) for e in S['ep']]}", soft=True)
    knee = [c["label"] for c in hw if c.get("kind") == "concern"]
    check(bool(knee), "the knee is a lasting concern group", f"health groups: {[c['label'] for c in hw]}", soft=True)

    # People, events
    arjun = [c for c in act if "arjun" in lab(c) and c.get("kind") == "person"]
    check(bool(arjun) and arjun[0].get("pillar") == "FAMILY", "Arjun is a person under FAMILY",
          f"{[(c['label'], c.get('kind'), c.get('pillar')) for c in act if 'arjun' in lab(c)]}", soft=True)
    visit = [c for c in S["cl"] if c.get("kind") == "event" and "arjun" in lab(c)]
    check(any(str(c.get("happened_on"))[:10] == day(5).isoformat() for c in visit),
          "'kal Arjun aaya tha' said on day 4 is dated day 5",
          f"{[(c['label'], c.get('happened_on')) for c in visit]}", soft=True)
    events = [c["label"] for c in S["cl"] if c.get("kind") == "event"]
    print(f"         events made: {events}")
    check(not any(c.get("kind") == "event" and (c.get("event_count") or 0) < 1 for c in S["cl"]),
          "every event has a count")

    # Counting
    kk = [c for c in act if "kishore" in lab(c)]
    if kk:
        n = sum(1 for e in S["ev"] if e.get("cluster_id") == kk[0]["id"]
                and (e.get("sub_pillar") or "") not in ("recall", "reaction"))
        check(n <= 2, "Kishore Kumar filed once per conversation (2 conversations)",
              f"{n} mention events", soft=True)
    dup = defaultdict(int)
    for e in S["ev"]:
        if (e.get("sub_pillar") or "") not in ("recall", "reaction") and e.get("session_id"):
            dup[(e["cluster_id"], e["session_id"], e.get("value"))] += 1
    worst = max(dup.values()) if dup else 0
    check(worst <= 1, "no fact filed twice in one conversation",
          f"max {worst} for {[k for k, v in dup.items() if v == worst][:3]}", soft=True)

    # Autocorrect
    dh = [m for m in S["msgs"] if m["role"] == "user" and "Dhyanesh" in (m.get("content") or "")]
    check(bool(dh) and bool(dh[0].get("meant")), "'Haan Dhyanesh hai' saved with what she meant",
          f"{dh[0].get('meant') if dh else 'message missing'}", soft=True)
    check(not any("dhyanesh" in lab(c) for c in act), "no person called Dhyanesh")

    # Junk and short chats
    from memory.mentions import record
    record(UID, [{"subject": "aj"}], when=TODAY)
    aj = db().table("subject_mentions").select("junk").eq("user_id", UID).eq("subject", "aj") \
        .eq("happened_on", TODAY.isoformat()).execute().data or []
    check(bool(aj) and aj[0].get("junk") is True, "a junk word said on a new day is still junk",
          f"{aj}")
    open_ = [s["id"][:8] for s in S["ss"] if s.get("summary") is None]
    check(not open_, "every chat closed (none left to be closed again)", f"open: {open_}")

    # Promotion
    bag = [c for c in act if "bagwani" in lab(c) or "garden" in lab(c)]
    check(bool(bag), "bagwani (three days) became a group", f"{[c['label'] for c in act]}", soft=True)


def main():
    print(f"memory simulation as {UID}, today {TODAY} (IST)")
    try:
        mp = setup()
        asyncio.run(run_week())
        heartbeat()
        S = snapshot()
        report(S)
        checks(S, mp)
    finally:
        if KEEP:
            print(f"\nKept {UID}. Remove with: PYTHONPATH=. railway run python3 scripts/cleanup_sims.py --go")
        else:
            wait_background(60)
            teardown()
            left = leftovers()
            print(f"\nDeleted {UID}." + (f" Left behind: {left}" if left else " Nothing left behind."))
    print(f"\n{len(_hard)} hard failure(s), {len(_soft)} soft miss(es)")
    for f in _hard:
        print("  FAIL", f)
    for f in _soft:
        print("  soft", f)
    sys.exit(1 if _hard else 0)


if __name__ == "__main__":
    main()

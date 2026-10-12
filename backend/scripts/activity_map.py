"""
Where her activities are recorded, and what trends they can already support.

    railway run python3 -u backend/scripts/activity_map.py default

Read only. For each place an activity can land, prints how many rows, the
date span, a sample, and how they fall across weekdays. Then runs the trend
functions that already exist on that data. The question it answers: is there
enough, in the right shape, to say "she walks most evenings", "chicken on
Sundays", "sabudana during Navratri"?
"""
import os
import sys
from collections import Counter
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = sys.argv[1] if len(sys.argv) > 1 else "default"
db = get_client()
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _d(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except Exception:
        try:
            return date.fromisoformat(str(v)[:10])
        except Exception:
            return None


def rows(table, cols, date_col=None, extra=None, limit=3000):
    try:
        q = db.table(table).select(cols).eq("user_id", UID)
        if extra:
            q = extra(q)
        if date_col:
            q = q.order(date_col, desc=True)
        return q.limit(limit).execute().data or []
    except Exception as e:
        print(f"   (cannot read {table}: {str(e)[:100]})")
        return None


def span(rs, col):
    ds = sorted(d for d in (_d(r.get(col)) for r in rs) if d)
    if not ds:
        return "no dates"
    days = len({d for d in ds})
    return f"{ds[0]} → {ds[-1]}  ({days} distinct days)"


def weekdays(rs, col):
    c = Counter(_d(r.get(col)).weekday() for r in rs if _d(r.get(col)))
    return "  ".join(f"{DAYS[i]} {c.get(i, 0)}" for i in range(7))


def head(title):
    print("\n" + "=" * 74 + f"\n{title}\n" + "=" * 74)


# ── 1. interest clusters: what she likes and does, with strength ─────────────
head("1. interest_clusters  — durable things: interests, people, routines, events")
cl = rows("interest_clusters",
          "id,label,kind,status,strength,event_count,current_state,last_event,attributes,created_at",
          "strength", lambda q: q.eq("status", "active"))
if cl is not None:
    k = Counter(r.get("kind") or "?" for r in cl)
    print(f"   {len(cl)} active  by kind: {dict(k)}")
    cats = Counter((r.get("attributes") or {}).get("category") or "-"
                   for r in cl if r.get("kind") == "interest")
    print(f"   interests by category: {dict(cats)}")
    print(f"   created: {span(cl, 'created_at')}")
    print(f"   last_event set on {sum(1 for r in cl if r.get('last_event'))} of {len(cl)}")
    print("   strongest 15:")
    for r in cl[:15]:
        a = r.get("attributes") or {}
        st = r.get("current_state")
        print(f"     {str(r['label'])[:30]:30} {str(r.get('kind')):9} "
              f"{str(a.get('category') or '-'):8} str {float(r.get('strength') or 0):5.2f}  "
              f"events {r.get('event_count') or 0:<3} feeling "
              f"{('%+.2f' % st) if st is not None else '  -  '}  last {str(r.get('last_event') or '-')[:10]}")
    ev = [r for r in cl if r.get("kind") == "event"]
    if ev:
        print(f"   events (dated moments), latest 8:")
        for r in sorted(ev, key=lambda r: str(r.get("last_event") or r.get("created_at")), reverse=True)[:8]:
            print(f"     {str(r.get('last_event') or r.get('created_at'))[:10]}  {r['label'][:60]}")

# ── 2. subject mentions: every subject, with the day ────────────────────────
head("2. subject_mentions  — every subject she raised, by day (feeds leanings, gone-quiet)")
sm = rows("subject_mentions", "subject,cluster_id,happened_on", "happened_on")
if sm is not None:
    print(f"   {len(sm)} mentions   {span(sm, 'happened_on')}")
    print(f"   by weekday: {weekdays(sm, 'happened_on')}")
    top = Counter(str(r.get("subject") or "").lower() for r in sm).most_common(20)
    print("   most mentioned (subject × times, and on how many distinct days):")
    by_days = {}
    for r in sm:
        by_days.setdefault(str(r.get("subject") or "").lower(), set()).add(str(r.get("happened_on"))[:10])
    for s, n in top:
        print(f"     {s[:34]:34} {n:3}×  on {len(by_days.get(s, ()))} days")
    linked = sum(1 for r in sm if r.get("cluster_id"))
    print(f"   linked to a cluster: {linked} of {len(sm)}")

# ── 3. behavioural events: the raw signal behind each cluster ───────────────
head("3. user_behavioral_events  — raw observations, including offer reactions")
be = rows("user_behavioral_events",
          "cluster_id,value,event_type,source,sentiment,created_at", "created_at")
if be is not None:
    print(f"   {len(be)} events   {span(be, 'created_at')}")
    print(f"   by source: {dict(Counter(r.get('source') or '-' for r in be))}")
    print(f"   by type (top 10): {dict(Counter(r.get('event_type') or '-' for r in be).most_common(10))}")
    print(f"   by weekday: {weekdays(be, 'created_at')}")
    hours = Counter(datetime.fromisoformat(str(r['created_at']).replace('Z', '+00:00')).hour
                    for r in be if r.get('created_at'))
    print("   by hour (UTC): " + " ".join(f"{h}:{hours.get(h,0)}" for h in range(24) if hours.get(h)))

# ── 4. the day, as it happened ──────────────────────────────────────────────
head("4. day_events  — each meal and routine per day, and whether it happened")
de = rows("day_events", "date,kind,label,due_at,status,note", "date")
if de is not None:
    print(f"   {len(de)} rows   {span(de, 'date')}")
    by = {}
    for r in de:
        by.setdefault((r.get("kind"), r.get("label")), Counter())[r.get("status") or "-"] += 1
    for (k, l), c in sorted(by.items(), key=lambda x: -sum(x[1].values()))[:12]:
        print(f"     {str(k):8} {str(l)[:26]:26} {dict(c)}")
    notes = [r for r in de if (r.get("note") or "").strip()]
    print(f"   with a note of what she said: {len(notes)}")
    for r in notes[:6]:
        print(f"     {r['date']} {r['label']}: {r['note'][:70]}")

# ── 5. offers and what she said back ────────────────────────────────────────
head("5. suggestions  — offers and her reactions")
sg = rows("suggestions", "label,reaction,offered_hour,intent,created_at", "created_at")
if sg is not None:
    print(f"   {len(sg)} offers   {span(sg, 'created_at')}")
    print(f"   reactions: {dict(Counter(r.get('reaction') or 'open' for r in sg))}")
    hrs = Counter((r.get("offered_hour"), r.get("reaction")) for r in sg if r.get("offered_hour") is not None)
    print(f"   (hour, reaction): {dict(hrs.most_common(10))}")

# ── 6. the daily thread note ────────────────────────────────────────────────
head("6. the day's note  — memory.thread, written at session end")
try:
    from memory.thread import recent_days
    th = recent_days(UID, 14) or []
    print(f"   {len(th)} recent days")
    for r in th[:5]:
        print(f"     {str(r.get('happened_on'))[:10]}  {str(r.get('text') or '')[:110]}")
except Exception as e:
    print(f"   (cannot read: {e})")

# ── 7. anchors: stated facts with dates ─────────────────────────────────────
head("7. anchors  — stated facts (e.g. no meat on Tuesdays)")
try:
    from memory.anchors import current
    for key in ("avoids_meat_on", "fasts_on", "wakes_at", "walks_at"):
        try:
            print(f"   {key:16} {current(UID, key)}")
        except Exception as e:
            print(f"   {key:16} (error: {str(e)[:60]})")
except Exception as e:
    print(f"   (cannot import anchors: {e})")

# ── 8. the trends that can be computed today ────────────────────────────────
head("8. TRENDS from the data above")
try:
    from memory.leanings import leanings, gone_quiet
    for i, dname in enumerate(DAYS):
        from datetime import timedelta
        d = date.today() + timedelta(days=(i - date.today().weekday()) % 7)
        lean = leanings(UID, d)
        if lean:
            print(f"   {dname} leans to: {dict(sorted(lean.items(), key=lambda x: -x[1])[:5])}")
    gq = gone_quiet(UID)
    print(f"   gone quiet: {[(g['subject'], g['silent_days']) for g in gq[:5]] or 'nothing'}")
except Exception as e:
    print(f"   leanings failed: {e}")
try:
    from memory.topics import declining
    print(f"   enjoying less: {[d.get('subject') for d in (declining(UID) or [])][:5] or 'nothing'}")
except Exception as e:
    print(f"   declining failed: {e}")
try:
    from memory.affinity import describe
    for m in (6 * 60, 10 * 60, 13 * 60, 16 * 60, 19 * 60, 22 * 60):
        print(f"   {describe(UID, m)}")
except Exception as e:
    print(f"   affinity failed: {e}")
try:
    from memory.festival_brief import for_user
    print(f"   festival now: {for_user(UID)}")
except Exception as e:
    print(f"   festival failed: {e}")
print()

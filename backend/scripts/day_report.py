"""
What did her day actually look like? Read-only.

    railway run python3 -u backend/scripts/day_report.py USER_ID [YYYY-MM-DD]

One timeline for one day, in her time: every message she and Nancy sent,
every engine decision (sent, held and why), every offer and how her reply
was read. Then the problems worth looking at:

  - a meal follow-up from her schedule that never went out
  - a medicine dose with no reminder, or one sent more than 15 minutes early
  - a long stretch of daytime with nothing sent while she was quiet
  - holds that lasted for hours
  - the same message from her several times in a row
  - offers and their reactions

Written after 16 Oct, when a gate held everything from 07:02 to 14:28 and
nothing showed it. Engine decisions appear here once proactive_engine
writes TRACE rows (one per change of decision); before that, only what
was logged (sent, held by cadence) shows.

Nothing is written. Run it each evening, or any time she says "Nancy was
quiet today" / "Nancy kept messaging".
"""
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

IST = timezone(timedelta(hours=5, minutes=30))
DAY_START, DAY_END = 7, 21          # waking hours checked for long gaps
LONG_GAP_MIN = 3 * 60               # nothing sent for this long while she's quiet
EARLY_DOSE_MIN = 15
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _dt(s):
    if not s:
        return None
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(IST)


def _hm(d):
    return d.strftime("%H:%M") if d else "--:--"


def _mins(hhmm):
    try:
        h, m = str(hhmm).split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _day_matches(days, weekday):
    days = str(days or "daily").lower().replace(" ", "")
    if days in ("daily", "everyday", "all", ""):
        return True
    return _WEEKDAYS[weekday] in days.split(",")


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: day_report.py USER_ID [YYYY-MM-DD]")
    uid = sys.argv[1]
    day = (datetime.strptime(sys.argv[2], "%Y-%m-%d").date()
           if len(sys.argv) > 2 else datetime.now(IST).date())

    from supabase_store import get_client
    db = get_client()

    start = datetime(day.year, day.month, day.day, tzinfo=IST)
    end = start + timedelta(days=1)
    s_utc, e_utc = start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()
    now = datetime.now(IST)
    is_today = day == now.date()
    upto = now if is_today else end

    # ── read ──────────────────────────────────────────────────────────────
    events = (db.table("proactive_events").select("*").eq("user_id", uid)
              .gte("created_at", s_utc).lt("created_at", e_utc)
              .order("created_at").execute()).data or []

    sess = [r["id"] for r in (db.table("sessions").select("id").eq("user_id", uid)
            .gte("updated_at", (start - timedelta(days=1)).astimezone(timezone.utc).isoformat())
            .execute()).data or []]
    msgs = []
    for i in range(0, len(sess), 50):
        msgs += (db.table("messages").select("role,content,timestamp,session_id")
                 .in_("session_id", sess[i:i + 50])
                 .gte("timestamp", s_utc).lt("timestamp", e_utc)
                 .execute()).data or []
    msgs.sort(key=lambda m: m["timestamp"])

    try:
        offers = (db.table("suggestions").select("*").eq("user_id", uid)
                  .gte("created_at", s_utc).lt("created_at", e_utc)
                  .order("created_at").execute()).data or []
    except Exception:
        offers = []

    sched = (db.table("care_schedule").select("*").eq("user_id", uid)
             .eq("active", True).execute()).data or []
    sched = [r for r in sched if _day_matches(r.get("days"), day.weekday())]

    # ── timeline ──────────────────────────────────────────────────────────
    lines = []
    for m in msgs:
        who = "HER  " if m["role"] == "user" else "NANCY"
        text = str(m.get("content") or "").replace("\n", " ")
        lines.append((_dt(m["timestamp"]), 2, f"{who}  {text[:150]}"))

    sent, held, traces = [], [], []
    for e in events:
        t = _dt(e.get("created_at"))
        act, why = e.get("action"), e.get("reason") or ""
        det, out = e.get("detail") or "", str(e.get("outcome") or "")
        if act == "TRACE":
            traces.append((t, why, det))
            lines.append((t, 1, f"  engine → {why}" + (f"  ({det})" if det and det not in why else "")))
        elif e.get("delivered_at") or out == "delivered" or out == "engaged":
            sent.append(e)
            lines.append((_dt(e.get("delivered_at")) or t, 0,
                          f"  SENT   {act:<20} {det}  [{why}]"))
        else:
            held.append(e)
            lines.append((t, 0, f"  {out or 'not sent':<6} {act:<20} {det}  [{why}]"))

    for o in offers:
        t = _dt(o.get("created_at"))
        lines.append((t, 3, f"  offer: {o.get('label')!r} → {o.get('reaction') or 'no reaction yet'}"
                            + (f"  (because {o['because']})" if o.get("because") else "")))

    lines.sort(key=lambda x: (x[0] or start, x[1]))

    print(f"\n{'=' * 78}\n{uid}  {day:%a %d %b %Y}"
          f"{'  (so far, ' + _hm(now) + ')' if is_today else ''}\n{'=' * 78}")
    her = [m for m in msgs if m["role"] == "user"]
    print(f"her messages: {len(her)}"
          + (f"  (first {_hm(_dt(her[0]['timestamp']))}, last {_hm(_dt(her[-1]['timestamp']))})" if her else ""))
    print("sent:", dict(Counter(e.get("action") for e in sent)) or "nothing")
    if held:
        print("not sent:", dict(Counter(f"{e.get('action')}:{e.get('outcome') or e.get('reason')}" for e in held)))
    if not traces:
        print("(no engine trace for this day: holds before the gate are invisible)")

    print("\n── timeline ──")
    for t, _, text in lines:
        print(f"{_hm(t)}  {text}")

    # ── problems ──────────────────────────────────────────────────────────
    probs = []
    sent_by = defaultdict(list)
    for e in sent:
        sent_by[e.get("action")].append(e)

    # meals: a follow-up for each declared meal whose time has passed
    boundaries = " | ".join(str(e.get("detail") or "").lower() for e in sent_by.get("BOUNDARY", []))
    for r in sched:
        if r.get("type") != "meal":
            continue
        at = _mins(r.get("time_of_day"))
        label = str(r.get("label") or "").lower()
        if at is None or at + 60 > upto.hour * 60 + upto.minute:
            continue        # not due yet
        if label and label not in boundaries:
            probs.append(f"no {label} follow-up went out (meal at {r['time_of_day'][:5]})")

    # medicines: one reminder per scheduled dose, not too early
    meds = [r for r in sched if r.get("type") == "medication"]
    reminders = sent_by.get("MEDICATION_REMINDER", [])
    for label in sorted({r["label"] for r in meds}):
        doses = sorted(_mins(r.get("time_of_day")) for r in meds if r["label"] == label)
        due = [d for d in doses if d is not None and d <= upto.hour * 60 + upto.minute]
        got = sorted(_dt(e.get("delivered_at") or e.get("created_at"))
                     for e in reminders if str(e.get("detail") or "") == label)
        if len(got) < len(due):
            probs.append(f"{label}: {len(due)} dose(s) due, {len(got)} reminder(s) sent")
        elif len(got) > len(doses):
            probs.append(f"{label}: {len(got)} reminders for {len(doses)} dose(s)")
        for dose, g in zip(due, got):
            early = dose - (g.hour * 60 + g.minute)
            if early > EARLY_DOSE_MIN:
                note = next((r.get("notes") for r in meds if r["label"] == label
                             and _mins(r.get("time_of_day")) == dose), "") or ""
                probs.append(f"{label}: reminded at {_hm(g)}, {early} min before the "
                             f"{dose // 60:02d}:{dose % 60:02d} dose" + (f" ('{note}')" if note else ""))

    # long quiet stretches: nothing sent and nothing from her, in waking hours
    marks = sorted([_dt(m["timestamp"]) for m in msgs])
    lo = start.replace(hour=DAY_START)
    hi = min(start.replace(hour=DAY_END), upto)
    prev = lo
    for t in [m for m in marks if lo <= m <= hi] + [hi]:
        if (t - prev).total_seconds() / 60 >= LONG_GAP_MIN:
            probs.append(f"nothing at all from {_hm(prev)} to {_hm(t)} "
                         f"({int((t - prev).total_seconds() // 3600)}h {int((t - prev).total_seconds() % 3600 // 60)}m)")
        prev = max(prev, t)

    # holds that lasted: consecutive engine decisions
    for i, (t, why, _) in enumerate(traces):
        nxt = traces[i + 1][0] if i + 1 < len(traces) else upto
        if why.startswith("SILENCE") and "late_night" not in why and \
                (nxt - t).total_seconds() / 60 >= 120:
            probs.append(f"held as {why} from {_hm(t)} to {_hm(nxt)}")

    # repeated messages from her
    for a, b in zip(her, her[1:]):
        if (str(a["content"]).strip().lower() == str(b["content"]).strip().lower()
                and (_dt(b["timestamp"]) - _dt(a["timestamp"])).total_seconds() < 600):
            probs.append(f"she sent the same message twice at {_hm(_dt(a['timestamp']))} "
                         f"and {_hm(_dt(b['timestamp']))}: {str(a['content'])[:60]!r}")

    # offers
    if offers:
        probs.append("offers: " + ", ".join(
            f"{o.get('label')} → {o.get('reaction') or 'pending'}" for o in offers))

    print("\n── worth looking at ──")
    for p in probs or ["nothing flagged"]:
        print(f"  • {p}")
    print()


if __name__ == "__main__":
    main()

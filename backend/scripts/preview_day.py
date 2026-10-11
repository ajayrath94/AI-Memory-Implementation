"""
What would a real person's day look like? Decides every hour, sends nothing.

    railway run python3 -u backend/scripts/preview_day.py USER_ID
    railway run python3 -u backend/scripts/preview_day.py USER_ID --compose

Walks 05:00 to 22:00 on the hour through the same path the scheduler takes:
proactive_check, then the cadence gate. Nothing is pushed and nothing is
written to proactive_events, so it can be run as often as you like against a
real account. --compose also writes each message (model calls, still nothing
sent), so you can read what they would get.

It walks TODAY's schedule, which is the same schedule tomorrow will use. What
it cannot know is what they say tomorrow, so it shows the day as if they said
nothing: the most messages they could get. Boundaries already spent or
answered today show as silent; run it early in the day for the cleanest view.

The cadence gap is measured on the walked clock, from the last message this
preview would have sent, which is how the real scheduler sees it hour by hour.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: preview_day.py USER_ID [--compose]")
    uid = sys.argv[1]
    compose = "--compose" in sys.argv

    import memory.day as D
    import memory.suggestions as S
    import memory.cadence as C
    from memory.proactive_engine import proactive_check

    real_m, real_s, real_l = D._mins_now, S._moment, C.todays_ledger
    last = {"min": None}
    offered_windows = set()

    def ledger(u):
        out = dict(real_l(u))
        out["minutes_since"] = (D._mins_now(u) - last["min"]
                                if last["min"] is not None else None)
        return out

    C.todays_ledger = ledger
    counts = {}
    try:
        D._mins_now = lambda u: 8 * 60
        from memory.windows import windows_today
        print(f"\n{uid}: windows")
        for w in windows_today(uid, read_her_words=False):
            print(f"   {w}")
        print()

        for h in range(5, 23):
            now = h * 60
            D._mins_now = lambda u, _n=now: _n
            S._moment = lambda u, _n=now: {**real_s(u), "now_min": _n}

            dec = proactive_check(uid, override_hour=h) or {}
            action = dec.get("action") or "SILENCE"
            what = dec.get("detail") or ""
            if action == "SILENCE":
                print(f"  {h:02d}:00  .            {dec.get('reason')}")
                continue

            # The real one is offered_in_window against suggestions, which
            # this preview never writes; track it here instead.
            win = dec.get("window")
            if action == "RECOMMENDATION" and win is not None:
                if win.clock() in offered_windows:
                    print(f"  {h:02d}:00  .            already offered in {win.clock()}")
                    continue

            gate = C.may_send(uid, action)
            if not gate.get("allow"):
                print(f"  {h:02d}:00  HELD {action[:14]:14} {what[:50]}  <- {gate.get('reason')}")
                continue

            line = f"  {h:02d}:00  SEND {action[:14]:14} {what[:60]}"
            if compose:
                try:
                    from memory.schedule_engine import generate_proactive_script
                    out = generate_proactive_script(
                        uid, action=action, hour=h, detail=str(what),
                        offer=dec.get("offer")) or {}
                    line += f"\n                 \"{(out.get('script') or '(empty)')[:150]}\""
                except Exception as e:
                    line += f"\n                 (compose raised: {e})"
            print(line)
            last["min"] = now
            counts[action] = counts.get(action, 0) + 1
            if action == "RECOMMENDATION" and win is not None:
                offered_windows.add(win.clock())
    finally:
        D._mins_now, S._moment, C.todays_ledger = real_m, real_s, real_l

    print(f"\n  would send: {counts or 'nothing'}")
    if not counts.get("RECOMMENDATION"):
        print("  no offer all day: read the lines above for the hour it was "
              "decided and what held it, or the reason it was never decided")


if __name__ == "__main__":
    main()

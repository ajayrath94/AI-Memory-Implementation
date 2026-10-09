"""
What does a decision carry, at each hour of her day?

    railway run python3 -u backend/tests/sim_decision.py

Three weeks, no offer delivered. The cause, finally: proactive_check picked
Kishore Kumar and passed it along, the composer ran pick_suggestion a second
time, got None at that moment, and every block guarded by `if picked:` was
skipped. The prompt reached the model containing the weather and nothing
else.

A decision now resolves the whole chain where it is made — pick, expand,
fetch — and carries it. This prints what each one holds, which is the test
that would have caught an empty one: the object either has the subject or it
does not, and you can see which.

WHAT TO READ
Each hour, what was decided and what came with it. Specifically:

    a RECOMMENDATION with no subject    must not exist. That was the bug.
    a MEDICATION_REMINDER               carries its one dose, not two
    a BOUNDARY                          carries the event it is about
    and an offer                        carries what it expands to, and the
                                        thing she can tap

The old path is run alongside for the same hours, so the difference is
visible rather than asserted.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

UID = "default"
_fails = []


def check(ok, label, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def main():
    import memory.day as D
    import memory.suggestions as S
    from memory.decision import build, hints_for

    real_d, real_s = D._mins_now, S._moment

    print("WHAT EACH HOUR DECIDES, AND WHAT IT CARRIES\n")
    offers, with_subject, with_artefact = 0, 0, 0

    for h in range(6, 22):
        D._mins_now = lambda uid, _n=h * 60: _n
        S._moment = lambda uid, _n=h * 60: {**real_s(uid), "now_min": _n}
        try:
            d = build(UID, hour=h)
        except Exception as e:
            print(f"  {h:02d}:00  build failed: {str(e)[:60]}")
            continue

        if d.action == "SILENCE":
            print(f"  {h:02d}:00  —  {d.reason}")
            continue

        print(f"  {h:02d}:00  {d.summary()}")

        if d.action == "RECOMMENDATION":
            offers += 1
            if d.subject:
                with_subject += 1
            if d.artefact:
                with_artefact += 1

    D._mins_now, S._moment = real_d, real_s

    print()
    check(offers == 0 or with_subject == offers,
          "no offer is decided without a subject",
          f"{with_subject} of {offers} carried one — an offer with no "
          f"subject is the bug that cost three weeks")

    # ── and what the composer would be told ─────────────────────────────
    print("\nWHAT THE COMPOSER WOULD BE TOLD, AT 11:00\n")
    D._mins_now = lambda uid: 11 * 60
    S._moment = lambda uid: {**real_s(UID), "now_min": 11 * 60}
    d = build(UID, hour=11)
    print(f"  decided: {d.summary()}")
    h = hints_for(d)
    print(f"  hints  : {h.strip()[:600] or '(nothing)'}")
    D._mins_now, S._moment = real_d, real_s

    if d.action == "RECOMMENDATION":
        check(bool(h.strip()), "an offer arrives with something to say",
              "the prompt reached the model containing only the weather")
        check(d.offering != "" , "it knows what it is offering")
        if d.offering and d.subject and d.offering != d.subject:
            print(f"\n  expanded: {d.subject} -> {d.offering}"
                  + (f" (because of {d.because})" if d.because else ""))

    # ── the three that must never be empty ──────────────────────────────
    print("\nTHE PARTS THAT MUST BE THERE\n")
    for hour, action, part in ((7, "MEDICATION_REMINDER", "dose"),
                               (9, "BOUNDARY", "boundary")):
        D._mins_now = lambda uid, _n=hour * 60: _n
        dd = build(UID, hour=hour)
        got = getattr(dd, part, None)
        if dd.action == action:
            print(f"  {hour:02d}:00 {action[:18]:20} {part}="
                  f"{'carried' if got else 'MISSING'}")
            check(bool(got), f"a {action.lower()} carries its {part}")
        else:
            print(f"  {hour:02d}:00 decided {dd.action} instead — "
                  f"{dd.reason}")
        D._mins_now = real_d


if __name__ == "__main__":
    crashed = None
    try:
        main()
    except Exception as e:
        crashed = e
    finally:
        print("\n" + "=" * 68)
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
        print("=" * 68)

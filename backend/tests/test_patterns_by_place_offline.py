"""
Offline checks for routines per place. No database, no model. From backend/:

    python3 -m pytest -q tests/test_patterns_by_place_offline.py

Ten days in Surat waking ~06:30, then twenty in Bengaluru waking ~08:00.
"""
import os
import sys
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _Res:
    def __init__(self, data): self.data = data


class _Q:
    def __init__(self, db, t):
        self.db, self.t, self.f, self.upd, self.ins = db, t, [], None, None
    def select(self, *_a, **_k): return self
    def eq(self, k, v): self.f.append(lambda r: r.get(k) == v); return self
    def is_(self, k, v): self.f.append(lambda r: r.get(k) is None); return self
    def gte(self, k, v): self.f.append(lambda r: str(r.get(k) or "") >= str(v)); return self
    def in_(self, k, vs): self.f.append(lambda r: r.get(k) in vs); return self
    def limit(self, *_a): return self
    def order(self, *_a, **_k): return self
    def update(self, u): self.upd = u; return self
    def insert(self, r): self.ins = r; return self
    def execute(self):
        rows = self.db.setdefault(self.t, [])
        if self.ins is not None:
            r = dict(self.ins); r["id"] = f"{self.t}-{len(rows)}"; rows.append(r)
            return _Res([r])
        hit = [r for r in rows if all(f(r) for f in self.f)]
        if self.upd is not None:
            for r in hit: r.update(self.upd)
        return _Res(hit)


DB = {}
store = types.ModuleType("supabase_store")
store.get_client = lambda: types.SimpleNamespace(table=lambda t: _Q(DB, t))
sys.modules["supabase_store"] = store
tc = types.ModuleType("memory.time_context")
tc.get_user_timezone = lambda uid: "Asia/Kolkata"
sys.modules["memory.time_context"] = tc

IST = timezone(timedelta(hours=5, minutes=30))


def _seed(arrived_days_ago=20, total=30, here="Vyalikaval HBCS Layout, Bengaluru", away=True):
    DB.clear()
    today = datetime.now(IST).replace(hour=12, minute=0, second=0, microsecond=0)
    arrived = today - timedelta(days=arrived_days_ago)
    DB["user_profile"] = [{"user_id": "u", "home_location": "Surat", "location": "Surat",
                           "current_location": here if away else None,
                           "arrived_at": arrived.astimezone(timezone.utc).isoformat() if away else None,
                           "life_context": {}}]
    DB["sessions"] = [{"id": "s1", "user_id": "u", "updated_at": datetime.now(timezone.utc).isoformat()}]
    msgs = []
    for i in range(total, 0, -1):
        day = today - timedelta(days=i)
        in_blr = day.date() >= arrived.date() and away
        wake = (8, 0) if in_blr else (6, 30)
        for h, m in (wake, (13, 0), (21, 30)):
            t = day.replace(hour=h, minute=m + (i % 3) * 5)
            msgs.append({"session_id": "s1", "role": "user",
                         "timestamp": t.astimezone(timezone.utc).isoformat()})
    DB["messages"] = msgs
    DB["user_patterns"] = [{"id": "w", "user_id": "u", "kind": "wake", "label": None,
                            "declared_at": "06:30:00", "source": "declared"}]


def _wake():
    return next(r for r in DB["user_patterns"] if r["kind"] == "wake")


def test_now_uses_the_place_she_is_in():
    from memory import patterns as P
    _seed()
    P.observe("u")
    w = _wake()
    assert w["observed_at"].startswith("08:"), w["observed_at"]
    assert w["place"].endswith("Bengaluru")
    assert w["by_place"]["Surat"]["observed_at"].startswith("06:")
    assert w["by_place"]["Vyalikaval HBCS Layout, Bengaluru"]["observed_at"].startswith("08:")
    assert w["by_place"]["Surat"]["home"] is True


def test_away_is_not_judged_against_home():
    from memory import patterns as P
    _seed()
    P.observe("u")
    # 08:00 in Bengaluru vs 06:30 declared at home would be a 90-minute
    # "drift"; judged against Bengaluru's own baseline it is none.
    assert _wake().get("drift_min") is None


def test_stays_log_is_kept_and_closed_on_return():
    from memory import patterns as P
    _seed()
    P.observe("u")
    stays = DB["user_profile"][0]["life_context"]["stays"]
    assert len(stays) == 1 and stays[0]["to"] is None and stays[0]["place"].endswith("Bengaluru")
    DB["user_profile"][0]["current_location"] = None        # she goes home
    P._stays("u")
    stays = DB["user_profile"][0]["life_context"]["stays"]
    assert stays[0]["to"] is not None
    # the trip's days stay labelled Bengaluru after she is home
    home, now, st = P._stays("u")
    d = datetime.now(IST).date() - timedelta(days=5)
    assert P._place_on(d, home, st).endswith("Bengaluru")
    assert now is None


def test_few_days_away_falls_back_to_home():
    from memory import patterns as P
    _seed(arrived_days_ago=2)
    P.observe("u")
    w = _wake()
    assert w["observed_at"].startswith("06:"), w["observed_at"]     # home's routine meanwhile
    assert w.get("drift_min") is None


def test_change_within_the_same_place_is_still_seen():
    from memory import patterns as P
    _seed(away=False)
    DB["user_patterns"][0]["declared_at"] = "05:00:00"               # she said 5, does 6:30
    P.observe("u")
    assert 85 <= (_wake().get("drift_min") or 0) <= 100

"""
Offline checks for closing and dropping lists. No database, no model.

    python3 -m pytest -q tests/test_lists_kept_offline.py

State as on 17 Oct: Grocery open, 13-Oct bazar and 09-Oct list kept.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _Res:
    def __init__(self, d): self.data = d


class _Q:
    def __init__(self, db, t):
        self.db, self.t, self.f, self.upd, self.dele, self.ins = db, t, [], None, False, None
    def select(self, *_a, **_k): return self
    def eq(self, k, v): self.f.append(lambda r: r.get(k) == v); return self
    def in_(self, k, vs): self.f.append(lambda r: r.get(k) in vs); return self
    def is_(self, k, v): self.f.append(lambda r: r.get(k) is None); return self
    @property
    def not_(self):
        q = self
        class N:
            def is_(s, k, v): q.f.append(lambda r: r.get(k) is not None); return q
        return N()
    def order(self, *_a, **_k): return self
    def limit(self, *_a): return self
    def update(self, u): self.upd = u; return self
    def delete(self): self.dele = True; return self
    def insert(self, r): self.ins = r; return self
    def execute(self):
        rows = self.db.setdefault(self.t, [])
        if self.ins is not None:
            r = dict(self.ins); r.setdefault("id", f"{self.t}{len(rows)}"); rows.append(r); return _Res([r])
        hit = [r for r in rows if all(f(r) for f in self.f)]
        if self.dele:
            self.db[self.t] = [r for r in rows if r not in hit]
        elif self.upd is not None:
            for r in hit: r.update(self.upd)
        return _Res(hit)


DB = {}
store = types.ModuleType("supabase_store")
store.get_client = lambda: types.SimpleNamespace(table=lambda t: _Q(DB, t))
sys.modules["supabase_store"] = store


def _seed():
    DB.clear()
    DB["lists"] = [
        {"id": "g", "user_id": "u", "name": "Grocery", "created_at": "2026-10-17T10:35:00+00:00", "closed_at": None},
        {"id": "b", "user_id": "u", "name": "bazar", "created_at": "2026-10-13T16:14:00+00:00", "closed_at": "2026-10-16T13:02:00+00:00"},
        {"id": "l", "user_id": "u", "name": "list", "created_at": "2026-10-09T18:57:00+00:00", "closed_at": "2026-10-09T19:31:00+00:00"},
    ]
    DB["list_items"] = [{"id": f"i{n}", "list_id": lid, "fields": {"what": f"x{n}"}, "done": False}
                        for n, lid in enumerate("gggbbbl")]


def _ids():
    return {l["id"]: ("open" if not l.get("closed_at") else "kept") for l in DB["lists"]}


def test_close_without_her_answer_closes_nothing():
    from engine_tools_shim import close_tool
    _seed()
    r = close_tool({"list_name": "Grocery"})
    assert r["why"] == "ask_first" and "rakh lein" in r["say"]
    assert _ids()["g"] == "open"


def test_keep_and_drop_an_open_list():
    from memory import lists as L
    _seed()
    assert L.close("u", "Grocery", keep=True)["kept"] is True
    assert _ids()["g"] == "kept"
    _seed()
    assert L.close("u", "Grocery", keep=False)["ok"]
    assert "g" not in _ids() and not [i for i in DB["list_items"] if i["list_id"] == "g"]


def test_drop_a_kept_list_by_name():
    from memory import lists as L
    _seed()
    r = L.close("u", "bazar", keep=False)
    assert r["ok"] and "bazar" in r["closed"]
    assert "b" not in _ids() and "g" in _ids() and "l" in _ids()


def test_drop_without_name_prefers_the_open_list():
    from memory import lists as L
    _seed()
    L.close("u", "", keep=False)
    assert "g" not in _ids() and "b" in _ids()


def test_drop_kept_without_name_asks_which():
    from memory import lists as L
    _seed()
    DB["lists"] = [l for l in DB["lists"] if l["id"] != "g"]      # no open list
    r = L.close("u", "", keep=False)
    assert r["why"] == "which kept list?" and len(r["kept_lists"]) == 2
    assert set(_ids()) == {"b", "l"}


def test_hint_mentions_kept_lists():
    from memory import lists as L
    _seed()
    L.walking = lambda uid: None
    h = L.hint("u")
    assert "Grocery" in h and "Kept lists" in h and "bazar" in h


def test_guard_sees_kept_lists():
    from memory.list_guard import _open_lists, _state
    _seed()
    lists = _open_lists("u", with_kept=True)
    assert {l["kept"] for l in lists} == {True, False}
    assert "KEPT" in _state(lists)
    assert all(not l["kept"] for l in _open_lists("u"))

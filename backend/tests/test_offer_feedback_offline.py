"""
Offline checks for the offer-feedback build. No database, no model: both are
replaced with small fakes. Run from backend/:

    python3 -m pytest -q tests/test_offer_feedback_offline.py
"""
import asyncio
import json
import os
import sys
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── fakes ────────────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, data):
        self.data = data


class _Q:
    """A tiny stand-in for a supabase table query over in-memory rows."""
    def __init__(self, store, table):
        self.store, self.table, self.filters, self._upd = store, table, [], None

    def select(self, *_a, **_k): return self
    def eq(self, k, v): self.filters.append(lambda r: r.get(k) == v); return self
    def limit(self, *_a): return self
    def gte(self, k, v): self.filters.append(lambda r: str(r.get(k) or "") >= str(v)); return self
    def order(self, *_a, **_k): return self
    def update(self, upd): self._upd = upd; return self

    @property
    def not_(self):
        q = self
        class _N:
            def is_(self_inner, k, v): q.filters.append(lambda r: r.get(k) is not None); return q
        return _N()

    def execute(self):
        rows = [r for r in self.store.setdefault(self.table, [])
                if all(f(r) for f in self.filters)]
        if self._upd is not None:
            for r in rows:
                r.update(self._upd)
        return _Res(rows)


class _DB:
    def __init__(self): self.store = {}
    def table(self, t): return _Q(self.store, t)


DB = _DB()
fake_store = types.ModuleType("supabase_store")
fake_store.get_client = lambda: DB
sys.modules["supabase_store"] = fake_store

LLM_ANSWERS = []
fake_llm = types.ModuleType("llm")
fake_llm.ask = lambda prompt, max_tokens=200, model_name=None: LLM_ANSWERS.pop(0) if LLM_ANSWERS else ""
sys.modules["llm"] = fake_llm


# ── rules ────────────────────────────────────────────────────────────────────

def _fresh(uid="u1"):
    DB.store["user_profile"] = [{"user_id": uid, "life_context": {}}]


def test_way_rule_blocks_only_that_way():
    from memory import offer_rules as R
    _fresh()
    R.add_rule("u1", "khana", "outside", "never", None, "bahar ka khana kabhi nahi mangwati")
    rules = R.rules("u1")
    assert R.blocked(rules, "khana", "outside", {}) is not None
    assert R.blocked(rules, "khana", "home", {}) is None          # can still cook it
    assert R.blocked(rules, "sangeet", None, {}) is None
    assert "from outside" in R.describe(rules[0])


def test_conditional_rule_only_on_that_day():
    from memory import offer_rules as R
    _fresh()
    R.add_rule("u1", "khana", None, "never", {"weekday": "Tuesday"}, "Mangalvar ko nahi")
    rules = R.rules("u1")
    assert rules[0]["when"] == {"weekday": "Tue"}
    assert R.blocked(rules, "khana", None, {"weekday": "Tue"}) is not None
    assert R.blocked(rules, "khana", None, {"weekday": "Wed"}) is None


def test_fast_day_rule():
    from memory import offer_rules as R
    _fresh()
    R.add_rule("u1", "khana", None, "never", {"fast_day": True}, "ekadashi hai")
    rules = R.rules("u1")
    assert R.blocked(rules, "khana", None, {"fast_day": True}) is not None
    assert R.blocked(rules, "khana", None, {"fast_day": False}) is None


def test_same_rule_twice_kept_once():
    from memory import offer_rules as R
    _fresh()
    R.add_rule("u1", "khana", "outside", "never", None, "pehli baar")
    R.add_rule("u1", "khana", "outside", "never", None, "doosri baar")
    rules = R.rules("u1")
    assert len(rules) == 1 and rules[0]["said"] == "doosri baar"


def test_ability_set_and_flip():
    from memory import offer_rules as R
    _fresh()
    R.set_ability("u1", "uses_phone", False, "phone chalana nahi aata")
    assert R.abilities("u1")["uses_phone"]["value"] is False
    R.set_ability("u1", "uses_phone", True, "Arjun ne sikha diya")
    assert R.abilities("u1")["uses_phone"]["value"] is True
    assert not R.set_ability("u1", "flies_planes", True)          # not a known ability


# ── credit goes to what was offered ──────────────────────────────────────────

def test_thing_of_song_is_the_singer():
    from memory.suggestions import _thing_of
    assert _thing_of("Mehbooba Mehbooba by R.D. Burman", "sangeet") == ("R.D. Burman", "artist")
    assert _thing_of("Mehbooba Mehbooba by R.D. Burman", "") == ("R.D. Burman", "artist")
    assert _thing_of("Chalti Ka Naam Gaadi", "dekhna") == ("Chalti Ka Naam Gaadi", "media")
    assert _thing_of("Sabudana Khichdi", "khana") == ("Sabudana Khichdi", "food")


def test_offer_seed_weight_is_small():
    from memory.suggestions import OFFER_SEED_WEIGHT, REACTION_WEIGHT
    assert 0 < OFFER_SEED_WEIGHT["accepted"] < REACTION_WEIGHT["accepted"]
    assert REACTION_WEIGHT["declined_preference"] < OFFER_SEED_WEIGHT["declined_preference"] < 0
    assert OFFER_SEED_WEIGHT["declined_way"] == 0 and REACTION_WEIGHT["declined_way"] == 0


# ── reading her answer ───────────────────────────────────────────────────────

def test_read_reply_parses_json_and_falls_back():
    from memory.suggestions import read_reply
    LLM_ANSWERS[:] = ['```json\n{"reaction": "declined_way", "never": true, '
                      '"way_she_wants": "home", "condition": null, "ability": null}\n```']
    got = read_reply("Fruit chaat from Sagar", "bahar ka khana kabhi nahi mangwati", way="outside")
    assert got["reaction"] == "declined_way" and got["never"] is True
    LLM_ANSWERS[:] = ["no idea", "still nothing"]
    assert read_reply("x", "y") is None


def test_follow_through_makes_rules_and_abilities():
    from memory.suggestions import _follow_through
    from memory import offer_rules as R
    _fresh()
    _follow_through("u1", {"id": "s1", "kind": "khana", "way": "outside"}, "declined_way",
                    {"never": True}, "bahar ka khana nahi khati")
    _follow_through("u1", {"id": "s2", "kind": "khana", "way": "home"}, "declined_timing",
                    {"condition": {"weekday": "Tue"}}, "Mangalvar ko nahi")
    _follow_through("u1", {"id": "s3", "kind": "sangeet"}, "declined_timing",
                    {"ability": {"key": "uses_phone", "value": False}}, "phone chalana nahi aata")
    rules = R.rules("u1")
    assert any(r["way"] == "outside" and not r["when"] for r in rules)
    assert any(r["when"] == {"weekday": "Tue"} and not r["way"] for r in rules)
    assert R.abilities("u1")["uses_phone"]["value"] is False


def test_accepted_another_way_makes_no_rule():
    from memory.suggestions import _follow_through
    from memory import offer_rules as R
    _fresh()
    _follow_through("u1", {"id": "s1", "kind": "khana", "way": "outside"}, "accepted",
                    {"way_she_wants": "home"}, "Ghar pe hi bana lenge")
    assert R.rules("u1") == []


# ── weighing the history ─────────────────────────────────────────────────────

def test_fade_by_time_and_kind():
    from memory.affinity import _fade
    assert abs(_fade("accepted", 45) - 0.5) < 1e-9
    assert abs(_fade("declined_timing", 21) - 0.5) < 1e-9
    assert _fade("no_response", 70) < 0.001
    assert _fade("declined_preference", 0) == 0.0               # about the thing, not the hour


def test_old_no_loses_to_recent_yes():
    from memory import affinity as A
    now = datetime.now(timezone.utc)
    DB.store["suggestions"] = [
        {"user_id": "u2", "intent": "recommendation", "kind": "sangeet",
         "offered_hour": 15, "reaction": "declined_timing",
         "created_at": (now - timedelta(days=120)).isoformat()},
        {"user_id": "u2", "intent": "recommendation", "kind": "sangeet",
         "offered_hour": 15, "reaction": "accepted",
         "created_at": (now - timedelta(days=1)).isoformat()},
    ]
    sys.modules["memory.offers"] = types.SimpleNamespace(hers=lambda uid: {})
    try:
        ev = A._evidence("u2")
        e = ev[("afternoon", "sangeet")]
        assert e["yes"] > 0.9 and e["no"] < 0.05
    finally:
        del sys.modules["memory.offers"]


# ── songs ────────────────────────────────────────────────────────────────────

def test_match_recording_cases():
    from memory.offers import _match_recording, _MATCH_CACHE
    _MATCH_CACHE.clear()
    LLM_ANSWERS[:] = ['{"same_song": true, "singer_in_title": "R.D. Burman", "same_singer": true}']
    assert _match_recording("Mehbooba Mehbooba by R.D. Burman",
                            "Mehbooba Oh Mehbooba - Lyrical | RD Burman") == (True, None)
    LLM_ANSWERS[:] = ['{"same_song": true, "singer_in_title": "Kishore Kumar", "same_singer": false}']
    assert _match_recording("Khaike Paan Banaras Wala by Mohammad Rafi",
                            "Khaike Paan Banaras Wala - Video Song | Don | Kishore Kumar") == \
        (True, "Khaike Paan Banaras Wala by Kishore Kumar")
    LLM_ANSWERS[:] = ['{"same_song": false, "singer_in_title": null, "same_singer": null}']
    assert _match_recording("Some Song by X", "Top 100 Songs Jukebox") == (False, None)
    # cached: no model call the second time
    LLM_ANSWERS[:] = []
    assert _match_recording("Some Song by X", "Top 100 Songs Jukebox") == (False, None)


# ── repeated messages ────────────────────────────────────────────────────────

def _install_messages(msgs):
    fake_store.get_recent_messages = lambda sid, n=4: msgs[-n:]


def _router():
    """Just the repeat check from engine_router, without importing the whole
    engine (litellm, the classifier and the rest are not needed for it)."""
    import ast
    src = open(os.path.join(os.path.dirname(__file__), "..", "engine", "engine_router.py")).read()
    tree = ast.parse(src)
    keep = [n for n in tree.body
            if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name in ("_norm_msg", "_answer_for_repeat"))
            or (isinstance(n, ast.Assign) and any(getattr(t, "id", "").startswith("REPEAT_")
                                                  for t in n.targets))]
    ns = {}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "engine_router", "exec"), ns)
    return types.SimpleNamespace(**ns)


def test_repeat_gets_the_reply_already_given():
    E = _router()
    t0 = datetime.now(timezone.utc) - timedelta(seconds=40)
    _install_messages([
        {"role": "user", "content": "Rd Burman mujhe bhaut pasand hai , unke gane bhaut ache the",
         "timestamp": t0.isoformat()},
        {"role": "assistant", "content": "Haan, R.D. Burman ka jaadu alag hi tha",
         "timestamp": (t0 + timedelta(seconds=30)).isoformat()},
    ])
    got = asyncio.run(E._answer_for_repeat("s", "Rd Burman mujhe  bhaut pasand hai , unke gane bhaut ache the "))
    assert got == "Haan, R.D. Burman ka jaadu alag hi tha"


def test_short_haan_twice_is_not_a_repeat():
    E = _router()
    t0 = datetime.now(timezone.utc) - timedelta(seconds=40)
    _install_messages([
        {"role": "user", "content": "haan", "timestamp": t0.isoformat()},
        {"role": "assistant", "content": "Aur chai pi?", "timestamp": (t0 + timedelta(seconds=10)).isoformat()},
    ])
    assert asyncio.run(E._answer_for_repeat("s", "haan")) is None


def test_old_or_different_message_is_new():
    E = _router()
    t0 = datetime.now(timezone.utc) - timedelta(minutes=20)
    _install_messages([
        {"role": "user", "content": "Rd Burman mujhe bhaut pasand hai", "timestamp": t0.isoformat()},
        {"role": "assistant", "content": "Haan", "timestamp": (t0 + timedelta(seconds=30)).isoformat()},
    ])
    assert asyncio.run(E._answer_for_repeat("s", "Rd Burman mujhe bhaut pasand hai")) is None
    assert asyncio.run(E._answer_for_repeat("s", "Aaj mausam accha hai")) is None


def test_way_with_condition_is_one_rule_for_that_day():
    from memory.suggestions import _follow_through
    from memory import offer_rules as R
    _fresh()
    _follow_through("u1", {"id": "s1", "kind": "khana", "way": "outside"}, "declined_way",
                    {"condition": {"weekday": "Tue"}}, "Mangalvar ko bahar ka nahi khati")
    rules = R.rules("u1")
    assert len(rules) == 1 and rules[0]["way"] == "outside" and rules[0]["when"] == {"weekday": "Tue"}
    assert R.blocked(rules, "khana", "outside", {"weekday": "Wed"}) is None
    assert R.blocked(rules, "khana", "outside", {"weekday": "Tue"}) is not None

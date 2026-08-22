"""
FUSION — observations that need more than one source to be worth saying.

Weather on its own is a bulletin: "aaj 32 degrees hai aur humidity 78%" is not
something a companion says. Knee pain on its own is already known. But a cold
morning AND a knee that hurts in the cold AND no mention of it for days is one
line worth saying, and it took all three to earn it.

That is the difference between fusion and concatenation. Handing the model a
weather block, a location block and a memory block and letting it choose is
concatenation — it is also what produced a 20:00 medication nudge that asked
about lunch, because lunch was in scope and read well. Here the sources are
combined BEFORE the prompt, and a rule that cannot satisfy all its inputs stays
quiet. Most turns nothing fires, which is correct.

Rules are deliberately few. A rules layer nobody maintains is worse than none;
add one only when there is a specific message it would improve.
"""
import time
from typing import Optional

# Weather does not change in fifteen minutes, and the call is a live
# OpenWeather request. Without this, running fusion on every compose means an
# external round-trip per message.
_WEATHER_TTL = 900
_weather_cache: dict = {}


def _weather(user_id: str) -> Optional[dict]:
    hit = _weather_cache.get(user_id)
    if hit and (time.time() - hit[0]) < _WEATHER_TTL:
        return hit[1]
    try:
        from routes.integrations import get_weather
        data = get_weather(user_id)
        if not data or data.get("error"):
            _weather_cache[user_id] = (time.time(), None)
            return None
        _weather_cache[user_id] = (time.time(), data)
        return data
    except Exception as e:
        print(f"[Fusion] weather failed: {e}")
        _weather_cache[user_id] = (time.time(), None)
        return None


def _profile(user_id: str) -> dict:
    try:
        from memory.profile_store import get_user_profile
        return get_user_profile(user_id) or {}
    except Exception:
        return {}


def _live_state(user_id: str, needle: str) -> Optional[dict]:
    """What is actually going on with this thing right now.

    The rules first read only the profile — a condition that has been true for
    months — so a knee question fired on a cold morning whether she had said
    "ghutna theek hai" yesterday or "bahut dard hai". The clusters know the
    difference: current_state carries recency-weighted sentiment and trend
    carries direction. Reading them is what makes an observation observant
    rather than merely triggered.
    """
    from datetime import datetime, timezone
    try:
        from supabase_store import get_client
        rows = (get_client().table("interest_clusters")
                .select("label,current_state,trend,last_event,event_count")
                .eq("user_id", user_id).eq("status", "active").execute()).data or []
    except Exception as e:
        print(f"[Fusion] state read failed: {e}")
        return None

    n = needle.lower()
    hit = next((r for r in rows if n in (r.get("label") or "").lower()), None)
    if not hit:
        return None

    days_since = None
    if hit.get("last_event"):
        try:
            dt = datetime.fromisoformat(str(hit["last_event"]).replace("Z", "+00:00"))
            days_since = (datetime.now(timezone.utc) - dt).days
        except Exception:
            pass

    return {
        "label":       hit.get("label"),
        "state":       hit.get("current_state"),
        "trend":       hit.get("trend"),
        "mentions":    hit.get("event_count") or 0,
        "days_since":  days_since,
    }


def _state_sentence(st: dict) -> str:
    """Say what is known, in plain terms the model can use."""
    bits = [f"They have mentioned {st['label']} {st['mentions']} time(s)"]
    if st.get("days_since") is not None:
        bits.append(f"last brought up {st['days_since']} day(s) ago")
    if st.get("trend") in ("improving", "worsening"):
        bits.append(f"and it has been {st['trend']}")
    elif st.get("state") is not None and st["state"] < -0.3:
        bits.append("and they sound unhappy about it")
    return ", ".join(bits) + "."


def _mentioned_recently(user_id: str, needle: str, days: int = 3) -> bool:
    """Has this come up lately? A rule that raises something they just talked
    about is not observant, it is repetitive."""
    from datetime import datetime, timezone, timedelta
    try:
        from supabase_store import get_client
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = (get_client().table("user_behavioral_events")
                .select("value").eq("user_id", user_id)
                .gte("created_at", since).execute()).data or []
        n = needle.lower()
        return any(n in (r.get("value") or "").lower() for r in rows)
    except Exception:
        return False


# ── rules ─────────────────────────────────────────────────────────────────────
# Each returns a line to add to the prompt, or None. None is the common case.

def cold_and_aching_joints(user_id: str, slot: str = "", **_) -> Optional[str]:
    """
    Cold weather + a joint condition + not raised recently.

    One profile records the connection explicitly — "knee pain worse in cold
    weather" — so on a cold morning this is exactly what a person who knew her
    would ask. On a warm day, or for someone without the condition, it stays
    quiet.
    """
    if slot not in ("morning", "midday", ""):
        return None

    health = (_profile(user_id).get("health") or {})
    conditions = " ".join(str(x) for x in (health.get("conditions") or [])).lower()
    concerns   = " ".join(str(x) for x in (health.get("concerns") or [])).lower()
    both = conditions + " " + concerns
    if not any(w in both for w in ("knee", "joint", "arthrit", "ghutn", "back pain")):
        return None

    w = _weather(user_id)
    if not w or w.get("temp_c") is None:
        return None
    if w["temp_c"] > 18:
        return None

    # If they raised it themselves in the last day, asking again is not
    # attentive, it is repetitive.
    st = _live_state(user_id, "knee") or _live_state(user_id, "ghutn")
    if st and st.get("days_since") is not None and st["days_since"] < 1:
        return None

    # Facts, not a script. The model writes the line; it needs to know the
    # trajectory to write a good one — "still bad?" and "better now?" are
    # different questions and only the state can tell them apart.
    lines = [f"It is {round(w['temp_c'])}°C where they are, which is cold for "
             f"them, and their joints hurt more in the cold."]
    if st:
        lines.append(_state_sentence(st))
    lines.append("Ask about it in passing, the way someone who had been paying "
                 "attention would. Do not state the temperature back at them.")
    return " ".join(lines)


def hot_and_elderly(user_id: str, slot: str = "", **_) -> Optional[str]:
    """Heat is a real risk for an older person, and a nudge to drink water is
    worth one line. Only in the middle of the day, and only when it is properly
    hot rather than merely warm."""
    if slot not in ("midday", "afternoon"):
        return None
    w = _weather(user_id)
    if not w or w.get("temp_c") is None or w["temp_c"] < 36:
        return None
    return ("It is very hot there today. Remind them to drink water — once, "
            "gently, not as an instruction.")


RULES = [
    cold_and_aching_joints,
    hot_and_elderly,
]


def fused_context(user_id: str, slot: str = "", intent: str = "") -> str:
    """
    At most one observation. Two would be a bulletin, and the first rule to
    fire is the most specific one because RULES is ordered that way.
    """
    for rule in RULES:
        try:
            line = rule(user_id, slot=slot, intent=intent)
        except Exception as e:
            print(f"[Fusion] {rule.__name__} raised: {e}")
            continue
        if line:
            print(f"[Fusion] {rule.__name__} fired for {user_id}")
            return line
    return ""

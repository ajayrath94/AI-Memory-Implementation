"""
SNAPSHOT — everything known about one person, in one call.

Three dashboards existed for this and all three are dead: they call
/memory/stm, /memory/user, /memory/state and /alerts/detected, none of which
survive. They were written against an earlier shape of the system and drifted
out of existence rather than being updated, which is what happens to read
surfaces that are assembled ad hoc.

This is the raw view. No interpretation, no curation — what is actually stored,
so a question like "why did it say that" can be answered by looking rather than
by writing another probe. A caregiver-facing view is a different endpoint built
on the same reads: a daughter should see trends and concerns, not cluster
centroids and confidence scores.

Every section is independently guarded. A snapshot missing its clusters because
one query failed is far more useful than a 500.
"""
from fastapi import APIRouter
from datetime import datetime, timezone, timedelta

router = APIRouter()


def _db():
    from supabase_store import get_client
    return get_client()


def _declared(user_id: str) -> dict:
    try:
        from memory.declared import get_declared
        d = get_declared(user_id)
        return {
            "name": d.name, "age_group": d.age_group,
            "caregiver_id": d.caregiver_id,
            "place": {"home": d.place.home, "current": d.place.current,
                      "timezone": d.place.timezone, "away": d.place.away},
            "language": {"pref": d.language.pref, "mix": d.language.mix,
                         "instruction": d.language.instruction},
            "companion": {
                "name": d.companion.name, "relationship": d.companion.relationship,
                "familial": d.companion.is_familial,
                "warmth": d.companion.warmth, "humour": d.companion.humour,
                "slangs": d.companion.slangs, "voice_id": d.companion.voice_id,
                "name_history": d.companion.name_history,
            },
            "rhythm": {"wake": d.rhythm.wake, "sleep": d.rhythm.sleep,
                       "meals": d.rhythm.meals, "routines": d.rhythm.routines},
            "interests_declared": d.interests,
        }
    except Exception as e:
        return {"error": str(e)[:200]}


def _memory(user_id: str) -> dict:
    try:
        from memory.user_memory_store import get_user_memory
        m = get_user_memory(user_id) or {}
        return {
            "summary": m.get("summary"),
            "key_facts": m.get("key_facts") or [],
            "session_count": m.get("session_count"),
            "updated_at": m.get("updated_at"),
        }
    except Exception as e:
        return {"error": str(e)[:200]}


def _clusters(user_id: str) -> list:
    """What the system has noticed. Centroid and embedding are omitted — they
    are large, unreadable, and nobody inspecting a user needs 768 floats."""
    try:
        rows = (_db().table("interest_clusters")
                .select("id,label,pillar,relationship,current_state,trend,"
                        "event_count,strength,first_seen,last_event,status,attributes")
                .eq("user_id", user_id)
                .order("strength", desc=True).limit(60).execute()).data or []
        return rows
    except Exception as e:
        return [{"error": str(e)[:200]}]


def _patterns(user_id: str) -> list:
    try:
        return (_db().table("user_patterns").select("*")
                .eq("user_id", user_id).order("kind").execute()).data or []
    except Exception as e:
        return [{"error": str(e)[:200]}]


def _interests(user_id: str) -> dict:
    try:
        from memory.interests_view import computed_interests, computed_dislikes
        return {"likes": computed_interests(user_id),
                "dislikes": computed_dislikes(user_id)}
    except Exception as e:
        return {"error": str(e)[:200]}


def _suggestions(user_id: str, limit: int = 20) -> list:
    try:
        return (_db().table("suggestions")
                .select("label,intent,reaction,created_at,reacted_at,context")
                .eq("user_id", user_id)
                .order("created_at", desc=True).limit(limit).execute()).data or []
    except Exception as e:
        return [{"error": str(e)[:200]}]


def _mood(user_id: str, days: int = 14) -> list:
    """Recent session mood. This is what the alert engine counts, and it was
    empty on every row for the system's whole life because extraction sat
    behind a summary that short conversations never produced."""
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return (_db().table("sessions")
                .select("id,valence,arousal,soft_flags,acute,created_at")
                .eq("user_id", user_id).gte("created_at", since)
                .order("created_at", desc=True).limit(30).execute()).data or []
    except Exception as e:
        return [{"error": str(e)[:200]}]


def _alerts(user_id: str) -> list:
    try:
        from memory.alert_engine import detect_alerts
        return detect_alerts(user_id)
    except Exception as e:
        return [{"error": str(e)[:200]}]


def _proactive(user_id: str, limit: int = 15) -> list:
    try:
        return (_db().table("proactive_events")
                .select("action,reason,detail,outcome,slot,created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True).limit(limit).execute()).data or []
    except Exception as e:
        return [{"error": str(e)[:200]}]


# Declared before the catch-all below. FastAPI matches routes in order, so
# with /{user_id} first, a request to /snapshot/overview was read as a user
# called "overview" and the list was unreachable.
@router.get("/overview")
def overview():
    """Everyone, one row each, ordered so the rows that need a look come first.

    Deliberately does not call detect_alerts — that makes a model call per user
    when it finds a candidate, which is fine on demand and wasteful for a list
    that gets refreshed. It reads the alert count already stored on the
    fingerprint instead.
    """
    from datetime import datetime, timezone
    try:
        users = (_db().table("user_memory")
                 .select("user_id,session_count")
                 .order("updated_at", desc=True).execute()).data or []
    except Exception as e:
        return {"users": [], "error": str(e)[:200]}

    # Synthetic users beside real ones is the problem this view exists to
    # avoid. The detail endpoint still serves them by id, so a probe can be
    # inspected directly.
    try:
        from memory.testing import test_user_ids, looks_like_test_id
        marked = test_user_ids()
        users = [u for u in users
                 if u["user_id"] not in marked
                 and not looks_like_test_id(u["user_id"])]
    except Exception as e:
        print(f"[Snapshot] test filter failed: {e}")

    rows = []
    for u in users:
        try:
            rows.append(_summary_for(u["user_id"], u.get("session_count") or 0))
        except Exception as e:
            rows.append({"user_id": u["user_id"], "error": str(e)[:120]})

    order = {"attention": 0, "watch": 1, None: 2}
    rows.sort(key=lambda r: (order.get(r.get("flag"), 2),
                             -(r.get("days_since") or 0)))

    return {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "count":    len(rows),
        "attention": sum(1 for r in rows if r.get("flag") == "attention"),
        "quiet":     sum(1 for r in rows if r.get("quiet")),
        "users":    rows,
    }


@router.get("/{user_id}")
def snapshot(user_id: str, include_alerts: bool = False):
    """
    Everything stored about one person.

    Alerts are opt-in because detect_alerts makes a model call when it finds a
    candidate pattern — fine on demand, wasteful if a dashboard polls this.
    """
    out = {
        "user_id":     user_id,
        "taken_at":    datetime.now(timezone.utc).isoformat(),
        "declared":    _declared(user_id),
        "memory":      _memory(user_id),
        "clusters":    _clusters(user_id),
        "patterns":    _patterns(user_id),
        "interests":   _interests(user_id),
        "suggestions": _suggestions(user_id),
        "mood":        _mood(user_id),
        "proactive":   _proactive(user_id),
        "pillars":     _pillars(user_id),
    }
    if include_alerts:
        out["alerts"] = _alerts(user_id)
    return out


@router.get("")
def list_users():
    """Who there is to look at. user_memory rather than user_profile: a row
    here means a conversation actually happened, where the profile table holds
    every throwaway id anything has ever written."""
    try:
        rows = (_db().table("user_memory")
                .select("user_id,session_count,updated_at")
                .order("updated_at", desc=True).execute()).data or []
        return {"users": rows, "count": len(rows)}
    except Exception as e:
        return {"users": [], "error": str(e)[:200]}


def _pillars(user_id: str) -> dict:
    """What they talk about, and which way each pillar is moving."""
    try:
        from memory.user_memory_store import get_user_memory
        m = get_user_memory(user_id) or {}
        trend = m.get("pillar_trend") or {}
        fp    = m.get("behavioural_fingerprint") or {}
        if isinstance(trend, str):
            import json as _j
            trend = _j.loads(trend)
        if isinstance(fp, str):
            import json as _j
            fp = _j.loads(fp)

        trends = trend.get("pillar_trends") or {}
        moving = {k: v for k, v in trends.items() if v not in ("stable", "new")}

        return {
            "dominant":          fp.get("dominant_pattern"),
            "trends":            trends,
            "moving":            moving,          # the only ones worth reading
            "emerging":          fp.get("emerging_interests") or [],
            "fading":            fp.get("fading_interests") or [],
            "consistency":       fp.get("session_consistency"),
            "sessions_analyzed": fp.get("sessions_analyzed"),
        }
    except Exception as e:
        return {"error": str(e)[:200]}


# ── the list view ─────────────────────────────────────────────────────────────

def _mood_direction(valences: list) -> str:
    """Which way the mood is going.

    Needs six sessions before it will say anything: three to compare against
    three. Fewer and it returns "unknown" rather than inventing a trend — the
    same reason pattern confidence gates drift. A dashboard that confidently
    reports a direction from two data points teaches people to distrust it.
    """
    vals = [float(v) for v in valences if v is not None]
    if len(vals) < 6:
        return "unknown"
    recent  = sum(vals[:3]) / 3.0
    earlier = sum(vals[3:6]) / 3.0
    delta   = recent - earlier
    if delta > 0.2:
        return "rising"
    if delta < -0.2:
        return "falling"
    return "steady"


def _summary_for(user_id: str, session_count: int) -> dict:
    """One row. Every field earns its place by being a reason to look closer."""
    from datetime import datetime, timezone
    from supabase_store import get_client
    db = get_client()

    row = {
        "user_id": user_id,
        "session_count": session_count,
        "name": None, "place": None, "away": False,
        "days_since": None, "mood": "unknown", "quiet": False,
        "alerts": 0, "unresolved_drift": 0, "talks_about": None,
        "flag": None,
    }

    try:
        from memory.declared import get_declared
        d = get_declared(user_id)
        row["name"]  = d.name
        row["place"] = d.place.where_now
        row["away"]  = d.place.away
    except Exception:
        pass

    # silence, both absolute and relative to their own rhythm
    try:
        from memory.time_context import time_context
        tc = time_context(user_id)
        mins = tc.get("minutes_since_last")
        if mins is not None:
            row["days_since"] = round(mins / 1440.0, 1)
        row["quiet"] = bool(tc.get("unusual_silence"))
    except Exception:
        pass

    try:
        vals = (db.table("sessions").select("valence")
                .eq("user_id", user_id).not_.is_("valence", "null")
                .order("created_at", desc=True).limit(6).execute()).data or []
        row["mood"] = _mood_direction([v["valence"] for v in vals])
    except Exception:
        pass

    # Drift that was raised and never answered. Not every drift — one that has
    # been explained is housekeeping; one that has not is a question outstanding.
    try:
        pats = (db.table("user_patterns")
                .select("drift_min,drift_note,asked_at")
                .eq("user_id", user_id).not_.is_("drift_min", "null")
                .execute()).data or []
        row["unresolved_drift"] = sum(1 for p in pats if not p.get("drift_note"))
    except Exception:
        pass

    try:
        from memory.user_memory_store import get_user_memory
        m  = get_user_memory(user_id) or {}
        fp = m.get("behavioural_fingerprint") or {}
        if isinstance(fp, str):
            import json as _j
            fp = _j.loads(fp)
        row["talks_about"] = fp.get("dominant_pattern")
        row["alerts"] = len(fp.get("alerts") or [])
    except Exception:
        pass

    # One judgement, made here rather than in every reader. Silence for over a
    # week is the strongest signal an eldercare product has, so it outranks the
    # rest.
    if (row["days_since"] or 0) >= 7 or row["alerts"] or row["mood"] == "falling":
        row["flag"] = "attention"
    elif row["unresolved_drift"] or row["quiet"]:
        row["flag"] = "watch"

    return row


"""
THE OFFER LOG — every recommendation that reached her, and what came back.

One row per offer in `suggestions`, now with everything needed to learn from
it later:

    local_date, weekday, offered_hour      when, on her clock
    kind                                   what it WAS: sangeet, khana, dekhna,
                                           shauk, bhakti — the thing offered,
                                           not the interest it came from
    label, because, why_now                what, from which love, and why then
    link                                   the song, the map, the recipe sent
    festival                               "Sharad Navratri, day 3 of 9"
    reaction, reply_text                   what she did, in her own words

Two uses:

    history() / patterns()   the helper the recommendation step reads: her
                             recent answers, and what has worked at this part
                             of the day and on this weekday, by kind
    rows()                   the same rows for a person to read — see
                             scripts/offer_log.py

Why kind is stored. The time-of-day learning used the category of the
interest an offer came from. Lag Ja Gale came "because of movie", so her yes
taught that films go well at two in the afternoon; pranayam came from "Walk".
The offer's own kind is what she said yes or no to.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

# Slots of her day, the same as affinity.py, so the two agree.
_SLOTS = ((5, "early_morning"), (9, "morning"), (12, "midday"),
          (15, "afternoon"), (18, "evening"), (21, "night"))

_YES = ("accepted",)
_NO_NOW = ("declined_timing",)
_NO_THIS = ("declined_preference", "declined")


def slot_of_hour(h: Optional[int]) -> str:
    if h is None:
        return ""
    name = "night"
    for start, s in _SLOTS:
        if h >= start:
            name = s
    return name


def _db():
    from supabase_store import get_client
    return get_client()


def _tz(user_id: str):
    from zoneinfo import ZoneInfo
    try:
        from memory.declared import get_declared
        return ZoneInfo(get_declared(user_id).place.timezone or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def stamp(user_id: str, offer, window=None, now_min: Optional[int] = None) -> Dict:
    """The extra columns for an offer being recorded now. Best effort: a
    missing part is left out, never guessed."""
    tz = _tz(user_id)
    now = datetime.now(tz)
    out = {
        "local_date": now.date().isoformat(),
        "weekday": now.strftime("%A"),
        "kind": (getattr(offer, "category", "") or "")[:20] or None,
        "why_now": (getattr(offer, "why_now", "") or "")[:300] or None,
    }
    art = getattr(offer, "artefact", None) or {}
    if art.get("url"):
        out["link"] = str(art["url"])[:500]
    try:
        from memory.festival_brief import for_user
        f = for_user(user_id)
        if f:
            out["festival"] = (f"{f['name']}, day {f.get('day_of')} of {f.get('days')}"
                               + (", fasting" if f.get("fasting") and f.get("she_keeps_it") else ""))[:120]
    except Exception:
        pass
    return {k: v for k, v in out.items() if v}


def rows(user_id: str, days: int = 30, limit: int = 200) -> List[Dict]:
    """Every offer in the last `days`, oldest first, on her clock."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cols = ("created_at,label,because,window_label,offered_hour,reaction,"
            "reacted_at,cluster_id,kind,local_date,weekday,reply_text,link,"
            "festival,why_now")
    try:
        data = (_db().table("suggestions").select(cols)
                .eq("user_id", user_id).eq("intent", "recommendation")
                .gte("created_at", since).order("created_at")
                .limit(limit).execute()).data or []
    except Exception:
        # Before the columns exist: the old ones only.
        try:
            data = (_db().table("suggestions")
                    .select("created_at,label,because,window_label,offered_hour,"
                            "reaction,reacted_at,cluster_id")
                    .eq("user_id", user_id).eq("intent", "recommendation")
                    .gte("created_at", since).order("created_at")
                    .limit(limit).execute()).data or []
        except Exception as e:
            print(f"[OfferLog] read failed: {e}")
            return []

    tz = _tz(user_id)
    kind_of = {}
    try:
        from memory.offers import hers
        kind_of = {v.get("id"): v.get("category") or "" for v in hers(user_id).values()}
    except Exception:
        pass

    out = []
    for r in data:
        try:
            at = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00")).astimezone(tz)
        except Exception:
            at = None
        hour = r.get("offered_hour")
        if hour is None and at is not None:
            hour = at.hour
        out.append({
            "date": r.get("local_date") or (at.date().isoformat() if at else ""),
            "weekday": r.get("weekday") or (at.strftime("%A") if at else ""),
            "time": at.strftime("%H:%M") if at else "",
            "hour": hour,
            "slot": slot_of_hour(hour),
            # The offer's own kind; for rows from before it was stored, the
            # interest's, which is the best that is known.
            "kind": r.get("kind") or kind_of.get(r.get("cluster_id"), "") or "",
            "what": r.get("label") or "",
            "because": r.get("because") or "",
            "why": r.get("why_now") or "",
            "link": r.get("link") or "",
            "festival": r.get("festival") or "",
            "answer": r.get("reaction") or "open",
            "her_words": r.get("reply_text") or "",
        })
    return out


def history(user_id: str, n: int = 12) -> List[Dict]:
    """Her last few answers, for the recommendation step. Compact."""
    out = []
    for r in rows(user_id, days=30)[-n:]:
        h = {"what": r["what"], "kind": r["kind"], "day": r["weekday"][:3],
             "hour": r["hour"], "answer": r["answer"]}
        if r["her_words"]:
            h["she_said"] = r["her_words"][:100]
        if r["festival"]:
            h["during"] = r["festival"]
        out.append({k: v for k, v in h.items() if v not in (None, "")})
    return out


def patterns(user_id: str, now_slot: str = "", weekday: str = "",
             days: int = 60) -> Dict:
    """What has worked, by kind: at this part of the day, and on this weekday.

    {"at_this_time": {"sangeet": "2 yes, 0 not now, 0 no"}, ...}. Only kinds
    with at least one answer; an offer still open says nothing yet.
    """
    def _tally():
        return defaultdict(lambda: {"yes": 0, "not_now": 0, "no": 0, "silent": 0})

    by_slot, by_day = _tally(), _tally()
    for r in rows(user_id, days=days):
        a, k = r["answer"], r["kind"] or "?"
        key = ("yes" if a in _YES else "not_now" if a in _NO_NOW
               else "no" if a in _NO_THIS else "silent" if a == "no_response" else None)
        if key is None:
            continue
        if now_slot and r["slot"] == now_slot:
            by_slot[k][key] += 1
        if weekday and r["weekday"] == weekday:
            by_day[k][key] += 1

    def _say(t):
        return {k: (f"{v['yes']} yes, {v['not_now']} not now, {v['no']} no"
                    + (f", {v['silent']} no reply" if v["silent"] else ""))
                for k, v in t.items()}

    out = {}
    if by_slot:
        out["at_this_time_of_day"] = _say(by_slot)
    if by_day:
        out[f"on_{weekday.lower()}s"] = _say(by_day)
    return out

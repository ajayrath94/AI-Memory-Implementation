"""
CATEGORIES — what kind of interest a thing is, and what may be done with it.

Keys only. No display names: those are UI strings and live in the app's i18n
files, so "sangeet" renders as Music, संगीत or ਸੰਗੀਤ according to what the
person picked. Same rule as cluster labels — the backend reasons in one stable
vocabulary and the interface speaks their language.

The properties matter because interests are not interchangeable. Suggesting a
singer adjacent to one someone likes is welcome; suggesting a religion adjacent
to theirs is not. Gardening has no artefact an API can fetch. A film is a
two-hour commitment where a song is three minutes, so a yes means less.
"""
from typing import Optional, Dict, List

EXPAND = "expand"   # a known liking implies related ones — Kishore to Rafi
DEEPEN = "deepen"   # stay on the same thing, get more specific
FULFIL = "fulfil"   # never suggest anything new, only serve what they named


CATEGORIES: Dict[str, dict] = {
    "sangeet": {
        "string_key": "setup.interests.music",
        "askable":    True,
        "mode":       EXPAND,
        "shareable":  True,
        # The best category to experiment in: adjacency is well understood, the
        # artefact is three minutes long, and a wrong guess costs nothing. Most
        # of what the system learns about someone's reactions will come from
        # here.
        "explore":    0.6,
    },
    "khana": {
        "string_key": "setup.interests.food",
        "askable":    True,
        # Adjacency in food is personal in a way music is not. Someone who likes
        # dal khichdi has not signalled an interest in "similar cuisines" — they
        # have signalled something about comfort and what their mother made.
        "mode":       DEEPEN,
        "shareable":  True,
        "explore":    0.4,
    },
    "dekhna": {
        "string_key": "setup.interests.watch",
        "askable":    True,
        "mode":       EXPAND,
        "shareable":  True,
        # Expands like music, but agreeing to watch something is a two-hour
        # commitment, so acceptance is weaker evidence of enthusiasm.
        "explore":    0.3,
    },
    "bhakti": {
        "string_key": "setup.interests.faith",
        "askable":    True,
        # Never expanded. This is also the category the extractor got wrong most
        # often, inferring Hinduism from the word "namaste" eight separate
        # times. Serve what they named and nothing else.
        "mode":       FULFIL,
        "shareable":  True,
        "explore":    0.0,
    },
    "shauk": {
        "string_key": "setup.interests.hobby",
        "askable":    True,
        # Gardening leads to more gardening. The useful move is specificity, not
        # breadth, and there is often no fetchable artefact at all — which is
        # fine, an offer can be a remark.
        "mode":       DEEPEN,
        "shareable":  False,
        "explore":    0.3,
    },
}

# Where the extractor's entity_type lands.
TYPE_TO_CATEGORY = {
    "artist": "sangeet",
    "media":  "dekhna",
    "food":   "khana",
    "hobby":  "shauk",
    "belief": "bhakti",
}

_PILLAR_FOR = {
    "sangeet": "ENTERTAINMENT",
    "dekhna":  "ENTERTAINMENT",
    "khana":   "GENERAL",
    "bhakti":  "GENERAL",
    "shauk":   "GENERAL",
}


def category_for(entity_type: str = "", pillar: str = "") -> Optional[str]:
    if entity_type and entity_type in TYPE_TO_CATEGORY:
        return TYPE_TO_CATEGORY[entity_type]
    if pillar == "ENTERTAINMENT":
        return "sangeet"
    return None


def may_expand(category: str) -> bool:
    return (CATEGORIES.get(category) or {}).get("mode") == EXPAND


def explore_tolerance(category: str) -> float:
    """How willing to offer something uncertain. Zero means never guess."""
    return float((CATEGORIES.get(category) or {}).get("explore", 0.0))


def askable() -> List[str]:
    return [k for k, v in CATEGORIES.items() if v.get("askable")]


# ── writing what they named ───────────────────────────────────────────────────

def record_declared_interest(user_id: str, category: str, text: str) -> Optional[str]:
    """
    Store something the person named as an interest.

    Goes through the same extraction path a spoken preference does, so
    "ਲਤਾ ਮੰਗੇਸ਼ਕਰ" becomes a cluster labelled "Lata Mangeshkar" with her own
    text kept alongside it — the canonical form for matching, hers for saying
    back to her.

    Marked source=declared in attributes for two reasons. The cleaner skips
    those, so a stated preference cannot be swept as junk for the crime of only
    being mentioned once. And the declared layer reads exactly this to tell what
    someone said from what was merely noticed about them.
    """
    text = (text or "").strip()
    if not text or category not in CATEGORIES:
        return None

    try:
        from memory.profile_enricher import _extract_propositions, _upsert_cluster
        from memory.entity_resolver import resolve
    except Exception as e:
        print(f"[Categories] imports failed: {e}")
        return None

    # Bare, not wrapped in a sentence: with a full sentence the extractor reads
    # the SPEAKER as the subject and the thing as the object, which is how a
    # Punjabi routine label came back as "self".
    label, etype = text, ""
    try:
        for p in (_extract_propositions(text, user_id) or []):
            subj = (p.get("subject") or "").strip()
            if subj and subj.lower() not in ("self", "user"):
                label, etype = subj, (p.get("entity_type") or "").strip()
                break
            obj = (p.get("object") or "").strip()
            if obj:
                label, etype = obj, (p.get("entity_type") or "").strip()
                break
    except Exception as e:
        print(f"[Categories] canonicalise failed for {text!r}: {e}")

    pillar = _PILLAR_FOR.get(category, "GENERAL")

    try:
        res = resolve(label, etype or "other", pillar, user_id)
        name = res.get("name") or label
        cid = _upsert_cluster(
            user_id, name, pillar,
            # Full strength: they said it outright. An inferred interest has to
            # accumulate; a stated one should not have to.
            1.0,
            res.get("embedding"),
            {"source": "declared", "category": category, "label_native": text},
            # Its own cluster. Two entries merge only if she types the same
            # thing twice, and the screen shows her what is already there.
            resolve_into=False,
        )
        if cid:
            _mark_preference(user_id, cid, name, text, pillar)
        return cid
    except Exception as e:
        print(f"[Categories] store failed for {text!r}: {e}")
        return None


def _mark_preference(user_id: str, cluster_id: str, label: str,
                     native: str, pillar: str):
    """A declared interest is a preference with positive sentiment — the same
    shape "mujhe Lata pasand hai" produces, so computed_interests picks it up
    without needing a special case."""
    try:
        from supabase_store import get_client
        from memory.profile_enricher import recompute_cluster_trajectory
        get_client().table("user_behavioral_events").insert({
            "user_id": user_id, "cluster_id": cluster_id,
            "pillar": pillar, "sub_pillar": "declared",
            "value": label, "surface_form": native[:200],
            "strength": 1.0, "sentiment": 1.0, "salience": 0.8,
            "event_type": "likes", "relationship_type": "preference",
            "source": "setup",
        }).execute()
        recompute_cluster_trajectory(user_id, cluster_id)
    except Exception as e:
        print(f"[Categories] preference event failed: {e}")

# ── when each kind of thing can be offered ────────────────────────────────────
# Against her declared rhythm, never a fixed clock. Someone who eats dinner at
# 21:00 should get food suggestions at 20:00, and the reason user_patterns
# exists is so that is knowable.
#
#   before_meal   the N minutes before a meal she declared
#   waking        any time she is normally up
#   evening       after her last meal, before wind-down
#   daylight      and only when she is at home

WHEN = {
    "khana":   {"rule": "before_meal", "lead_min": 90},
    # A song is three minutes and fits anywhere she is awake. This is why it is
    # also the best category to experiment in.
    "sangeet": {"rule": "waking"},
    # Two hours of attention. Not before bed, not in the middle of her day.
    "dekhna":  {"rule": "evening"},
    # Gardening needs light, and a hobby suggestion at her daughter's house is
    # useless — she is not there.
    "shauk":   {"rule": "daylight", "home_only": True},
    # Whatever she declared, whenever she declared it. Never adjacent, never
    # inferred, and never at a time we chose for her.
    "bhakti":  {"rule": "declared_only"},
}


def _mins(hhmm: str) -> int:
    try:
        h, m = str(hhmm)[:5].split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return -1


def offerable_now(category: str, now_min: int, rhythm: dict,
                  at_home: bool = True) -> bool:
    """Can this category sensibly be offered at this minute of her day?

    A hard filter rather than a ranking penalty: a wrong-time offer is worse
    than no offer, and the cadence design treats silence as a correct answer.
    """
    spec = WHEN.get(category)
    if not spec:
        return True                       # unknown category: do not block it

    rule = spec.get("rule")

    if rule == "declared_only":
        return False                      # only ever served, never suggested

    if spec.get("home_only") and not at_home:
        return False

    wake  = _mins((rhythm or {}).get("wake") or "07:00")
    sleep = _mins((rhythm or {}).get("sleep") or "22:00")
    if sleep < wake:                      # someone who sleeps after midnight
        sleep += 24 * 60

    if rule == "waking":
        # Not in the first hour after waking or the last before sleeping —
        # she is getting the day started, or winding down.
        return wake + 60 <= now_min <= sleep - 60

    if rule == "daylight":
        return max(wake + 60, 7 * 60) <= now_min <= min(sleep - 60, 18 * 60)

    if rule == "before_meal":
        lead  = int(spec.get("lead_min", 90))
        meals = (rhythm or {}).get("meals") or {}
        if not meals:
            # No declared meals. Falling back to a fixed clock would be the
            # thing this rule exists to avoid, so decline rather than guess.
            return False
        for at in meals.values():
            m = _mins(at)
            if m >= 0 and (m - lead) <= now_min <= m:
                return True
        return False

    if rule == "evening":
        # After her last meal, with an hour before sleep.
        meals = [_mins(v) for v in ((rhythm or {}).get("meals") or {}).values()]
        last  = max([m for m in meals if m >= 0] or [19 * 60])
        return last <= now_min <= sleep - 60

    return True


def busy_with_routine(now_min: int, rhythm: dict, window: int = 30) -> bool:
    """Is she in the middle of something she told us about?

    Offering during her evening walk is not a timing error in the same way as
    food at 9pm — it is interrupting.
    """
    for r in (rhythm or {}).get("routines") or []:
        m = _mins(r.get("at") or "")
        if m >= 0 and abs(now_min - m) <= window:
            return True
    return False

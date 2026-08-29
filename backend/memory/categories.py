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

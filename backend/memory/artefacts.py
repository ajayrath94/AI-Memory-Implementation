"""
ARTEFACTS — turning a subject into something she can act on.

The flow already picked what to offer and could compose a sentence about it, but
the two ends never met: pick_suggestion chose a cluster and handed the label to
the composer as text, so someone who likes Kishore Kumar was offered "Kishore
Kumar" as a topic rather than a song she could tap and hear. That is a
conversation about an interest, not an offer.

The fetchers already existed and already take a query — /music, /recipes,
/search. What was missing is anything joining the picker to them.

WHAT EACH CATEGORY CAN BE GIVEN
  sangeet  a specific song, with a link
  dekhna   a specific film or clip
  khana    a recipe, filtered against her conditions by the route itself
  shauk    a seasonal tip, via search — often nothing, which is fine
  bhakti   nothing. Fulfil-only: serve what she named, never fetch around it.

Returning None is a normal outcome, not a failure. An offer can be a remark —
"aaj bagiche mein kuch naya laga?" needs no artefact — and a fetch that half
works is worse than one that does not run.
"""
import os
from typing import Optional, Dict

# Timeout kept short: this runs while a proactive message is being composed,
# and a slow fetch is worse than no artefact.
_TIMEOUT = 8


def _call(path: str, params: Dict[str, str]) -> Optional[dict]:
    """Call our own integration route in-process rather than over HTTP.

    Going out and back through the network to reach a route in the same
    application would add a hop, a timeout and an auth header for nothing.
    """
    try:
        import urllib.parse
        if path == "music":
            from routes.integrations import get_music_recommendations
            return get_music_recommendations(params["user_id"], query=params.get("query"))
        if path == "recipes":
            from routes.integrations import get_recipes
            return get_recipes(params["user_id"], query=params.get("query"), number=3)
        if path == "search":
            from routes.integrations import web_search
            return web_search(params["user_id"], q=params.get("query", ""))
    except Exception as e:
        print(f"[Artefact] {path} failed: {e}")
    return None


def _music(user_id: str, subject: str) -> Optional[dict]:
    # "songs" rather than the bare name: searching an artist returns hour-long
    # compilations, and the offer should be one thing she can finish.
    data = _call("music", {"user_id": user_id, "query": f"{subject} best song"})
    videos = (data or {}).get("videos") or []
    if not videos:
        return None
    v = videos[0]
    return {
        "kind":  "song",
        "title": v.get("title"),
        "url":   v.get("youtube_url"),
        "thumb": v.get("thumbnail"),
    }


def _film(user_id: str, subject: str) -> Optional[dict]:
    data = _call("music", {"user_id": user_id, "query": f"{subject} movie scene"})
    videos = (data or {}).get("videos") or []
    if not videos:
        return None
    v = videos[0]
    return {
        "kind":  "clip",
        "title": v.get("title"),
        "url":   v.get("youtube_url"),
        "thumb": v.get("thumbnail"),
    }


def _recipe(user_id: str, subject: str) -> Optional[dict]:
    # The route filters against her conditions itself — low sodium for blood
    # pressure, low sugar for diabetes — so a food suggestion is safe by
    # construction rather than by the composer remembering to be careful.
    data = _call("recipes", {"user_id": user_id, "query": subject})
    recipes = (data or {}).get("recipes") or []
    if not recipes:
        return None
    r = recipes[0]
    return {
        "kind":  "recipe",
        "title": r.get("title"),
        "url":   r.get("sourceUrl") or r.get("url"),
        "thumb": r.get("image"),
        "note":  r.get("why_fits"),
    }


def _tip(user_id: str, subject: str) -> Optional[dict]:
    """Hobbies rarely have an artefact. A seasonal tip is the closest thing, and
    often there is nothing worth saying — which is a fine answer."""
    data = _call("search", {"user_id": user_id, "query": f"{subject} tip this season India"})
    answer = (data or {}).get("answer")
    if not answer or len(answer) < 20:
        return None
    return {"kind": "tip", "title": answer[:200], "url": None, "thumb": None}


_FETCHERS = {
    "sangeet": _music,
    "dekhna":  _film,
    "khana":   _recipe,
    "shauk":   _tip,
    # bhakti has none on purpose. It is fulfil-only: serve what she named,
    # never fetch something adjacent. Getting that wrong is not an
    # unhelpful suggestion, it is an offensive one.
}


def fetch_artefact(user_id: str, category: str, subject: str) -> Optional[dict]:
    """Something specific she can act on, or None.

    None is common and expected. The caller falls back to naming the subject,
    which is what the system did before this existed.
    """
    fn = _FETCHERS.get(category)
    if not fn or not subject:
        return None
    try:
        got = fn(user_id, subject)
        if got:
            print(f"[Artefact] {category}/{subject!r} -> {got['kind']}: "
                  f"{str(got.get('title'))[:60]}")
        return got
    except Exception as e:
        print(f"[Artefact] fetch failed for {category}/{subject!r}: {e}")
        return None


def as_hint(artefact: Optional[dict], subject: str) -> str:
    """The line the composer is given.

    The URL goes in. I had assumed a link inside a sentence would read as an
    advertisement — but MessageBubble already extracts the id, strips the URL
    from the displayed text, and renders a tappable player. So including it is
    what makes the offer actionable, and she never sees the raw link.
    """
    if not artefact:
        return (f"Offer this specifically: {subject}. Mention nothing else "
                f"they like.")

    kind  = artefact.get("kind")
    title = (artefact.get("title") or "").strip()
    url = artefact.get("url") or ""
    tail = (f"\nEnd the message with this link on its own, nothing after it: "
            f"{url}") if url else ""

    if kind == "song":
        return (f"Offer this one song: \"{title}\". They like {subject}. "
                f"Say it the way someone would who thought of it just now — "
                f"do not describe it as a recommendation." + tail)
    if kind == "clip":
        return (f"Offer this: \"{title}\", from {subject}. Brief and warm."
                + tail)
    if kind == "recipe":
        note = artefact.get("note")
        return (f"Suggest making this: \"{title}\". They like {subject}."
                + (f" It suits them because {note}." if note else "")
                + " One line, as a thought rather than an instruction.")
    if kind == "tip":
        return (f"They enjoy {subject}. This is worth passing on, in your own "
                f"words and much shorter: {title}")
    return f"Offer this specifically: {subject}."

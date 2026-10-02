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
        # Which meal is coming. The picker allows a food offer in the ninety
        # minutes before a declared meal — and then the composer said "lunch ke
        # liye" at 18:18, when the meal 72 minutes away was dinner. It had no
        # way to know.
        meal = _next_meal_label(subject)
        return (f"Offer this specifically: {subject}. Mention nothing else "
                f"they like."
                + (f" If you name a meal, it is {meal} — nothing else is close."
                   if meal else ""))

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


def _axis_query(axis: str, facts: dict, subject: str) -> Optional[str]:
    """A search built from a verified fact, or None.

    None whenever the fact is missing or unverified — falling back to the
    subject itself, which is what an offer did before axes existed.
    """
    v = (facts or {}).get("verified") or {}

    if axis == "music":
        who = v.get("music")
        # "hit songs" rather than the bare name: searching a composer returns
        # hour-long compilations, and an offer should be one thing she can
        # finish.
        return f"{who} hit songs" if who else None

    if axis == "cast":
        cast = v.get("cast") or []
        # The lead, not the whole cast. A search for six names returns nothing
        # anybody made.
        return f"{cast[0]} best songs" if cast else None

    if axis == "director":
        who = v.get("director")
        return f"{who} movie songs" if who else None

    if axis == "era":
        # A film has a year; a singer has a span. "1946–1987" becomes the
        # decade they were most associated with, which is what someone means
        # by "us zamane ke gaane".
        year = v.get("year")
        if year:
            return f"{year} hindi film songs"
        span = v.get("years_active")
        span = span[0] if isinstance(span, list) and span else span
        if span:
            start = str(span)[:4]
            if start.isdigit():
                decade = f"{start[:3]}0s"
                return f"{decade} hindi film songs"
    return None


def fetch_along_axis(user_id: str, cluster: dict) -> Optional[dict]:
    """Something one step from what she named, in a direction she follows.

    Returns None when no axis is live, no verified fact supports it, or the
    search comes back empty — and the caller offers the subject itself, which
    is the behaviour this improves on rather than replaces.
    """
    attrs = cluster.get("attributes") if isinstance(cluster.get("attributes"), dict) else {}
    facts = attrs.get("facts") or {}
    cat   = attrs.get("category") or ""
    label = cluster.get("label") or ""

    if cat not in ("sangeet", "dekhna") or not facts.get("verified"):
        return None

    try:
        from memory.axes import live_axes
        axes = live_axes(user_id)
    except Exception as e:
        print(f"[Artefact] axis read failed: {e}")
        return None
    if not axes:
        return None

    for axis in axes:
        query = _axis_query(axis, facts, label)
        if not query:
            continue

        got = _music(user_id, query)
        if not got:
            continue

        # What it is and why, so the composer can say the connection rather
        # than presenting an unexplained song. "Sholay ka sangeet unhi ka tha"
        # is the whole difference between a recommendation and a thought.
        got["via_axis"]   = axis
        # An artist has years_active where a film has a year, so the era hint
        # read "from ." with a hole where the fact should be.
        ver = facts.get("verified") or {}
        got["via_fact"] = (
            ver.get("music") if axis == "music" else
            ver.get("cast") if axis == "cast" else
            ver.get("director") if axis == "director" else
            ver.get("year") or ver.get("years_active") if axis == "era" else ""
        ) or ""
        got["via_source"] = label
        print(f"[Artefact] {label!r} --{axis}--> {str(got.get('title'))[:50]}")
        return got

    return None


def axis_hint(artefact: dict) -> str:
    """The line for the composer when an offer travelled an axis.

    The connection is the point. Offering an R. D. Burman song to someone who
    likes Sholay is unremarkable unless she is told why — and told in a way
    that sounds like remembering rather than reciting.
    """
    fact = artefact.get("via_fact")
    fact = ", ".join(fact[:1]) if isinstance(fact, list) else fact
    src  = artefact.get("via_source")
    import html
    # YouTube titles arrive HTML-escaped — "1940&#39;s" — and the companion
    # should not be reading entities aloud.
    title = html.unescape((artefact.get("title") or "").strip())
    url   = artefact.get("url") or ""
    tail  = (f"\nEnd the message with this link on its own, nothing after it: "
             f"{url}") if url else ""

    axis = artefact.get("via_axis")
    if axis == "music":
        return (f"They like \"{src}\". {fact} wrote its music, and this is "
                f"another of his: \"{title}\". Mention the connection — that "
                f"is the whole reason it is worth offering — but say it as "
                f"something you just remembered." + tail)
    if axis == "cast":
        return (f"They like \"{src}\", which starred {fact}. This is "
                f"another of his: \"{title}\". Say the connection lightly."
                + tail)
    if axis == "director":
        return (f"They like \"{src}\", directed by {fact}. This is another "
                f"of his: \"{title}\"." + tail)
    if axis == "era":
        return (f"They like \"{src}\" from {fact}. This is from around the "
                f"same time: \"{title}\". Mention the era, not the year."
                + tail)
    return f"Offer this: \"{title}\"." + tail


def _next_meal_label(subject: str = "") -> Optional[str]:
    """The meal actually approaching, in her own schedule."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from memory.declared import get_declared
        d = get_declared("default")
        tz = ZoneInfo(d.place.timezone)
        now = datetime.now(tz)
        now_min = now.hour * 60 + now.minute
        best, gap = None, 10 ** 6
        for name, at in (d.rhythm.meals or {}).items():
            try:
                h, m = str(at)[:5].split(":")
                mins = int(h) * 60 + int(m)
            except Exception:
                continue
            if 0 <= mins - now_min < gap:
                best, gap = name, mins - now_min
        return best
    except Exception:
        return None


def _dietary(user_id: str) -> str:
    """What she cannot or would not be offered — for the prompt, never for her.

    Read from her conditions and her faith. The rule is the same as the knee:
    it decides what is generated and is never named in the message.
    """
    bits = []
    try:
        from memory.profile_store import get_user_profile
        p = get_user_profile(user_id) or {}
        h = p.get("health") or {}
        blob = " ".join(str(x) for x in
                        (h.get("conditions") or []) + (h.get("medications") or [])
                        ).lower()

        if any(w in blob for w in ("blood pressure", "bp", "hypertension",
                                   "amlodipine")):
            bits.append("nothing heavily salted or deep fried")
        if any(w in blob for w in ("diabet", "sugar", "metformin")):
            bits.append("nothing sweet")
        if any(w in blob for w in ("thyroid", "thyronorm")):
            bits.append("go easy on raw cabbage and soya")

        food = p.get("food") or {}
        likes = " ".join(str(x) for x in (food.get("likes") or [])).lower()
        avoid = " ".join(str(x) for x in (food.get("avoids") or [])).lower()
        # Only when she has said so. Assuming a Hindu woman is vegetarian is
        # exactly the kind of guess that ends trust in one message — and this
        # one eats chicken.
        if "veg" in avoid or any(m in avoid for m in
                                 ("chicken", "mutton", "fish", "egg", "meat")):
            bits.append("vegetarian only")
        else:
            # Neither, by default. 'chicken' appearing in her likes might be
            # one meal the extractor caught, not a preference — and offering
            # meat to a vegetarian is a serious mistake where offering
            # vegetarian food to someone who eats meat is no mistake at all.
            # Whether she can eat meat TODAY, which is a different question
            # from whether she is vegetarian. Shravan, Tuesdays, her own
            # Sunday — all of it is a date, not a flag.
            try:
                from memory.diet import can_eat_meat_today
                v = can_eat_meat_today(user_id)
                bits.append("she eats meat" if v["ok"]
                            else "nothing with meat, and do not say why")
            except Exception as _de:
                print(f"[Adjacent] diet read failed: {_de}")
                bits.append("nothing with meat")

        # A fasting day is not a day for it, whatever she usually eats.
        try:
            from memory.festivals import today as _festival_today
            f = _festival_today()
            if f and f.get("fasting"):
                bits.append(f"today is {f['name']} and many people fast — "
                            f"nothing heavy, and no meat")
        except Exception:
            pass

        # Seventy, not thirty.
        bits.append("nothing very rich or very spicy")
    except Exception as e:
        print(f"[Adjacent] dietary read failed: {e}")
    return "; ".join(bits)


def adjacent(user_id: str, label: str, category: str = "") -> list:
    """Three or four things one step from this. Cached forever.

    Not "similar" — adjacent. Who sang with him, what the dish actually is,
    what else that film's director made. Things she would recognise as
    connected rather than as an algorithm's opinion.
    """
    if not label:
        return []

    try:
        from supabase_store import get_client
        db = get_client()
        # Cached on the cluster. Who Kishore Kumar sang with does not change.
        rows = (db.table("interest_clusters").select("id,attributes")
                .eq("user_id", user_id).ilike("label", label)
                .limit(1).execute()).data or []
        if rows:
            a = rows[0].get("attributes")
            a = a if isinstance(a, dict) else {}
            if a.get("adjacent"):
                return list(a["adjacent"])
    except Exception as e:
        print(f"[Adjacent] cache read failed: {e}")
        rows = []

    diet = _dietary(user_id) if category == "khana" else ""
    diet_line = f"\n\nFor food only: {diet}." if diet else ""

    prompt = f"""Someone elderly in India likes this: "{label}"

Name three or four things that sit NEXT to it — things she would recognise as
connected, not things an algorithm calls similar.

JSON only: {{"adjacent": ["...", "..."]}}

  a singer   -> who they sang with, their music director, a contemporary she
                would know
  a film     -> its songs, its director's other films, its lead's other films
  a cuisine  -> actual dishes from it, by name. Nobody eats "Chinese food".
  a hobby    -> what someone who does it also does, or a thing it needs
  a place    -> not applicable. Return an empty list.

Specific, and nameable. "Old Hindi songs" is not a thing to offer; "Lata
Mangeshkar" is. Use the name she would use — Hindi words in Hindi.

Nothing she cannot have.{diet_line}

No prose."""

    try:
        from llm import ask
        import json as _j
        raw = ask(prompt, max_tokens=200).replace("```json", "").replace("```", "")
        out = [str(x).strip()[:60] for x in
               (_j.loads(raw.strip()).get("adjacent") or []) if str(x).strip()]
        out = out[:4]
    except Exception as e:
        print(f"[Adjacent] failed for {label!r}: {e}")
        return []

    if out and rows:
        try:
            a = rows[0].get("attributes")
            a = a if isinstance(a, dict) else {}
            a["adjacent"] = out
            db.table("interest_clusters").update(
                {"attributes": a}).eq("id", rows[0]["id"]).execute()
        except Exception as e:
            print(f"[Adjacent] cache write failed: {e}")

    print(f"[Adjacent] {label} -> {', '.join(out)}")
    return out


def adjacent_hint(user_id: str, picked: dict) -> str:
    """One thing next to what was drawn, that she has not been offered before.

    Returns "" often, and that is fine — the caller falls back to offering the
    subject itself, which is what it did before.
    """
    label = (picked or {}).get("label") or ""
    attrs = picked.get("attributes") if isinstance(picked.get("attributes"), dict) else {}
    cat = attrs.get("category") or ""
    if not label:
        return ""

    options = adjacent(user_id, label, cat)
    if not options:
        return ""

    # Not one she has already been offered. The whole point is that it is new.
    try:
        from supabase_store import get_client
        from datetime import datetime, timezone, timedelta
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        seen = {str(r.get("label") or "").lower() for r in
                (get_client().table("suggestions").select("label")
                 .eq("user_id", user_id).gte("created_at", since)
                 .limit(60).execute()).data or []}
        options = [o for o in options if o.lower() not in seen] or options
    except Exception:
        pass

    import random
    pick = random.choice(options)
    return (f"\n\nThey like {label}, and {pick} sits right next to it. Offer "
            f"{pick} — because of {label}, which is the reason it is worth "
            f"mentioning. Not 'you might also like': a person would say why.")


def what_to_offer(user_id: str, picked: dict) -> dict:
    """What to actually put in front of her, from an interest she has.

    Returns {kind, subject, with_, why} — kind is "paired", "alone" or
    "subject". The composer phrases it; this only decides.
    """
    label = (picked or {}).get("label") or ""
    attrs = picked.get("attributes") if isinstance(picked.get("attributes"), dict) else {}
    cat = attrs.get("category") or ""
    if not label:
        return {"kind": "subject", "subject": "", "with_": "", "why": ""}

    plain = {"kind": "subject", "subject": label, "with_": "",
             "why": "nothing adjacent worth offering"}

    options = adjacent(user_id, label, cat)
    if not options:
        return plain

    from datetime import datetime, timezone, timedelta
    scored = []
    try:
        from supabase_store import get_client
        db = get_client()
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

        # What has been offered, and what she did about it.
        past = (db.table("suggestions").select("label,reaction,created_at")
                .eq("user_id", user_id).gte("created_at", since)
                .limit(80).execute()).data or []
        week = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        # And what she has raised herself, which is worth more than a list
        # saying the same thing.
        hers = {str(r.get("subject") or "").lower() for r in
                (db.table("subject_mentions").select("subject")
                 .eq("user_id", user_id).limit(300).execute()).data or []}
    except Exception as e:
        print(f"[Offer] history read failed: {e}")
        past, hers, week = [], set(), ""

    for o in options:
        low = o.lower()
        score = 1.0
        for p in past:
            if str(p.get("label") or "").lower() != low:
                continue
            if str(p.get("created_at") or "") >= week:
                score = -1.0           # offered this week; not again
                break
            r = str(p.get("reaction") or "")
            if r == "no_response":
                score -= 0.4           # she let it pass
            elif r == "declined":
                score -= 1.0           # she said no
            elif r == "accepted":
                score += 0.5           # she took it up
        if any(low in h or h in low for h in hers):
            score += 0.8               # she has said this herself
        scored.append((score, o))

    scored.sort(reverse=True)
    best, pick = scored[0] if scored else (-1.0, "")
    if best <= 0 or not pick:
        return plain

    # Paired when the connection is the point — a singer and a singer, a film
    # and its songs. Alone when pairing would be strained: a dish is not
    # offered "along with" a cuisine, it IS the cuisine.
    paired = cat in ("sangeet", "dekhna")
    return {
        "kind": "paired" if paired else "alone",
        "subject": pick,
        "with_": label if paired else "",
        "why": f"{pick} sits next to {label}",
    }


def offer_hint(user_id: str, picked: dict) -> str:
    """The line for the composer. It decides the words; this decides the thing."""
    o = what_to_offer(user_id, picked)
    if not o["subject"]:
        return ""

    if o["kind"] == "paired":
        return (f"\n\nOffer {o['subject']}, BECAUSE of {o['with_']} — they "
                f"go together, and that connection is the reason it is worth "
                f"mentioning. Not 'you might also like'; a person would say "
                f"why.")
    if o["kind"] == "alone":
        return (f"\n\nOffer {o['subject']}. They like {picked.get('label')}, "
                f"and this is the same kind of thing — but offer THIS, not "
                f"that.")
    return ""

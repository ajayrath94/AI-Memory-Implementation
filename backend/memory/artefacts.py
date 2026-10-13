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
        # The SUBJECT is what to say; the title is only what the link points
        # at. A YouTube title is written for a search engine — "Gulabi
        # Aankhen Jo Teri Dekhi | Rajesh Khanna, Nanda | The Train (1970) |
        # Mohd Rafi | Superhit Song" went out verbatim as a markdown link,
        # pipes and year and all, because this handed it over as the thing
        # to offer.
        return (f"Offer this one song: {subject}. Name it that way — not "
                f"whatever the link is called, which is written for a "
                f"search engine and reads like one. "
                f"Say it the way someone would who thought of it just now — "
                f"do not describe it as a recommendation." + tail)
    if kind == "clip":
        return (f"Offer this: {subject}. Name it that way, not whatever the "
                f"link is called. Brief and warm." + tail)
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
        # What her health and her own words mean for a dish — from the
        # model, in any language. These were English word lists ("bp",
        # "veg", "chicken"), and read `avoids` while the food tool writes
        # `avoid`, so what she said she does not eat never reached here.
        from memory.food_rules import rules as _food_rules, raw_line as _raw
        fr = _food_rules(user_id)
        bits.extend(fr.get("offer_rules") or [])
        if fr.get("doctor_decides"):
            bits.append("nothing their doctor would need to approve")
        if fr.get("never"):
            bits.append("never: " + ", ".join(fr["never"]))
        if not fr.get("ok") and _raw(fr):
            bits.append(_raw(fr))

        # Only when she has said so. Assuming a Hindu woman is vegetarian is
        # exactly the kind of guess that ends trust in one message — and this
        # one eats chicken.
        if fr.get("vegetarian") is True:
            bits.append("vegetarian only")
        else:
            # Whether she can eat meat TODAY is a different question from
            # whether she is vegetarian. Shravan, Tuesdays, her own Sunday —
            # all of it is a date, not a flag.
            try:
                from memory.diet import can_eat_meat_today
                v = can_eat_meat_today(user_id)
                if v["ok"] and fr.get("vegetarian") is False:
                    bits.append("she eats meat")
                elif not v["ok"]:
                    bits.append("nothing with meat, and do not say why")
                else:
                    # Not said either way: offering meat to a vegetarian is a
                    # serious mistake, offering vegetarian food is none.
                    bits.append("nothing with meat")
            except Exception as _de:
                print(f"[Adjacent] diet read failed: {_de}")
                bits.append("nothing with meat")

        # A fasting day is not a day for it, whatever she usually eats.
        # Every day it runs, and only a festival she keeps: festivals.today()
        # knew the first day of Navratri and nothing about the other eight.
        try:
            from memory.festival_brief import for_user as _festival_for
            f = _festival_for(user_id)
            if f and f.get("fasting"):
                if f.get("eaten_instead"):
                    bits.append(f"it is {f['name']}, day {f['day_of']} of "
                                f"{f['days']}, and the fast avoids "
                                f"{f.get('fast_avoids') or 'certain foods'}: "
                                f"only dishes made from "
                                f"{f['eaten_instead']}")
                else:
                    bits.append(f"it is {f['name']} and many people fast — "
                                f"nothing heavy, and no meat")
        except Exception as _fe:
            print(f"[Adjacent] festival read failed: {_fe}")

        # Seventy, not thirty.
        bits.append("nothing very rich or very spicy")
    except Exception as e:
        print(f"[Adjacent] dietary read failed: {e}")
    return "; ".join(bits)


def _fast_dishes(user_id, label, fast, who, rows, db, cache_key) -> list:
    """Dishes for a fast she keeps, near what she loves where the fast allows.

    Asked as its own question, then checked: anything that breaks the fast is
    struck by a second, narrow question, because one grain dish offered during
    a grain fast costs more trust than nine days of nothing.
    """
    import json as _j
    from llm import ask
    avoids = fast.get("fast_avoids") or "certain foods"
    allowed = fast.get("eaten_instead") or ""
    prompt = f"""Someone elderly in India loves "{label}".{who}
Today they are keeping the {fast['name']} fast (day {fast.get('day_of')} of {fast.get('days')}).
The fast avoids: {avoids}.
People eat instead: {allowed}.

Name three or four dishes they could have TODAY that keep this fast. As close
to "{label}" as the fast allows — a fasting dish from their own region's
kitchen if there is one — and otherwise fasting dishes they would know.
Every dish must be made only from what the fast allows. A dish that
normally contains anything the fast avoids is not allowed, however it is
usually served.

Nothing very rich, fried or salty: they are elderly.

JSON only:
{{"adjacent": [{{"what": "<dish name>", "when": "before_meal", "kind": "khana", "lang": "none"}}]}}"""
    out = []
    try:
        raw = (ask(prompt, max_tokens=300) or "").replace("```json", "").replace("```", "")
        for x in (_j.loads(raw[raw.find("{"):raw.rfind("}") + 1]).get("adjacent") or []):
            what = str((x or {}).get("what") or "").strip()[:60]
            if what:
                out.append({"what": what, "when": "before_meal",
                            "kind": "khana", "lang": "none"})
    except Exception as e:
        print(f"[Adjacent] fast dishes failed for {label!r}: {e}")
        return []

    # The check. Narrow on purpose: one question, yes or no per dish.
    if out:
        listed = "\n".join(f"{i + 1}. {o['what']}" for i, o in enumerate(out))
        try:
            raw = ask(f"""During {fast['name']} a fast avoids: {avoids}.
What people eat instead: {allowed}.

{listed}

Which of these dishes keep that fast, as they are normally made for it?
Made from what people eat instead, it keeps it — including the flours and
millets kept for fasting (kuttu, singhara, rajgira, samak or sama rice,
sabudana, makhana), even where the word "rice" or "atta" is in the name.
A dish whose usual recipe contains anything the fast avoids does NOT keep
it: rice, wheat, semolina, lentil batter, onion, garlic.

Reply with the numbers that keep it, separated by commas, or NONE.""",
                      max_tokens=20) or ""
            import re as _re
            ok = {int(n) - 1 for n in _re.findall(r"\d+", raw)}
            struck = [o["what"] for i, o in enumerate(out) if i not in ok]
            if struck:
                print(f"[Adjacent] struck during {fast['name']}: {struck}")
            out = [o for i, o in enumerate(out) if i in ok]
        except Exception as e:
            print(f"[Adjacent] fast check failed, offering none: {e}")
            out = []

    out = out[:4]
    if out and rows:
        try:
            a = rows[0].get("attributes")
            a = a if isinstance(a, dict) else {}
            a[cache_key] = out
            db.table("interest_clusters").update(
                {"attributes": a}).eq("id", rows[0]["id"]).execute()
        except Exception as e:
            print(f"[Adjacent] cache write failed: {e}")
    print(f"[Adjacent] {label} during {fast['name']} -> "
          + ", ".join(o["what"] for o in out))
    return out


def adjacent(user_id: str, label: str, category: str = "") -> list:
    """Three or four things one step from this. Cached forever.

    Not "similar" — adjacent. Who sang with him, what the dish actually is,
    what else that film's director made. Things she would recognise as
    connected rather than as an algorithm's opinion.
    """
    if not label:
        return []

    # Food during a fast she keeps is its own list. The cache is forever, so
    # without this the nine days of Navratri would be served the dishes
    # worked out on an ordinary Tuesday, every one of them refused by the
    # picker, and she would be offered no food at all until Dussehra. Kept
    # under the festival's name, so next year's Navratri starts from it.
    cache_key = "adjacent_v3"
    fast = None
    if category == "khana":
        try:
            from memory.festival_brief import for_user as _festival_for
            _f = _festival_for(user_id)
            if _f and _f.get("fasting") and _f.get("she_keeps_it"):
                fast = _f
            if _f and _f.get("fasting"):
                cache_key = "adjacent_fast_" + "".join(
                    c for c in _f["name"].lower() if c.isalnum())[:40]
        except Exception as _fe:
            print(f"[Adjacent] festival read failed: {_fe}")

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
            # v2 carries when each one belongs. The old key was a list
            # of strings and is left alone rather than migrated — it will
            # simply be refilled.
            # v3 carries what KIND of thing each one is. v2 entries took
            # the kind of the interest they came from, so Tagore's
            # Gitanjali, a book, counted as music because it was reached
            # from Rabindrasangeet, and the music search found a Telugu
            # film song. v2 is left alone and refilled, once per interest.
            if a.get(cache_key):
                return list(a[cache_key])
    except Exception as e:
        print(f"[Adjacent] cache read failed: {e}")
        rows = []

    diet = _dietary(user_id) if category == "khana" else ""
    diet_line = f"\n\nFor food only: {diet}." if diet else ""

    # Who, so "next to it" stays inside their own world. Without it a Tamil
    # Carnatic listener was given Hindi bhajans twice in one day.
    who = ""
    try:
        from memory.declared import get_declared
        d = get_declared(user_id)
        who = (f" They live in {d.place.home or 'India'} and speak "
               f"{d.language.pref}.")
    except Exception:
        pass

    if fast:
        # Its own question. Asked "what sits next to South Indian food" with
        # the fast as a footnote, the model answered the question it was
        # asked — Rava Idli, Maddur Vada, Bisi Bele Bath, every one of them
        # grain — and the picker rightly refused all three, so a woman keeping
        # Navratri would have been offered no food for nine days.
        return _fast_dishes(user_id, label, fast, who, rows, db, cache_key)

    prompt = f"""Someone elderly in India likes this: "{label}".{who}

Name three or four things that sit NEXT to it — things she would recognise as
connected, not things an algorithm calls similar. Stay inside her own
tradition and language: what someone from where she lives, who loves this,
would actually know.

JSON only:
{{"adjacent": [{{"what": "...", "when": "anytime", "kind": "sangeet", "lang": "tamil"}}, ...]}}

  lang   the language it is in, one lowercase word (tamil, hindi, urdu,
         bengali, sanskrit, telugu, english...). "none" for a dish, a hobby,
         or music without words.

  kind   what kind of thing THIS one is, whatever it was reached from:
           sangeet  a song or a piece of music, always "<title> by <singer>"
           dekhna   a film or a serial
           khana    a dish, by its name alone: never "<dish> by <shop>"
                    and never a restaurant. Nobody has checked a shop
                    exists near her.
           shauk    something to do or read: a book, a hobby, a game
           bhakti   a prayer, a stotram, a devotional recitation

  when   where it belongs in an ordinary day, so it is offered at a moment
         it suits rather than whenever a gap appears:

           before_meal   a dish or a recipe — useless an hour after lunch
           evening       a film, a serial: it needs two hours and a settled
                         evening
           morning       gardening, a walk, anything done while it is cool
           anytime       a song, a short video — three minutes, any gap

         The thing decides, not its category. A film and a film song are
         both "watching" and belong at different hours.

  a singer   -> a song SUNG BY SOMEONE ELSE. Not one of his own with
                another name attached.

                "Roop Tera Mastana by Mohammad Rafi" and "Chala Jata
                Hoon by Lata Mangeshkar" both went out for Kishore Kumar.
                They are Kishore's songs. The instruction to name someone
                else was met by changing the credit, which is worse than
                repeating him — she has known these records for fifty
                years and would see it at once.

                Pick a song the OTHER person actually sang. A duet
                partner singing their own hit, a contemporary, someone
                from the same films. If you are not sure who sang it,
                choose a different song you are sure about.

                Always "<song> by <other artist>" — a real song title and
                a real name, never a description like "their music director"
                or a bare name, both of which search to an hour-long
                compilation.

                No examples here: with them the model returned the same two
                songs whatever the subject was, including for the artist who
                sang them.

                A name alone searches to an hour-long compilation — "Best Of
                Mohammad Rafi Hit Songs | Old Hindi Superhit Songs" — and
                that is not an offer to a woman of seventy. It is also three
                artists in one title, and the message then names all three
                instead of the one chosen.

                Same reason a cuisine becomes a dish below.
  a film     -> its songs, its director's other films, its lead's other films
  a cuisine  -> actual dishes from it, by name. Nobody eats "Chinese food".
  a hobby    -> something she could DO, not something she would buy.
                Gardening gives a plant worth growing or a thing worth
                planting now — not khad, gamla and khurpi, which are a
                shopping list.
  a place    -> not applicable. Return an empty list.

Specific, and nameable. "Old Hindi songs" is not a thing to offer; "Lata
Mangeshkar" is. Use the name she would use — Hindi words in Hindi.

Nothing she cannot have.{diet_line}

No prose."""

    try:
        from llm import ask
        import json as _j
        raw = ask(prompt, max_tokens=300).replace("```json", "").replace("```", "")
        got = _j.loads(raw.strip()).get("adjacent") or []
        out = []
        for x in got:
            # v1 returned bare strings and the cache may still hold some.
            if isinstance(x, str):
                if x.strip():
                    out.append({"what": x.strip()[:60], "when": "anytime"})
                continue
            what = str((x or {}).get("what") or "").strip()[:60]
            if not what:
                continue
            when = str((x or {}).get("when") or "anytime").strip().lower()
            if when not in ("before_meal", "evening", "morning", "anytime"):
                when = "anytime"
            kind = str((x or {}).get("kind") or "").strip().lower()
            if kind not in ("sangeet", "dekhna", "khana", "shauk", "bhakti"):
                kind = ""
            lang = str((x or {}).get("lang") or "").strip().lower()[:20]
            out.append({"what": what, "when": when, "kind": kind,
                        "lang": lang})
        out = out[:4]
    except Exception as e:
        print(f"[Adjacent] failed for {label!r}: {e}")
        return []

    if out and rows:
        try:
            a = rows[0].get("attributes")
            a = a if isinstance(a, dict) else {}
            a[cache_key] = out
            db.table("interest_clusters").update(
                {"attributes": a}).eq("id", rows[0]["id"]).execute()
        except Exception as e:
            print(f"[Adjacent] cache write failed: {e}")

    print(f"[Adjacent] {label} -> "
          + ", ".join(f"{o['what']} ({o['when']})" for o in out))
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
            elif r in ("declined", "declined_preference"):
                score -= 1.0           # she said no to the thing
            # declined_timing: no to the hour, not the thing. No penalty;
            # affinity.py moves it to a better time instead.
            elif r == "accepted":
                score += 0.5           # she took it up
        # Whole subjects, not substrings. "dosa" is in her mentions and
        # "padosan" contains it, so a dish she ate boosted a 1968 film and
        # Kishore Kumar expanded to Padosan six times out of six.
        if low in hers:
            score += 0.8               # she has said this herself
        scored.append((score, o))

    # Shuffle before sorting, so ties are not broken alphabetically. Every
    # option scores 1.0 until she has been offered one, and sort(reverse)
    # then picks the last name every time — Kishore Kumar expanded to Lata,
    # Rafi, R.D. Burman and Padosan, and Padosan won twice in a row.
    import random as _r
    _r.shuffle(scored)
    scored.sort(key=lambda x: -x[0])
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

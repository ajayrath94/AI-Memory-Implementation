"""
INTEGRATIONS — External API routes
All real-time data Nancy needs to make recommendations:

  GET /integrations/weather/{user_id}     — current weather at user's location
  GET /integrations/news/{user_id}        — news based on user interests
  GET /integrations/places/{user_id}      — nearby hospitals/pharmacies
  GET /integrations/music/{user_id}       — Spotify recommendations
  GET /integrations/context/{user_id}     — all context in one call (for recommendation engine)
"""

import os
import json
import urllib.request
import urllib.parse
from fastapi import APIRouter

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────

def http_get(url: str, headers: dict = {}) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as res:
        return json.loads(res.read())


def get_user_location(user_id: str) -> tuple:
    """Get user's active location (current if traveling, home otherwise)."""
    try:
        from memory.location_engine import get_active_location
        loc = get_active_location(user_id)
        return loc["location"], loc.get("lat"), loc.get("lng")
    except Exception:
        return "Mumbai", 19.076, 72.877


def get_user_interests(user_id: str) -> dict:
    """Get user's interests from profile."""
    try:
        from memory.profile_store import get_user_profile
        profile   = get_user_profile(user_id) or {}
        interests = profile.get("interests", {})
        cultural  = profile.get("cultural_context", {})
        return {
            "sports":      interests.get("sports", []),
            "music":       interests.get("music", []),
            "religion":    cultural.get("religion", ""),
            "region":      cultural.get("region", ""),
            "language":    profile.get("language_pref", "hinglish"),
        }
    except Exception:
        return {}


# ── Weather ────────────────────────────────────────────────────────────────────

@router.get("/weather/{user_id}")
def get_weather(user_id: str, location: str = None):
    """
    Get current weather for user's location (or an explicit override).
    Used by schedule engine for daily check-ins and by the chat tool-calling layer.
    e.g. "Aaj Delhi mein bahut garmi hai — paani peete rehna"
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return {"error": "OPENWEATHER_API_KEY not set"}

    lat = lng = None
    if not location:
        location, lat, lng = get_user_location(user_id)

    try:
        # Coordinates are more precise than a city-name lookup, and let the
        # stored location name be as granular as we like (e.g. "Vesu, Surat")
        # without breaking the weather query.
        if lat is not None and lng is not None:
            url = (f"https://api.openweathermap.org/data/2.5/weather"
                   f"?lat={lat}&lon={lng}&appid={api_key}&units=metric")
        else:
            encoded = urllib.parse.quote(location)
            url = (f"https://api.openweathermap.org/data/2.5/weather"
                   f"?q={encoded}&appid={api_key}&units=metric")
        data     = http_get(url)

        return {
            "location":    data.get("name"),
            "country":     data.get("sys", {}).get("country"),
            "temp_c":      data.get("main", {}).get("temp"),
            "feels_like":  data.get("main", {}).get("feels_like"),
            "humidity":    data.get("main", {}).get("humidity"),
            "description": data.get("weather", [{}])[0].get("description"),
            "icon":        data.get("weather", [{}])[0].get("main"),
            "wind_speed":  data.get("wind", {}).get("speed"),
            # No advice line: it was fixed Hinglish ("Thand hai — garam
            # kapde pehenna"), and Nancy repeated it to everyone. She has
            # the numbers and writes the advice herself, in their language.
        }
    except Exception as e:
        return {"error": str(e), "location": location}


# ── News ───────────────────────────────────────────────────────────────────────

# The kinds of news on the Khabar sheet. Each is a Google News section for
# India (en-IN): the stories Indian papers lead with, already sorted by
# section. A keyword search for "sports" on the general news API brought
# back whatever in the world mentioned the word.
NEWS_KINDS = {
    "india":         "NATION",
    "sports":        "SPORTS",
    "entertainment": "ENTERTAINMENT",
    "world":         "WORLD",
    # "local" is her city's page, worked out from where she is.
}
_CITY: dict = {}        # "lat,lng" -> city, so the lookup is made once


def _city_of(user_id: str) -> str:
    """The city she is in now ("Bengaluru"), for local news.

    Her stored place can be as fine as "Vyalikaval HBCS Layout, Bengaluru";
    the city is Google's `locality` for her coordinates, not a guess at
    which part of that string is the city.
    """
    place, lat, lng = get_user_location(user_id)
    if lat is not None and lng is not None:
        k = f"{round(float(lat), 2)},{round(float(lng), 2)}"
        if k in _CITY:
            return _CITY[k]
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            try:
                data = http_get("https://maps.googleapis.com/maps/api/geocode/json"
                                f"?latlng={lat},{lng}&result_type=locality&key={api_key}")
                for res in data.get("results") or []:
                    for comp in res.get("address_components") or []:
                        if "locality" in (comp.get("types") or []):
                            _CITY[k] = comp.get("long_name")
                            return _CITY[k]
            except Exception as e:
                print(f"[News] city lookup failed: {e}")
    return str(place or "").split(",")[-1].strip() or str(place or "")


def _google_news(url: str, limit: int = 6) -> list:
    """Stories from a Google News RSS feed: title, source, link, time."""
    import xml.etree.ElementTree as ET
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=6) as res:
        root = ET.fromstring(res.read())
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        src_el = item.find("source")
        source = (src_el.text or "").strip() if src_el is not None and src_el.text else ""
        # Titles end with " - The Hindu"; the source is given separately.
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)].strip()
        if not title:
            continue
        out.append({
            "title":     title,
            "source":    source,
            "url":       (item.findtext("link") or "").strip(),
            "published": (item.findtext("pubDate") or "").strip(),
        })
        if len(out) >= limit:
            break
    return out


def news_of_kind(user_id: str, kind: str) -> dict:
    """The day's stories of one kind: local, india, sports, entertainment,
    world."""
    kind = (kind or "").strip().lower()
    tail = "hl=en-IN&gl=IN&ceid=IN:en"
    if kind == "local":
        city = _city_of(user_id)
        url = ("https://news.google.com/rss/headlines/section/geo/"
               f"{urllib.parse.quote(city)}?{tail}")
        where = city
    elif kind in NEWS_KINDS:
        url = f"https://news.google.com/rss/headlines/section/topic/{NEWS_KINDS[kind]}?{tail}"
        where = "India"
    else:
        return {"error": f"unknown kind {kind!r}", "articles": []}
    try:
        stories = _google_news(url)
        if not stories and kind == "local":
            # A city Google News has no page for: search its name instead.
            stories = _google_news("https://news.google.com/rss/search"
                                   f"?q={urllib.parse.quote(where)}+when:2d&{tail}")
    except Exception as e:
        print(f"[News] {kind} feed failed: {e}")
        return {"error": str(e), "kind": kind, "articles": []}
    return {
        "kind":     kind,
        "where":    where,
        "articles": stories,
        "count":    len(stories),
        "note": ("Tell three or four of these, one or two sentences each, in "
                 "her language. After each, put its link as [source](url) on "
                 "its own line so she can tap to read it. Never invent a story "
                 "or a detail that is not in the title."),
    }


@router.get("/news/{user_id}")
def get_news(user_id: str, topic: str = None, kind: str = None):
    """
    Get personalized news based on user interests.
    Cricket fan → sports news. Religious → India spiritual news.

    kind (local / india / sports / entertainment / world) is the Khabar
    sheet's choice, and reads that section instead of searching.
    """
    if kind and not topic:
        return news_of_kind(user_id, kind)

    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return {"error": "NEWS_API_KEY not set"}

    interests = get_user_interests(user_id)
    articles  = []

    # Determine search query from interests
    queries = []
    # Whatever sports she follows, as she named them — not only the two
    # that were on a list.
    sports  = interests.get("sports", [])
    for sp in [str(x).strip() for x in sports if str(x).strip()][:2]:
        queries.append(f"{sp} news")

    region = interests.get("region", "")
    if region:
        queries.append(f"{region} India news")

    # Default to India news
    if topic:
        queries = [topic]
    if not queries:
        queries.append("India news today")

    try:
        for query in queries[:2]:  # Max 2 queries
            encoded = urllib.parse.quote(query)
            url     = f"https://newsapi.org/v2/everything?q={encoded}&language=en&pageSize=5&sortBy=publishedAt&apiKey={api_key}"
            data    = http_get(url)
            for article in data.get("articles", [])[:3]:
                articles.append({
                    "title":       article.get("title", ""),
                    "description": article.get("description", ""),
                    "source":      article.get("source", {}).get("name", ""),
                    "url":         article.get("url", ""),
                    "published":   article.get("publishedAt", ""),
                    "topic":       query,
                })

        return {
            "articles":  articles[:5],
            "interests": interests,
            "count":     len(articles),
        }
    except Exception as e:
        return {"error": str(e), "articles": []}


# ── Places ─────────────────────────────────────────────────────────────────────

@router.get("/places/{user_id}")
def place_details(place_id: str) -> dict:
    """The full address and the phone number, for one place.

    A second call, so only made for something she might actually ring — the
    hospital on the emergency screen, not every restaurant near her.
    """
    import os
    api_key = os.getenv("GOOGLE_API_KEY")
    if not (api_key and place_id):
        return {}
    try:
        url = ("https://maps.googleapis.com/maps/api/place/details/json"
               f"?place_id={place_id}"
               "&fields=formatted_address,formatted_phone_number,name,opening_hours"
               f"&key={api_key}")
        r = (http_get(url) or {}).get("result") or {}
        return {
            "name":    r.get("name"),
            "address": r.get("formatted_address"),
            "phone":   (r.get("formatted_phone_number") or "").replace(" ", ""),
            "open":    (r.get("opening_hours") or {}).get("open_now"),
        }
    except Exception as e:
        print(f"[Places] details failed: {e}")
        return {}

# Google place types that can be passed as `type`. Anything else is a name or
# a description ("Murugan Idli Shop", "South Indian breakfast") and is searched
# as a keyword only: an unknown type makes Google refuse the whole request.
_PLACE_TYPES = {
    "hospital", "pharmacy", "doctor", "dentist", "physiotherapist", "restaurant",
    "cafe", "bakery", "park", "hindu_temple", "church", "mosque",
    "supermarket", "grocery_or_supermarket", "store", "bank", "atm",
    "post_office", "library", "shopping_mall", "movie_theater", "tourist_attraction",
}
_PLACE_ALIASES = {"clinic": "doctor", "temple": "hindu_temple", "mandir": "hindu_temple",
                  "chemist": "pharmacy", "medical store": "pharmacy",
                  "grocery": "grocery_or_supermarket", "cinema": "movie_theater"}


_CALL_TYPES = {"pharmacy", "doctor", "hospital", "dentist", "physiotherapist"}
_PHONES: dict = {}


def _phone_of(place_id: str) -> str:
    """The place's phone number, from Details, remembered by place id."""
    if not place_id:
        return ""
    if place_id not in _PHONES:
        _PHONES[place_id] = (place_details(place_id) or {}).get("phone") or ""
    return _PHONES[place_id]


def _km(lat1, lng1, lat2, lng2):
    """Straight-line distance in km. Roads are longer; it is said as "about"."""
    from math import radians, sin, cos, asin, sqrt
    try:
        la1, lo1, la2, lo2 = map(radians, (float(lat1), float(lng1), float(lat2), float(lng2)))
    except (TypeError, ValueError):
        return None
    a = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


def get_nearby_places(user_id: str, place_type: str = "hospital",
                      location: str = None, radius: int = 5000,
                      with_phone: bool = False, keep: int = 5):
    """
    Real places near her, nearest first, each with how far it is.

    place_type is a Google type (hospital, pharmacy, restaurant, park...) or a
    name or description ("Murugan Idli Shop", "South Indian breakfast").

    Distance is always from HER: where she is now, or home. She asked "kitna
    door hai" about an idli place and was given three names and three ratings
    and no distance, because nothing here worked one out. Google returns each
    place's coordinates, so it costs nothing extra.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_API_KEY not set"}

    # Where she is, whatever area is being searched: "how far" means from her.
    her_place, her_lat, her_lng = get_user_location(user_id)

    if location:
        lat, lng = None, None          # explicit place given, geocode it below
    else:
        location, lat, lng = her_place, her_lat, her_lng

    asked = str(place_type or "hospital").strip()
    gtype = _PLACE_ALIASES.get(asked.lower(), asked.lower())
    gtype = gtype if gtype in _PLACE_TYPES else None

    try:
        # Use stored lat/lng if available, otherwise geocode
        if not lat or not lng:
            query    = location if "india" in location.lower() else f"{location}, India"
            encoded  = urllib.parse.quote(query)
            geo_url  = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded}&key={api_key}"
            geo_data = http_get(geo_url)

            if not geo_data.get("results"):
                return {
                    "error":          "Location not found",
                    "location":       location,
                    "google_status":  geo_data.get("status"),
                    "google_message": geo_data.get("error_message"),
                }

            loc_data = geo_data["results"][0]["geometry"]["location"]
            lat, lng = loc_data["lat"], loc_data["lng"]

        if not (her_lat and her_lng):
            her_lat, her_lng = lat, lng

        def _search(r):
            # keyword AND type for a kind of place. With type alone, a 2km
            # search for a hospital returned a chemist, an eye clinic, a
            # diagnostics lab and Herbalife — Google pads the results when
            # exact matches are thin, and the padding does not care what you
            # asked for.
            #
            # 5km, not 2km. In an emergency she would travel further than two
            # kilometres anyway, and a real hospital five minutes away beats a
            # chemist next door.
            url = (f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
                   f"?location={lat},{lng}&radius={r}"
                   f"&keyword={urllib.parse.quote(asked)}&key={api_key}")
            if gtype:
                url += f"&type={gtype}"
            return http_get(url).get("results", [])

        results = _search(radius)
        widened = False
        # A named place may simply not be within 5 km. Look further once, and
        # say so, rather than answering "nothing found" about a shop that
        # exists across town.
        if not results and not gtype and radius < 15000:
            results = _search(15000)
            widened = bool(results)

        places = []
        for p in results[:10]:
            plat = p.get("geometry", {}).get("location", {}).get("lat")
            plng = p.get("geometry", {}).get("location", {}).get("lng")
            d = _km(her_lat, her_lng, plat, plng)
            places.append({
                "name":    p.get("name"),
                # Kept so Details can be called for a real address and a
                # phone number. Nearby Search returns neither — "vicinity" is
                # a fragment, and there is no number at all, so a hospital on
                # an emergency screen had nothing to dial.
                "place_id": p.get("place_id"),
                # Google's own types, so "is this a bar" is a fact about the
                # place, not a guess from words in its name.
                "types":   p.get("types") or [],
                "address": p.get("vicinity"),
                "rating":  p.get("rating"),
                # How many people rated it: a 5.0 from three people is not a
                # 4.6 from nine hundred.
                "reviews": p.get("user_ratings_total"),
                "open":    p.get("opening_hours", {}).get("open_now"),
                "lat":     plat,
                "lng":     plng,
                # Straight line, so "about". Walking at an older person's
                # pace, about 4 km an hour: 15 minutes a kilometre.
                "distance_km": round(d, 1) if d is not None else None,
                "walk_min":    int(round(d * 15)) if d is not None else None,
            })

        places.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 1e9)
        places = places[:max(1, keep)]

        # A map link for each, so she can tap it and go.
        for p in places:
            p["map_url"] = ("https://www.google.com/maps/search/?api=1&query="
                            + urllib.parse.quote(p.get("name") or "")
                            + (f"&query_place_id={p['place_id']}" if p.get("place_id") else ""))

        # A number to ring, for the places she would ring: the chemist, the
        # doctor, the hospital — by Google's own type for the place, not what
        # was searched (a chemist search pads its results with other shops).
        # One Details call each, for the nearest three only, and remembered.
        callable_ = [p for p in places
                     if with_phone and set(p.get("types") or []) & _CALL_TYPES][:3]
        for p in callable_:
            ph = _phone_of(p.get("place_id"))
            if ph:
                p["phone"] = ph
                p["call_url"] = "tel:" + ph

        return {
            "location":   location,
            "place_type": place_type,
            "places":     places,
            "count":      len(places),
            "distance_from": her_place,
            "note": ("Distances are straight-line from where she is; by road it "
                     "is a little more. Say them as 'about'. Say whether each is "
                     "open now when `open` is given. For each place you name, "
                     "put [its name](map_url) on its own line, and when it has a "
                     "call_url, [📞 its name](call_url) on the next line, so she "
                     "can tap to see it or ring it."
                     + (" Nothing within 5 km, so this looked up to 15 km."
                        if widened else "")),
        }
    except Exception as e:
        return {"error": str(e), "location": location}


# ── YouTube Music ──────────────────────────────────────────────────────────────

# ── YouTube search cache ─────────────────────────────────────────────────────
# A search costs 100 of the 10,000 units YouTube allows a day: about a
# hundred searches, for every user and every test run together. The same
# songs come up again and again — "Lag Ja Gale" is offered to half of
# everyone — and on 12 Oct a few test runs used the day up by eleven at night:
# every search after that returned 429 and every song offer was struck.
#
# So a search is made once and kept. A recording does not change; a video
# can be taken down, so a cached answer is trusted for a month and then
# looked up again. Failures are never cached — a 429 is about today, not
# about the song.
YT_CACHE_DAYS = 30
_YT_MEMO: dict = {}


def _yt_key(query: str) -> str:
    return " ".join(str(query or "").lower().split())[:300]


def _yt_cached(query: str):
    k = _yt_key(query)
    if k in _YT_MEMO:
        return _YT_MEMO[k]
    try:
        from datetime import datetime, timedelta, timezone
        from supabase_store import get_client
        since = (datetime.now(timezone.utc) - timedelta(days=YT_CACHE_DAYS)).isoformat()
        rows = (get_client().table("youtube_cache").select("videos")
                .eq("query", k).gte("fetched_at", since)
                .limit(1).execute()).data or []
        if rows and isinstance(rows[0].get("videos"), list):
            _YT_MEMO[k] = rows[0]["videos"]
            return _YT_MEMO[k]
    except Exception as e:
        print(f"[YouTube] cache read failed: {str(e)[:100]}")
    return None


def _yt_remember(query: str, videos: list) -> None:
    k = _yt_key(query)
    _YT_MEMO[k] = videos
    try:
        from datetime import datetime, timezone
        from supabase_store import get_client
        get_client().table("youtube_cache").upsert({
            "query": k, "videos": videos,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="query").execute()
    except Exception as e:
        print(f"[YouTube] cache write failed: {str(e)[:100]}")


@router.get("/music/{user_id}")
def get_music_recommendations(user_id: str, query: str = None):
    """
    Get YouTube music/video recommendations. If a query is given (from chat
    tool-calling, e.g. "Bhag Milkha Bhag songs"), search that directly.
    Otherwise fall back to inferring from user interests.
    """
    api_key   = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_API_KEY not set", "videos": []}

    if not query:
        interests = get_user_interests(user_id)
        music     = interests.get("music", [])
        religion  = interests.get("religion", "")
        language  = interests.get("language", "hinglish")

        if music:
            query = music[0]  # e.g. "Kishore Kumar songs"
        elif religion == "Hindu":
            query = "bhajan Hindi devotional songs"
        elif "hi" in language or "hinglish" in language:
            query = "Bollywood old Hindi songs"
        else:
            query = "Indian classical music"

    cached = _yt_cached(query)
    if cached is not None:
        return {"query": query, "videos": cached, "count": len(cached),
                "cached": True}

    try:
        encoded = urllib.parse.quote(query)
        url     = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={encoded}&type=video&videoCategoryId=10&key={api_key}&maxResults=5&regionCode=IN"
        data    = http_get(url)

        # Which of these will actually play in an embed. Search does not say,
        # so it takes a second call — and without it the player appears, fails,
        # and hands off to the YouTube app, which reads as a crash even though
        # the fallback is working. Music is the most commonly blocked kind,
        # which is most of what gets offered here.
        embeddable = set()
        try:
            ids = ",".join(i.get("id", {}).get("videoId", "")
                           for i in data.get("items", []) if i.get("id", {}).get("videoId"))
            if ids:
                st = http_get(
                    f"https://www.googleapis.com/youtube/v3/videos"
                    f"?part=status&id={ids}&key={api_key}")
                for v in st.get("items", []):
                    if (v.get("status") or {}).get("embeddable"):
                        embeddable.add(v.get("id"))
        except Exception as e:
            print(f"[Integrations] embeddable check failed: {e}")
            embeddable = None      # unknown: let everything through

        videos = []
        for item in data.get("items", []):
            snippet  = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId", "")
            videos.append({
                "title":       snippet.get("title"),
                "channel":     snippet.get("channelTitle"),
                "description": snippet.get("description", "")[:100],
                "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                "thumbnail":   snippet.get("thumbnails", {}).get("medium", {}).get("url"),
                "video_id":    video_id,
                # The app shows a player when this is true and a tap-through
                # card when it is not.
                "embeddable":  (video_id in embeddable) if embeddable is not None else True,
            })

        if videos:
            _yt_remember(query, videos)
        return {
            "query":  query,
            "videos": videos,
            "count":  len(videos),
        }
    except Exception as e:
        # Said plainly in the log: a 429 or 403 here is the day's allowance,
        # not a missing song, and it reads very differently from "not found".
        msg = str(e)
        if "429" in msg or "403" in msg:
            print(f"[YouTube] daily limit reached — {msg[:80]}")
        return {"error": msg, "videos": [], "limited": ("429" in msg or "403" in msg)}


# ── All context in one call ────────────────────────────────────────────────────

@router.get("/context/{user_id}")
def get_full_context(user_id: str):
    """
    One call returns all real-time context for the recommendation engine.
    Weather + top news + nearby places + music — everything Nancy needs.
    """
    weather = get_weather(user_id)
    news    = get_news(user_id)
    music   = get_music_recommendations(user_id)

    return {
        "user_id":  user_id,
        "weather":  weather,
        "news":     {"top_articles": news.get("articles", [])[:3]},
        "music":    {"top_videos": music.get("videos", [])[:3]},
        "places":   {},  # Only fetch on demand (health alert triggers)
    }


# ── Web search (agent) — the long-tail catch-all ────────────────────────────────
# Google Custom Search fetches live web results; Haiku synthesizes a warm, concise
# answer in the user's language. Nancy's voice, current facts, grounded in results
# (Haiku answers FROM the snippets, not its own memory — current + less hallucination).

def _search_web(query: str, num: int = 5) -> list:
    """Brave Search → list of {title, snippet, link}. [] on failure."""
    key = os.getenv("BRAVE_SEARCH_API_KEY")
    if not key:
        print("[Search] BRAVE_SEARCH_API_KEY not set")
        return []
    try:
        q = urllib.parse.quote(query)
        url = f"https://api.search.brave.com/res/v1/web/search?q={q}&count={num}"
        req = urllib.request.Request(url, headers={
            "X-Subscription-Token": key,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=8) as res:
            data = json.loads(res.read())
        out = []
        for item in (data.get("web", {}).get("results") or [])[:num]:
            out.append({
                "title":   item.get("title"),
                "snippet": item.get("description"),
                "link":    item.get("url"),
            })
        return out
    except Exception as e:
        print(f"[Search] Brave search failed: {e}")
        return []


@router.get("/search/{user_id}")
def web_search(user_id: str, q: str):
    """Search the live web + synthesize a warm answer in the user's language.
    The catch-all for 'what is / how do I / is X good for Y' that no fixed
    API covers. Returns {answer, sources}."""
    results = _search_web(q, num=5)
    if not results:
        return {"answer": None, "sources": [], "error": "no search results (check GOOGLE_API_KEY / GOOGLE_SEARCH_ENGINE_ID / CSE web-search config)"}

    # user's language preference (Hinglish default), so the answer matches how they speak
    interests = get_user_interests(user_id)
    lang = interests.get("language", "hinglish")

    snippets = "\n".join(f"- {r['title']}: {r['snippet']}" for r in results if r.get("snippet"))
    prompt = f"""A person asked: "{q}"

Here are current web search results:
{snippets}

Answer their question warmly and concisely, as a caring companion would — not like
a search engine. Base your answer ONLY on these results (don't invent facts). If the
results don't answer it, say so gently. Answer in the user's language: {lang}
(Hinglish = natural mix of Hindi and English, the way an Indian family member speaks).
Keep it to 2-4 short sentences. No bullet points, no links in the text."""

    try:
        from memory.summarizer import _call_haiku
        answer = _call_haiku(prompt, max_tokens=250).strip()
    except Exception as e:
        print(f"[Search] synthesis failed: {e}")
        # fallback: return the top snippet plainly
        answer = results[0].get("snippet") if results else None

    return {
        "answer":  answer,
        "sources": [{"title": r["title"], "link": r["link"]} for r in results[:3]],
        "query":   q,
    }


# ── Recipes (health-aware) ──────────────────────────────────────────────────────
# Spoonacular recipe search, filtered by the user's health conditions:
# high BP -> low sodium, diabetes -> low sugar. Recipes tied to who they are.

def _user_health_filters(user_id: str) -> dict:
    """Read the user's health, region, religion, and any captured food prefs →
    Spoonacular params. Layers TASTE (cuisine/diet/likes) onto HEALTH (sodium/sugar),
    so recipes fit the whole person, not just their condition."""
    try:
        from memory.profile_store import get_user_profile
        profile = get_user_profile(user_id) or {}
    except Exception:
        profile = {}

    health    = profile.get("health", {}) or {}
    interests = profile.get("interests", {}) or {}
    food      = profile.get("food", {}) or {}          # future capture field
    location  = str(profile.get("location", "") or "").lower()
    religion  = " ".join(str(x).lower() for x in (
                    interests.get("religion", []) if isinstance(interests.get("religion"), list)
                    else [interests.get("religion", "")]))

    filters, notes = {}, []

    # Everything below is the model's reading of her profile, in whatever
    # language it was written. These were word lists — "hypertension",
    # "dairy", a list of foreign countries — that missed "hipertensión",
    # "lácteos" and Spain. The values are Spoonacular's own vocabulary.
    try:
        from memory.food_rules import rules as _food_rules
        fr = _food_rules(user_id)
    except Exception as e:
        print(f"[Recipes] food rules failed: {e}")
        fr = {}
    r = fr.get("recipe") or {}
    if r.get("max_sodium"):
        filters["maxSodium"] = r["max_sodium"]
        notes.append("low-salt")
    if r.get("max_sugar"):
        filters["maxSugar"] = r["max_sugar"]
        notes.append("low-sugar")
    if r.get("cuisine"):
        filters["cuisine"] = r["cuisine"]
        notes.append(r["cuisine"])
    if fr.get("vegetarian") is True:
        filters["diet"] = "vegetarian"
        notes.append("vegetarian")
    if r.get("intolerances"):
        filters["intolerances"] = ",".join(r["intolerances"])

    likes = food.get("likes") or []

    return {"filters": filters, "notes": notes, "likes": likes}


@router.get("/recipes/{user_id}")
def get_recipes(user_id: str, query: str = None, number: int = 5):
    """Health-aware recipe suggestions. Reads the user's conditions and filters
    (BP -> low sodium, diabetes -> low sugar). Returns recipes + a why-fits note."""
    # A fast she keeps decides the food, and Spoonacular knows nothing about
    # Navratri: on day three it returned red lentil soup and garlicky kale to
    # a woman whose fast avoids grain, lentils, onion and garlic. So during
    # one, no search — the model is given what the fast allows and suggests
    # from that, in her own kitchen's terms.
    try:
        from memory.festival_brief import for_user as _festival_for
        _f = _festival_for(user_id)
        if _f and _f.get("fasting") and _f.get("she_keeps_it"):
            return {
                "recipes": [],
                "fasting": True,
                "festival": f"{_f['name']}, day {_f.get('day_of')} of {_f.get('days')}",
                "fast_avoids": _f.get("fast_avoids"),
                "eaten_instead": _f.get("eaten_instead"),
                "note": ("She is keeping this fast. Suggest only dishes made from "
                         "what is eaten instead — the usual vrat dishes of her own "
                         "region — nothing with anything the fast avoids. Light, "
                         "low in salt, not fried."),
            }
    except Exception as _fe:
        print(f"[Recipes] festival read failed: {_fe}")

    key = os.getenv("SPOONACULAR_API_KEY")
    if not key:
        return {"error": "SPOONACULAR_API_KEY not set", "recipes": []}

    hf = _user_health_filters(user_id)
    params = {
        "apiKey": key,
        "number": number,
        "addRecipeInformation": "true",
        "fillIngredients": "true",
    }
    if query:
        params["query"] = query
    params.update(hf["filters"])

    try:
        qs = urllib.parse.urlencode(params)
        url = f"https://api.spoonacular.com/recipes/complexSearch?{qs}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NancyAI/1.0)"})
        with urllib.request.urlopen(req, timeout=8) as res:
            data = json.loads(res.read())
        recipes = []
        for r in (data.get("results") or [])[:number]:
            ingredients = [i.get("original") for i in (r.get("missedIngredients", []) + r.get("usedIngredients", []))] \
                          or [i.get("name") for i in (r.get("extendedIngredients") or [])]
            recipes.append({
                "title":        r.get("title"),
                "image":        r.get("image"),
                "ready_in_min": r.get("readyInMinutes"),
                "servings":     r.get("servings"),
                "ingredients":  ingredients[:15],
                "source_url":   r.get("sourceUrl"),
            })
        return {
            "recipes":     recipes,
            "health_note": ", ".join(hf["notes"]) if hf["notes"] else None,
            "query":       query,
        }
    except Exception as e:
        print(f"[Recipes] Spoonacular failed: {e}")
        return {"error": str(e)[:100], "recipes": []}

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
            "advice":      _weather_advice(data),
        }
    except Exception as e:
        return {"error": str(e), "location": location}


def _weather_advice(data: dict) -> str:
    """Generate simple health advice based on weather."""
    temp = data.get("main", {}).get("temp", 25)
    desc = data.get("weather", [{}])[0].get("main", "").lower()

    if temp > 38:
        return "Bahut garmi hai — paani peete rehna, bahar mat jaana"
    elif temp > 32:
        return "Garmi hai — hydrated rehna, dhoop se bachna"
    elif temp < 10:
        return "Thand hai — garam kapde pehenna, chai lo"
    elif "rain" in desc:
        return "Baarish ho rahi hai — bahar jaate waqt chhata le jaana"
    elif "storm" in desc:
        return "Toofan aa sakta hai — ghar pe rehna"
    return "Mausam theek hai"


# ── News ───────────────────────────────────────────────────────────────────────

@router.get("/news/{user_id}")
def get_news(user_id: str, topic: str = None):
    """
    Get personalized news based on user interests.
    Cricket fan → sports news. Religious → India spiritual news.
    """
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return {"error": "NEWS_API_KEY not set"}

    interests = get_user_interests(user_id)
    articles  = []

    # Determine search query from interests
    queries = []
    sports  = interests.get("sports", [])
    if any("cricket" in s.lower() for s in sports):
        queries.append("cricket India")
    if any("football" in s.lower() for s in sports):
        queries.append("football India")

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
def get_nearby_places(user_id: str, place_type: str = "hospital", location: str = None):
    """
    Find nearby hospitals, pharmacies, clinics.
    Used when health alerts fire.
    place_type: hospital | pharmacy | doctor | clinic
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_API_KEY not set"}

    if location:
        lat, lng = None, None          # explicit place given, geocode it below
    else:
        location, lat, lng = get_user_location(user_id)

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

        # Search nearby places
        places_url = (
            f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            f"?location={lat},{lng}&radius=2000&type={place_type}&key={api_key}"
        )
        places_data = http_get(places_url)

        places = []
        for p in places_data.get("results", [])[:5]:
            places.append({
                "name":    p.get("name"),
                "address": p.get("vicinity"),
                "rating":  p.get("rating"),
                "open":    p.get("opening_hours", {}).get("open_now"),
                "lat":     p.get("geometry", {}).get("location", {}).get("lat"),
                "lng":     p.get("geometry", {}).get("location", {}).get("lng"),
            })

        return {
            "location":   location,
            "place_type": place_type,
            "places":     places,
            "count":      len(places),
        }
    except Exception as e:
        return {"error": str(e), "location": location}


# ── YouTube Music ──────────────────────────────────────────────────────────────

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

    try:
        encoded = urllib.parse.quote(query)
        url     = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={encoded}&type=video&videoCategoryId=10&key={api_key}&maxResults=5&regionCode=IN"
        data    = http_get(url)

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
            })

        return {
            "query":  query,
            "videos": videos,
            "count":  len(videos),
        }
    except Exception as e:
        return {"error": str(e), "videos": []}


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

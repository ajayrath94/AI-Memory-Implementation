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
def get_weather(user_id: str):
    """
    Get current weather for user's location.
    Used by schedule engine for daily check-ins.
    e.g. "Aaj Delhi mein bahut garmi hai — paani peete rehna"
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return {"error": "OPENWEATHER_API_KEY not set"}

    location, _, _ = get_user_location(user_id)

    try:
        encoded  = urllib.parse.quote(location)
        url      = f"https://api.openweathermap.org/data/2.5/weather?q={encoded}&appid={api_key}&units=metric"
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
def get_news(user_id: str, category: str = None):
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
def get_nearby_places(user_id: str, place_type: str = "hospital"):
    """
    Find nearby hospitals, pharmacies, clinics.
    Used when health alerts fire.
    place_type: hospital | pharmacy | doctor | clinic
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_API_KEY not set"}

    location, _, _ = get_user_location(user_id)

    try:
        # Use stored lat/lng if available, otherwise geocode
        if lat and lng:
            pass  # Already have coordinates
        else:
            query    = location if "india" in location.lower() else f"{location}, India"
            encoded  = urllib.parse.quote(query)
            geo_url  = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded}&key={api_key}"
            geo_data = http_get(geo_url)

            if not geo_data.get("results"):
                return {"error": "Location not found", "location": location}

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


# ── Spotify Music ──────────────────────────────────────────────────────────────

def _get_spotify_token() -> str:
    """Get Spotify access token via client credentials flow."""
    client_id     = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise Exception("Spotify credentials not set")

    import base64
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data        = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req         = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data    = data,
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type":  "application/x-www-form-urlencoded",
        }
    )
    with urllib.request.urlopen(req, timeout=5) as res:
        return json.loads(res.read())["access_token"]


@router.get("/music/{user_id}")
def get_music_recommendations(user_id: str):
    """
    Get Spotify track recommendations based on user's music interests.
    Kishore Kumar fan → Bollywood classic recommendations.
    """
    try:
        token     = _get_spotify_token()
        interests = get_user_interests(user_id)
        music     = interests.get("music", [])
        language  = interests.get("language", "hinglish")

        # Build search query from music interests
        if music:
            query = music[0]  # e.g. "Kishore Kumar songs"
        elif "hi" in language or "hinglish" in language:
            query = "Bollywood hits"
        else:
            query = "Indian music"

        encoded = urllib.parse.quote(query)
        url     = f"https://api.spotify.com/v1/search?q={encoded}&type=track&limit=5&market=IN"
        data    = http_get(url, headers={"Authorization": f"Bearer {token}"})

        tracks = []
        for track in data.get("tracks", {}).get("items", []):
            tracks.append({
                "name":       track.get("name"),
                "artist":     ", ".join(a["name"] for a in track.get("artists", [])),
                "album":      track.get("album", {}).get("name"),
                "preview_url": track.get("preview_url"),
                "spotify_url": track.get("external_urls", {}).get("spotify"),
            })

        return {
            "query":   query,
            "tracks":  tracks,
            "count":   len(tracks),
        }
    except Exception as e:
        return {"error": str(e), "tracks": []}


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
        "music":    {"top_tracks": music.get("tracks", [])[:3]},
        "places":   {},  # Only fetch on demand (health alert triggers)
    }

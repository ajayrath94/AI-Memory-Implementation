"""
LOCATION INTELLIGENCE ENGINE
Detects location changes, geocodes, surfaces care resources,
notifies caregivers, and feeds the recommendation engine.

Two location types:
  home_location    → permanent, rarely changes
  current_location → temporary, changes when traveling

Triggers:
  "Main X mein rehta/rehti hoon" → home_location
  "Main X mein hoon/gaya/gayi"  → current_location
  "Wapas aa gaya/aayi"          → clear current_location

On location change:
  1. Geocode new location → store lat/lng
  2. Fetch emergency resources (hospital, pharmacy)
  3. Notify caregiver if traveling away from home
  4. Feed into recommendation engine
"""

import os
import json
import urllib.request
import urllib.parse
from typing import Optional, Tuple


# ── Geocoding ──────────────────────────────────────────────────────────────────

def geocode_location(location: str) -> Tuple[Optional[float], Optional[float], str]:
    """
    Geocode a location string to lat/lng using Google Geocoding API.
    Returns (lat, lng, canonical_name)
    Handles misspellings, partial names, Hindi transliterations.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None, None, location

    try:
        # Append India for better results if not already specified
        query   = location if any(c in location.lower() for c in ["india", ",", "delhi", "mumbai", "bangalore", "chennai", "kolkata"]) else f"{location}, India"
        encoded = urllib.parse.quote(query)
        url     = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded}&key={api_key}"

        req  = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read())

        if data.get("results"):
            result       = data["results"][0]
            lat          = result["geometry"]["location"]["lat"]
            lng          = result["geometry"]["location"]["lng"]
            canonical    = result["formatted_address"].split(",")[0].strip()
            return lat, lng, canonical

    except Exception as e:
        print(f"[LocationEngine] Geocoding failed for {location}: {e}")

    return None, None, location


# ── Location type detection ────────────────────────────────────────────────────

def detect_location_type(text: str, classified) -> Tuple[Optional[str], str]:
    """
    Detect if user is mentioning home or current location.
    Returns (location_string, type) where type is 'home', 'current', or 'clear'

    Home signals:   "rehta/rehti hoon", "mera ghar", "hum X mein rehte hain"
    Current signals: "abhi X mein hoon", "X gaya/gayi", "X aa gaya/aayi"
    Clear signals:   "wapas aa gaya", "ghar aa gaya", "wapas hoon"
    """
    t = text.lower()

    # Clear current location signals
    clear_signals = ["wapas aa gaya", "wapas aa gayi", "ghar aa gaya",
                     "ghar aa gayi", "wapas hoon", "back home", "returned"]
    if any(s in t for s in clear_signals):
        return None, "clear"

    # Home location signals
    home_signals = ["rehta hoon", "rehti hoon", "rehte hain", "rehti hai",
                    "mera ghar", "hamara ghar", "i live in", "i stay in",
                    "permanently", "settled in", "based in"]
    is_home = any(s in t for s in home_signals)

    # Current location signals
    current_signals = ["abhi hoon", "abhi main", "currently in", "right now in",
                       "gaya hoon", "gayi hoon", "visiting", "trip mein",
                       "travel kar raha", "travel kar rahi", "aa gaya", "aa gayi"]
    is_current = any(s in t for s in current_signals)

    # Use Haiku to extract the actual location string
    location = _extract_location_from_text(text)

    if not location:
        return None, "unknown"

    if is_home:
        return location, "home"
    elif is_current:
        return location, "current"
    else:
        # Default: if LOCATION modifier is high, treat as current
        if classified.modifiers and "LOCATION" in classified.modifiers:
            return location, "current"
        return None, "unknown"


def _extract_location_from_text(text: str) -> Optional[str]:
    """Use Haiku to extract location mention from text."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp   = client.messages.create(
            model      = "claude-haiku-4-5",
            max_tokens = 50,
            messages   = [{
                "role":    "user",
                "content": f"""Extract ONLY the city/place name from this text. Return just the place name, nothing else. If no place mentioned, return "NONE".

Text: "{text}"

Place name:"""
            }]
        )
        result = resp.content[0].text.strip()
        return None if result == "NONE" or not result else result
    except Exception:
        return None


# ── Update profile location ────────────────────────────────────────────────────

def update_user_location(user_id: str, location: str, location_type: str):
    """
    Geocode location and update user profile.
    Triggers care resources fetch and caregiver notification if needed.
    """
    lat, lng, canonical = geocode_location(location)

    try:
        from supabase_store import get_client
        from memory.profile_store import get_user_profile
        db      = get_client()
        profile = get_user_profile(user_id) or {}

        if location_type == "home":
            db.table("user_profile").update({
                "home_location": canonical,
                "home_lat":      lat,
                "home_lng":      lng,
                "location":      canonical,  # Keep existing field in sync
                "location_updated_at": "now()",
            }).eq("user_id", user_id).execute()
            print(f"[LocationEngine] Updated home location: {canonical} for {user_id}")

        elif location_type == "current":
            home = profile.get("home_location") or profile.get("location")

            db.table("user_profile").update({
                "current_location": canonical,
                "current_lat":      lat,
                "current_lng":      lng,
                "location_updated_at": "now()",
            }).eq("user_id", user_id).execute()
            print(f"[LocationEngine] Updated current location: {canonical} for {user_id}")

            # If traveling away from home — notify caregiver
            if home and canonical and home.lower() not in canonical.lower():
                _notify_caregiver_travel(user_id, canonical, home, profile)

        elif location_type == "clear":
            db.table("user_profile").update({
                "current_location": None,
                "current_lat":      None,
                "current_lng":      None,
                "location_updated_at": "now()",
            }).eq("user_id", user_id).execute()
            print(f"[LocationEngine] Cleared current location for {user_id}")

    except Exception as e:
        print(f"[LocationEngine] Profile update failed: {e}")


# ── Caregiver notification ─────────────────────────────────────────────────────

def _notify_caregiver_travel(user_id: str, current: str, home: str, profile: dict):
    """Notify caregiver when user is traveling away from home."""
    try:
        from memory.alert_engine import get_caregivers_for_user, send_email_alert
        relationships = get_caregivers_for_user(user_id)
        if not relationships:
            return

        name = profile.get("name") or user_id
        alert = {
            "alert_type": "travel",
            "severity":   "low",
            "message":    f"{name} is currently in {current} (home: {home}). "
                          f"{get_companion_name(user_id)} is monitoring and has "
                          f"surfaced local emergency resources.",
            "pillar":     "LOCATION",
        }

        for rel in relationships:
            caregiver = rel.get("caregivers", {})
            email     = rel.get("alert_email") or caregiver.get("email")
            if email:
                send_email_alert(email, caregiver.get("name", "Caregiver"), name, [alert], user_id)
                print(f"[LocationEngine] Travel alert sent to {email}")

    except Exception as e:
        print(f"[LocationEngine] Travel notification failed: {e}")


# ── Get active location ────────────────────────────────────────────────────────

def get_active_location(user_id: str) -> dict:
    """
    Get the most relevant location for API calls.
    Returns current_location if set, otherwise home_location.
    """
    try:
        from memory.profile_store import get_user_profile
        profile = get_user_profile(user_id) or {}

        if profile.get("current_location"):
            return {
                "location": profile["current_location"],
                "lat":      profile.get("current_lat"),
                "lng":      profile.get("current_lng"),
                "type":     "current",
            }
        elif profile.get("home_location"):
            return {
                "location": profile["home_location"],
                "lat":      profile.get("home_lat"),
                "lng":      profile.get("home_lng"),
                "type":     "home",
            }
        elif profile.get("location"):
            return {
                "location": profile["location"],
                "lat":      None,
                "lng":      None,
                "type":     "profile",
            }
    except Exception:
        pass

    return {"location": "Mumbai", "lat": 19.076, "lng": 72.877, "type": "default"}


# ── Main entry point ───────────────────────────────────────────────────────────

def process_location_from_message(text: str, classified, user_id: str):
    """
    Called from profile_enricher after every message.
    Detects location mentions and updates profile accordingly.
    """
    # Only process if LOCATION modifier is present or general message
    if not classified.modifiers or "LOCATION" not in str(classified.modifiers):
        # Still check for obvious location signals in text
        location_words = ["mein hoon", "mein rehta", "mein rehti", "mein gaya",
                         "mein gayi", "wapas", "travel", "visiting", "trip"]
        if not any(w in text.lower() for w in location_words):
            return

    location, loc_type = detect_location_type(text, classified)

    if not location and loc_type != "clear":
        return

    update_user_location(user_id, location or "", loc_type)
    print(f"[LocationEngine] Processed: {location} ({loc_type}) for {user_id}")


# ── GPS (live location from device) ────────────────────────────────────────────

def reverse_geocode(lat: float, lng: float) -> Optional[str]:
    """
    Convert GPS coordinates to a human-readable place name (city level).
    Returns None if lookup fails — callers should keep coords regardless.
    """
    import os, json, urllib.request, urllib.parse

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("[LocationEngine] reverse_geocode: GOOGLE_API_KEY not set")
        return None

    try:
        url = (
            "https://maps.googleapis.com/maps/api/geocode/json"
            f"?latlng={lat},{lng}&key={api_key}"
        )
        with urllib.request.urlopen(url, timeout=5) as res:
            data = json.loads(res.read())

        if data.get("status") != "OK" or not data.get("results"):
            print(f"[LocationEngine] reverse_geocode status={data.get('status')} "
                  f"msg={data.get('error_message')}")
            return None

        # Collect the most useful components across all returned results.
        # Indian addresses often expose the neighbourhood as sublocality_level_1
        # (e.g. "Vesu"), with the city as locality (e.g. "Surat").
        area = city = None
        for result in data["results"]:
            for comp in result.get("address_components", []):
                types = comp.get("types", [])
                if not area and (
                    "sublocality_level_1" in types
                    or "sublocality" in types
                    or "neighborhood" in types
                ):
                    area = comp.get("long_name")
                if not city and "locality" in types:
                    city = comp.get("long_name")
            if area and city:
                break

        if area and city and area.lower() != city.lower():
            return f"{area}, {city}"
        return city or area or data["results"][0].get("formatted_address")

    except Exception as e:
        print(f"[LocationEngine] reverse_geocode failed: {e}")
        return None


def update_location_from_gps(user_id: str, lat: float, lng: float) -> dict:
    """
    Store live device coordinates as the user's current location.

    Coordinates are always saved (they're what the places API actually needs).
    The human-readable name is best-effort — if reverse geocoding fails we keep
    the previous name rather than wiping it, so weather lookups still work.
    """
    if lat is None or lng is None:
        return {"ok": False, "error": "lat and lng are required"}
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return {"ok": False, "error": "coordinates out of range"}

    canonical = reverse_geocode(lat, lng)

    try:
        from supabase_store import get_client
        from memory.profile_store import get_user_profile

        db      = get_client()
        profile = get_user_profile(user_id) or {}

        updates = {
            "current_lat":         lat,
            "current_lng":         lng,
            "location_updated_at": "now()",
        }
        if canonical:
            updates["current_location"] = canonical

        db.table("user_profile").update(updates).eq("user_id", user_id).execute()

        resolved = canonical or profile.get("current_location")
        print(f"[LocationEngine] GPS update for {user_id}: {resolved} ({lat}, {lng})")

        # Reuse existing travel-detection / caregiver notification
        home = profile.get("home_location") or profile.get("location")
        if home and canonical and home.lower() not in canonical.lower():
            try:
                _notify_caregiver_travel(user_id, canonical, home, profile)
            except Exception as e:
                print(f"[LocationEngine] caregiver notify failed: {e}")

        return {"ok": True, "location": resolved, "lat": lat, "lng": lng}

    except Exception as e:
        print(f"[LocationEngine] GPS update failed: {e}")
        return {"ok": False, "error": str(e)}

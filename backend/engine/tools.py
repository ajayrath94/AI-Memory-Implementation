"""
TOOLS — Extensible tool registry for LLM tool-calling.

Add a new tool by adding one entry to TOOL_REGISTRY below. Nothing else
in this file, engine_router.py, or the LiteLLM call site needs to change.

Each entry needs:
  - schema:  OpenAI-format function schema (LiteLLM translates this to
             whatever shape each individual provider actually needs)
  - handler: the real Python function to call when the LLM requests this tool
"""

from routes.integrations import get_weather, get_music_recommendations, get_news, get_nearby_places


# ── Tool schemas (OpenAI format — universal across all LiteLLM providers) ──────

WEATHER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Get current real-time weather for a city. Use this whenever the "
            "user asks about weather, temperature, or conditions anywhere — "
            "do not guess or make up weather data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": (
                        "City name, e.g. 'Bangalore'. If the user doesn't "
                        "specify a city, omit this and their saved location "
                        "will be used instead."
                    ),
                },
            },
            "required": [],
        },
    },
}

MUSIC_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_music",
        "description": (
            "Search YouTube for songs/music videos. Use this whenever the "
            "user asks for song recommendations, wants to listen to "
            "something specific, or mentions a movie/artist/genre they want "
            "music from — do not just describe songs from memory, actually "
            "search for real, current results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The search query, using the user's own words as "
                        "closely as possible, e.g. 'Bhag Milkha Bhag songs' "
                        "or 'Michael Jackson songs'."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}


# ── Registry ─────────────────────────────────────────────────────────────────
# To add a new tool: write its schema above, write its handler in
# routes/integrations.py (or anywhere), add one entry here. Done.

NEWS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_news",
        "description": (
            "Get current real news articles. Use this whenever the user asks "
            "what's happening, wants news on a topic, or asks about recent "
            "events — do not answer from memory, fetch real articles."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "What to search news for, e.g. 'cricket India' or "
                        "'Mumbai weather alert'. Omit for general India news."
                    ),
                },
            },
            "required": [],
        },
    },
}

PLACES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_places",
        "description": (
            "Find real nearby places — hospitals, pharmacies, clinics, "
            "doctors, restaurants, parks. Use whenever the user asks where "
            "something is near them or needs to find a place."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "place_type": {
                    "type": "string",
                    "description": (
                        "Kind of place: hospital, pharmacy, doctor, clinic, "
                        "restaurant, park, etc."
                    ),
                },
                "location": {
                    "type": "string",
                    "description": (
                        "City or area to search near. Omit to use the "
                        "person's saved location."
                    ),
                },
            },
            "required": ["place_type"],
        },
    },
}


TOOL_REGISTRY = {
    "get_weather": {
        "schema":  WEATHER_SCHEMA,
        "handler": lambda args, user_id: get_weather(user_id, args.get("location")),
    },
    "get_music": {
        "schema":  MUSIC_SCHEMA,
        "handler": lambda args, user_id: get_music_recommendations(user_id, args.get("query")),
    },
    "get_news": {
        "schema":  NEWS_SCHEMA,
        "handler": lambda args, user_id: get_news(user_id, args.get("topic")),
    },
    "get_places": {
        "schema":  PLACES_SCHEMA,
        "handler": lambda args, user_id: get_nearby_places(
            user_id,
            args.get("place_type") or "hospital",
            args.get("location"),
        ),
    },
}


def get_tool_schemas() -> list:
    """All tool schemas, in the format LiteLLM/OpenAI expects for `tools=`."""
    return [entry["schema"] for entry in TOOL_REGISTRY.values()]


def execute_tool(name: str, args: dict, user_id: str) -> dict:
    """
    Run a tool by name. Returns the tool's real result, or an error dict
    if the tool isn't found or the call itself fails — never raises, since
    this runs inside the LLM orchestration loop and one bad tool call
    shouldn't crash the whole conversation turn.
    """
    entry = TOOL_REGISTRY.get(name)
    if not entry:
        return {"error": f"Unknown tool: {name}"}
    try:
        return entry["handler"](args, user_id)
    except Exception as e:
        print(f"[Tools] {name} failed: {e}")
        return {"error": str(e)}

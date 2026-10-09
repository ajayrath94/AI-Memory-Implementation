"""
TOOLS — Extensible tool registry for LLM tool-calling.

Add a new tool by adding one entry to TOOL_REGISTRY below. Nothing else
in this file, engine_router.py, or the LiteLLM call site needs to change.

Each entry needs:
  - schema:  OpenAI-format function schema (LiteLLM translates this to
             whatever shape each individual provider actually needs)
  - handler: the real Python function to call when the LLM requests this tool
"""

from routes.integrations import get_weather, get_music_recommendations, get_news, get_nearby_places, web_search, get_recipes
from routes.calendar import get_calendar


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
                        "ONLY set this if the user explicitly names a place in "
                        "their message (e.g. 'weather in Mumbai'). If they say "
                        "'here', 'outside', or name no place at all, OMIT this "
                        "parameter entirely so their live GPS location is used. "
                        "Never copy a location from the profile into this field."
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
                        "What to search news for, as the person asked for it. "
                        "Omit for general India news."
                        # No example topic. "e.g. 'cricket India'" was read as
                        # a hint about what to offer, and a woman who does not
                        # watch cricket was offered cricket scores before she
                        # had said anything about sport. A tool is there when
                        # she asks for it, not a suggestion when she has not.
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


# ── New tool schemas (recipes, search, calendar, food) ──────────────────────────

RECIPES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_recipes",
        "description": (
            "Suggest recipes / meal ideas. Use whenever the user asks what to "
            "cook, wants a recipe, asks 'kya banau', or mentions wanting food "
            "ideas. Automatically filters for their health (low-salt for BP, "
            "low-sugar for diabetes) and taste (vegetarian, Indian cuisine, "
            "their liked dishes) — so just call it, the personalization is "
            "handled. Don't invent recipes from memory; call this for real ones."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Optional. What kind of food, in the user's words, e.g. "
                        "'dinner', 'something light', 'rajma'. Omit for a general suggestion."
                    ),
                },
            },
            "required": [],
        },
    },
}

SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": (
            "Search the live web for a warm, current answer. Use for ANY general "
            "question, current fact, or 'what is / how do I / is X good for Y' "
            "that the other tools (weather, music, news, places, recipes) don't "
            "cover — e.g. health questions, prices, how-tos, general knowledge. "
            "Don't answer from memory when it's something current or factual; search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The question, in the user's own words.",
                },
            },
            "required": ["query"],
        },
    },
}

CALENDAR_ADD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "add_calendar_event",
        "description": (
            "Add an event to the user's calendar. You MUST call this tool (not "
            "just say 'I'll remember') whenever the user mentions an appointment, "
            "visit, or something happening on a date/time (e.g. 'Tuesday ko doctor "
            "hai', 'beta Sunday ko aa raha hai'). Calling this tool is what "
            "actually saves it — saying you'll remember without calling it saves "
            "nothing. For event_at, compute the FULL ISO datetime in the user's "
            "local timezone (India, +05:30) — e.g. 11am Tuesday = that date "
            "T11:00:00+05:30. Call the tool, THEN confirm warmly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title":    {"type": "string", "description": "What the event is, e.g. 'Doctor appointment'."},
                "event_at": {"type": "string", "description": "ISO 8601 datetime, e.g. '2026-08-19T16:00:00'. Infer from what the user said relative to now."},
                "category": {"type": "string", "description": "One of: medical, social, festival, personal. Best guess."},
            },
            "required": ["title", "event_at"],
        },
    },
}

CALENDAR_VIEW_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_calendar",
        "description": (
            "Get the user's upcoming schedule — appointments, reminders, and "
            "recurring routines (meds) — as one timeline. Use when they ask "
            "what's coming up, their schedule, or their day/week."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "How many days ahead to show. Default 7."},
            },
            "required": [],
        },
    },
}

FOOD_PREF_SCHEMA = {
    "type": "function",
    "function": {
        "name": "update_food_prefs",
        "description": (
            "Record the user's food preferences to memory. You MUST call this "
            "tool (not just say you noted it) whenever the user mentions ANY food "
            "preference: a dish they like ('mujhe rajma pasand hai' -> likes), a "
            "dislike or something they don't eat ('karela pasand nahi' -> "
            "dislikes), their diet ('main veg hoon' -> diet), or something they "
            "avoid for allergy/religion ('pyaaz-lehsun nahi khaati' -> avoid). "
            "Calling this tool is what actually saves it — saying 'noted' without "
            "calling it saves nothing. Call it, THEN reply warmly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "likes":    {"type": "array", "items": {"type": "string"}, "description": "Foods/dishes they like."},
                "dislikes": {"type": "array", "items": {"type": "string"}, "description": "Foods they dislike."},
                "diet":     {"type": "string", "description": "e.g. 'vegetarian', 'non-vegetarian', 'vegan'."},
                "avoid":    {"type": "array", "items": {"type": "string"}, "description": "Foods to avoid (allergy/religious), e.g. onion, garlic."},
            },
            "required": [],
        },
    },
}


# ── Handlers for the model-taking functions (build the Pydantic models) ─────────

def _handle_add_calendar(args, user_id):
    from routes.calendar import add_event, CalendarEvent
    ev = CalendarEvent(
        user_id=user_id,
        title=args.get("title", "Event"),
        event_at=args.get("event_at"),
        category=args.get("category") or "personal",
        created_by="elder",
    )
    return add_event(ev)


def _handle_update_food(args, user_id):
    from routes.memory_state import update_food, FoodPrefs
    # smart-merge: append to existing lists rather than replace (auto-capture accumulates)
    from memory.profile_store import get_user_profile
    existing = (get_user_profile(user_id) or {}).get("food", {}) or {}
    def _merge(key):
        old = existing.get(key) or []
        new = args.get(key) or []
        return sorted(set([*old, *new])) if (old or new) else None
    prefs = FoodPrefs(
        likes=_merge("likes"),
        dislikes=_merge("dislikes"),
        avoid=_merge("avoid"),
        diet=args.get("diet") or existing.get("diet"),
    )
    return update_food(user_id, prefs)


LIST_ADD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "add_to_list",
        "description": (
            "Put something on one of her lists. Use this the moment she "
            "names a thing she needs to get, do, remember or ask about — "
            "'sabudana lena hai', 'doctor se yeh poochna hai', 'beta ko "
            "batana hai'. She is seventy and writing on paper; the whole "
            "point is that she can say it in passing and it is kept.\n\n"
            "Add it even if she has not asked for a list. A list starts "
            "itself the first time she names something.\n\n"
            "Do NOT use this for things with a time — 'teen baje dawai "
            "leni hai' is a reminder, not a list item."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "what": {
                    "type": "string",
                    "description": (
                        "The thing itself, in her words. 'sabudana', not "
                        "'sago for fasting'."
                    ),
                },
                "fields": {
                    "type": "object",
                    "description": (
                        "Anything else she said about it, as key-value "
                        "pairs in HER words: {'kitna': 'do kilo'}, "
                        "{'kahan se': 'Big Bazaar'}. Leave it out when she "
                        "said nothing else. Do not invent fields and do "
                        "not translate her words into English."
                    ),
                },
                "list_name": {
                    "type": "string",
                    "description": (
                        "Which list, if she named one — 'bazar ki list', "
                        "'doctor ke sawaal'. Omit it and the most recent "
                        "list is used, which is almost always right."
                    ),
                },
            },
            "required": ["what"],
        },
    },
}

LIST_READ_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_list",
        "description": (
            "Read back what is on a list. Use this when she asks — 'list "
            "mein kya hai', 'kya kya lena tha' — and when she is about to "
            "go out and the list is plainly relevant.\n\n"
            "Do not read it back unprompted at other times. A companion "
            "that recites a shopping list every morning is a nuisance."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "list_name": {
                    "type": "string",
                    "description": "Which one, if she named it. Usually omit.",
                },
            },
            "required": [],
        },
    },
}

LIST_TICK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "tick_off_list",
        "description": (
            "Cross something off, when she says she has got it or done it "
            "— 'sabudana le liya', 'woh ho gaya'. It stays on the list, "
            "crossed off, because a market list is worth seeing again next "
            "month and she will want the same things."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "what": {
                    "type": "string",
                    "description": "The thing she has got, in her words.",
                },
                "list_name": {"type": "string"},
            },
            "required": ["what"],
        },
    },
}

LIST_CLOSE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "close_list",
        "description": (
            "Finish with a list, when she says she is done — 'sab le "
            "liya', 'list khatam'. Do not close it because everything is "
            "ticked; she may add more."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "list_name": {"type": "string"},
            },
            "required": [],
        },
    },
}


# ── handlers ──────────────────────────────────────────────────────────────

def _handle_list_add(args: dict, user_id: str) -> dict:
    from memory.lists import add
    return add(user_id,
               args.get("what") or "",
               args.get("fields") or {},
               args.get("list_name") or "")


def _handle_list_read(args: dict, user_id: str) -> dict:
    from memory.lists import read
    return read(user_id, args.get("list_name") or "")


def _handle_list_tick(args: dict, user_id: str) -> dict:
    from memory.lists import tick
    return tick(user_id, args.get("what") or "",
                args.get("list_name") or "")


def _handle_list_close(args: dict, user_id: str) -> dict:
    from memory.lists import close
    return close(user_id, args.get("list_name") or "")


TOOL_REGISTRY = {
    # Her lists. She said she was going to the market and the companion
    # offered to keep things for her, with nowhere to put them.
    "add_to_list":   {"schema": LIST_ADD_SCHEMA,   "handler": _handle_list_add},
    "read_list":     {"schema": LIST_READ_SCHEMA,  "handler": _handle_list_read},
    "tick_off_list": {"schema": LIST_TICK_SCHEMA,  "handler": _handle_list_tick},
    "close_list":    {"schema": LIST_CLOSE_SCHEMA, "handler": _handle_list_close},

    "get_recipes": {
        "schema":  RECIPES_SCHEMA,
        "handler": lambda args, user_id: get_recipes(user_id, args.get("query")),
    },
    "search_web": {
        "schema":  SEARCH_SCHEMA,
        "handler": lambda args, user_id: web_search(user_id, args.get("query")),
    },
    "add_calendar_event": {
        "schema":  CALENDAR_ADD_SCHEMA,
        "handler": _handle_add_calendar,
    },
    "get_calendar": {
        "schema":  CALENDAR_VIEW_SCHEMA,
        "handler": lambda args, user_id: get_calendar(user_id, args.get("days") or 7),
    },
    "update_food_prefs": {
        "schema":  FOOD_PREF_SCHEMA,
        "handler": _handle_update_food,
    },
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

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
                "kind": {
                    "type": "string",
                    "enum": ["all", "local", "india", "sports", "entertainment", "world"],
                    "description": (
                        "A kind of news rather than a topic: all (the day's "
                        "top stories of every kind), local (her own "
                        "city's news), india, sports, entertainment (films, TV, "
                        "music), world. Use when she asks for a kind of news "
                        "('aas-paas ki khabar', 'khel ki khabar', 'duniya ki "
                        "khabar'); use topic instead when she names a subject."
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
            "doctors, restaurants, parks, temples, or one place by name. Use "
            "whenever the user asks where something is, how far it is, or "
            "needs to find a place. Each result has distance_km and walk_min "
            "from where she is, nearest first: when she asks how far, answer "
            "from these, as 'about', and never guess a distance or a place "
            "that is not in the results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "place_type": {
                    "type": "string",
                    "description": (
                        "Kind of place (hospital, pharmacy, doctor, clinic, "
                        "restaurant, park, temple) or a specific name, e.g. "
                        "the shop or restaurant she asked about."
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
            "T11:00:00+05:30. Call the tool, THEN confirm warmly. Telling you the "
            "same plan again is safe: the calendar keeps one (status 'already "
            "there'), and a new time for it moves it (status 'moved'). To call "
            "something off or move it, use change_calendar_event."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title":    {"type": "string", "description": "The thing itself, as she would name it: 'Doctor appointment', 'Durga Puja pandal darshan (Palace Grounds)'. Not the asking: no 'yaad dilana', 'reminder' or 'plan' in it — the calendar already shows it will remind her."},
                "event_at": {"type": "string", "description": "ISO 8601 datetime, e.g. '2026-08-19T16:00:00'. Infer from what the user said relative to now."},
                "category": {"type": "string", "description": "One of: medical, social, festival, personal. Best guess."},
            },
            "required": ["title", "event_at"],
        },
    },
}

CALENDAR_CHANGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "change_calendar_event",
        "description": (
            "Call off or move something on her calendar, or a reminder, when she "
            "says so: 'pandal nahi jaenge', 'doctor ab 4 baje hai', 'woh reminder "
            "hata do', 'Arjun Sunday nahi, Monday aayega'. Its reminder goes or "
            "moves with it. You do not need to look the calendar up first; say in "
            "'about' which thing she means, in her words. If the result is 'not "
            "sure which', ask her which one, naming the options. For a move, "
            "compute new_event_at as a FULL ISO datetime in her timezone "
            "(India, +05:30). Then confirm in a few words what changed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "about":        {"type": "string", "description": "Which plan or reminder, in her words, e.g. 'pandal darshan'."},
                "action":       {"type": "string", "enum": ["cancel", "move"]},
                "new_event_at": {"type": "string", "description": "For move: the new ISO datetime, e.g. '2026-10-17T16:00:00+05:30'."},
            },
            "required": ["about", "action"],
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
            "names a thing she needs to get, pack, do, remember or ask about "
            "— 'sabudana lena hai', 'doctor se yeh poochna hai', 'shawl "
            "rakhna hai'. She is seventy and writing on paper; the whole "
            "point is that she can say it in passing and it is kept. Several "
            "things in one breath → call this once per thing.\n\n"
            "Add it even if she has not asked for a list. A list starts "
            "itself the first time she names something; the result says "
            "started_new_list, and then tell her in a few words which list "
            "you started ('bazar ki list bana di').\n\n"
            "Do NOT use this for things with a time — 'teen baje dawai "
            "leni hai' is a reminder, not a list item.\n\n"
            "If a word looks misheard or misspelt for the list it is going "
            "on — 'carbon' and 'pool' on a market list were tarbooz and "
            "phool — add what she most likely meant and check it with her "
            "in a few words in your reply ('tarbooz likha hai, theek?'). "
            "Do not add the garbled word as it is."
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
                        "{'kahan se': 'Big Bazaar'}, {'kis liye': 'Navratri'}. "
                        "Leave it out when she said nothing else. Do not "
                        "invent fields and do not translate her words."
                    ),
                },
                "list_name": {
                    "type": "string",
                    "description": (
                        "Which list. Short, one or two words, by what it is "
                        "for: 'bazar', 'packing', 'doctor ke sawaal', "
                        "'Navratri'. Name it when she named one or when the "
                        "thing plainly belongs to a different kind of list "
                        "than the one open (a shawl to pack is not market "
                        "shopping). Otherwise omit it and the most recent "
                        "open list is used."
                    ),
                },
                "expires_on": {
                    "type": "string",
                    "description": (
                        "YYYY-MM-DD, only when she said how long it is for — "
                        "'kal ke bazar ke liye', 'Surat jaane tak', 'Navratri "
                        "tak'. Resolve it against her local date. Omit "
                        "otherwise; an untouched list closes itself after "
                        "two weeks."
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
            "Read a list back. Use this when she asks — 'list mein kya hai', "
            "'kya kya lena tha', 'meri saari lists' — and when she is about "
            "to go out and the list is plainly relevant. Do not read it back "
            "unprompted at other times.\n\n"
            "In a shop she wants ONE thing at a time: 'ek ek karke batao', "
            "'padh ke sunao, main dhoondti hoon' → one_at_a_time=true. Say "
            "only that one item and wait. The next comes from "
            "tick_off_list (current=true when she has it, skip=true when "
            "she did not find it).\n\n"
            "'Bas', 'baad mein dekhenge' while going through one → "
            "stop_reading=true."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "list_name": {
                    "type": "string",
                    "description": "Which one, if she named it. Usually omit.",
                },
                "one_at_a_time": {
                    "type": "boolean",
                    "description": "Read out just the next item not yet got.",
                },
                "all_lists": {
                    "type": "boolean",
                    "description": "Which lists she has open and how much is left on each.",
                },
                "kept": {
                    "type": "boolean",
                    "description": "Her finished lists she chose to keep ('purani lists').",
                },
                "stop_reading": {
                    "type": "boolean",
                    "description": "She has stopped going through it one at a time.",
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
            "Cross something off, or put it back.\n"
            "- She names it: 'sabudana le liya' → what='sabudana'.\n"
            "- She is going through the list one at a time and says 'mil "
            "gaya' / 'le liya' with no name → current=true. The result "
            "carries the next item: say it.\n"
            "- 'Nahi mila', 'aage batao' → skip=true. It stays on.\n"
            "- 'Sab le liya' → everything=true.\n"
            "- 'Nahi, woh abhi nahi liya', 'galti se kaat diya' → undo=true "
            "with what.\n"
            "Ticked things stay on the list, crossed off. If the result says "
            "not_found, tell her it is not on the list — do not pretend."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "what": {"type": "string", "description": "The thing, in her words."},
                "current": {"type": "boolean", "description": "The item just read out to her."},
                "skip": {"type": "boolean", "description": "She did not find the item just read out."},
                "everything": {"type": "boolean", "description": "She has got all of it."},
                "undo": {"type": "boolean", "description": "Put it back — not got after all."},
                "list_name": {"type": "string"},
            },
            "required": [],
        },
    },
}

LIST_CHANGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "change_list_item",
        "description": (
            "Change or remove something already on a list. 'Do kilo nahi, "
            "ek kilo' → fields={'kitna': 'ek kilo'}. 'Sabudana nahi, "
            "makhana' → new_what='makhana'. 'Woh hata do, galti se bola' → "
            "remove=true. Removing is for mistakes; something she has got is "
            "crossed off with tick_off_list, not removed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "what": {"type": "string", "description": "The item as it is on the list now."},
                "new_what": {"type": "string", "description": "What it should say instead."},
                "fields": {
                    "type": "object",
                    "description": "Details to set, in her words. An empty value drops that detail.",
                },
                "remove": {"type": "boolean", "description": "Take it off entirely."},
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
            "Finish with a list, when she says she is done — 'list "
            "khatam', 'ab iski zaroorat nahi'. Do not close it just "
            "because everything is ticked; she may add more.\n\n"
            "ASK FIRST, and pass what she says as `keep`: rakh lein agli "
            "baar ke liye, ya hata dein? A kept list can be started again "
            "next time; a dropped one is gone. It is hers to decide, and if "
            "she does not say, keep it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keep": {
                    "type": "boolean",
                    "description": (
                        "True to keep it for next time, false to delete it. "
                        "What SHE said. Default true."
                    ),
                },
                "list_name": {"type": "string"},
            },
            "required": [],
        },
    },
}

LIST_REUSE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "reuse_list",
        "description": (
            "Start a kept list again — 'pichli baar wali Navratri list', "
            "'wahi packing list phir se'. Makes a new open list with the "
            "same things, nothing crossed off. If it is not found, the "
            "result names her kept lists; offer those."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "list_name": {"type": "string", "description": "The kept list's name, in her words."},
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
               args.get("list_name") or "",
               expires_on=args.get("expires_on") or "")


def _handle_list_read(args: dict, user_id: str) -> dict:
    from memory import lists as L
    name = args.get("list_name") or ""
    if args.get("stop_reading"):
        return L.stop_walk(user_id, name)
    if args.get("kept"):
        return L.kept(user_id)
    if args.get("all_lists"):
        return L.read_all(user_id)
    if args.get("one_at_a_time"):
        return L.next_item(user_id, name)
    return L.read(user_id, name)


def _handle_list_tick(args: dict, user_id: str) -> dict:
    from memory import lists as L
    name = args.get("list_name") or ""
    what = (args.get("what") or "").strip()
    if args.get("undo"):
        return L.untick(user_id, what, name)
    if args.get("everything"):
        return L.tick_all(user_id, name)
    if args.get("skip"):
        return L.skip_current(user_id, name)
    if args.get("current") or not what:
        # No name: only the thing just read out. Never everything by
        # default — that empties her list on a misheard "ho gaya".
        return L.tick_current(user_id, name)
    return L.tick(user_id, what, name)


def _handle_list_change(args: dict, user_id: str) -> dict:
    from memory import lists as L
    name = args.get("list_name") or ""
    if args.get("remove"):
        return L.remove(user_id, args.get("what") or "", name)
    return L.change(user_id, args.get("what") or "",
                    args.get("new_what") or "", args.get("fields") or {}, name)


def _handle_list_close(args: dict, user_id: str) -> dict:
    from memory.lists import close
    return close(user_id, args.get("list_name") or "",
                 keep=bool(args.get("keep", True)))


def _handle_list_reuse(args: dict, user_id: str) -> dict:
    from memory.lists import reuse
    return reuse(user_id, args.get("list_name") or "")


TOOL_REGISTRY = {
    # Her lists. She said she was going to the market and the companion
    # offered to keep things for her, with nowhere to put them.
    "add_to_list":   {"schema": LIST_ADD_SCHEMA,   "handler": _handle_list_add},
    "read_list":     {"schema": LIST_READ_SCHEMA,  "handler": _handle_list_read},
    "tick_off_list": {"schema": LIST_TICK_SCHEMA,  "handler": _handle_list_tick},
    "change_list_item": {"schema": LIST_CHANGE_SCHEMA, "handler": _handle_list_change},
    "close_list":    {"schema": LIST_CLOSE_SCHEMA, "handler": _handle_list_close},
    "reuse_list":    {"schema": LIST_REUSE_SCHEMA, "handler": _handle_list_reuse},

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
    "change_calendar_event": {
        "schema":  CALENDAR_CHANGE_SCHEMA,
        "handler": lambda args, user_id: __import__("routes.calendar", fromlist=["change_event"]).change_event(
            user_id, args.get("about") or "", args.get("action") or "cancel", args.get("new_event_at") or ""),
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
        "handler": lambda args, user_id: get_news(user_id, args.get("topic"), args.get("kind")),
    },
    "get_places": {
        "schema":  PLACES_SCHEMA,
        "handler": lambda args, user_id: get_nearby_places(
            user_id,
            args.get("place_type") or "hospital",
            args.get("location"),
            with_phone=True,      # a call button for the chemist or doctor
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

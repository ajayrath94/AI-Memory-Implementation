"""
PERSONA NAMES — single source of truth for what the companion is called.

The companion's name is spoken constantly by the user, so every extractor
downstream needs to know it is not a person in the user's life. Before this
existed, "Nancy" was hardcoded in profile_store, summarizer and reminder_engine;
a user who renamed their companion would have had it filed as a relative.

Lives in memory/ rather than routes/ so the memory pipeline can import it
without pulling in FastAPI.

History matters: after a rename, stored sessions still contain the old name. If
it stopped being reserved, re-extraction over those sessions would file the
former companion as a relative. Names are appended, never removed.
"""

from typing import Optional

# Product default, used when a user has no persona row.
DEFAULT_BOT_NAME = "Nancy"
_DEFAULT_ASSISTANT_NAMES = {"nancy", "nancy ai", "nancy app"}

# A companion configured with one of these roleplays a relative — the user says
# "mera beta Shubham" about the COMPANION, which is indistinguishable from
# saying it about a real son. See is_familial_persona.
_FAMILIAL_ROLES = {"son", "daughter", "mother", "father", "brother", "sister"}


def _persona_row(user_id: str) -> Optional[dict]:
    try:
        from supabase_store import get_client
        res = (get_client().table("bot_personas")
               .select("bot_name,bot_name_history,relationship")
               .eq("user_id", user_id).limit(1).execute())
        return (res.data or [None])[0]
    except Exception as e:
        print(f"[Persona] lookup failed for {user_id}: {e}")
        return None


def get_companion_name(user_id: str) -> str:
    """Display name of this user's companion."""
    row = _persona_row(user_id)
    if row and (row.get("bot_name") or "").strip():
        return row["bot_name"].strip()
    return DEFAULT_BOT_NAME


def get_reserved_names(user_id: str) -> set:
    """
    Lowercased names that must never be recorded as people in the user's life.

    Always includes the product defaults, so a user whose persona row is missing
    or unreadable still gets the baseline protection.
    """
    names = set(_DEFAULT_ASSISTANT_NAMES)
    row = _persona_row(user_id)
    if row:
        candidates = list(row.get("bot_name_history") or [])
        if row.get("bot_name"):
            candidates.append(row["bot_name"])
        for n in candidates:
            n = (n or "").strip().lower()
            if n:
                names.add(n)
    return names


def is_familial_persona(user_id: str) -> bool:
    """
    True when the companion roleplays a relative.

    Matters because the usual safeguard — "keep the name if a relation was
    stated, drop it if bare" — fails here. For a companion named Shubham with
    relationship 'son', the user will say "mera beta Shubham" about the
    companion, and no signal distinguishes that from a real son of the same
    name. These personas reserve the name unconditionally, which means a real
    relative sharing it cannot be recorded. That is a deliberate trade: a
    missing relative is recoverable by asking, a companion filed as family
    corrupts the profile silently.
    """
    row = _persona_row(user_id)
    return bool(row) and row.get("relationship") in _FAMILIAL_ROLES

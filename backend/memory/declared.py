"""
DECLARED — what the person has told us about themselves.

The line this draws is between what someone SAID and what the system NOTICED.
Language, their companion's name, when they get up, where they live: those are
declarations. Knee pain, that they mention Kishore Kumar often, that they have
gone quiet for three days: those are observations, and they live in memory.

The reason for the split is a bug that cost an evening. Language was read in
three places — the profile column, the persona's language_mix, and the prompt
block — and none of them owned it, so a person could pick English on the
language screen and still be answered in Hinglish because the persona was more
specific and sat closer to the model. Voice, timezone and the companion's name
are all one careless commit away from the same shape.

So: one function assembles this, and everything that needs a preference reads
it here rather than reaching into whichever table happens to hold the field.

WHAT THIS IS NOT
Not the whole profile. Health, family, interests learned from conversation,
clusters, summaries — those are memory, they are expensive to load, and a
handler that wants the companion's name should not pay for them. Six groups,
three tables, one query each.

MIGRATION
Additive. Existing callers keep working; they move over one at a time. The one
thing worth not doing is leaving it half migrated for months — two ways to read
the same preference is the problem this exists to remove.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class Place:
    home:    Optional[str] = None      # permanent — "main Surat mein rehti hoon"
    current: Optional[str] = None      # set only while travelling
    timezone: str = "Asia/Kolkata"

    @property
    def where_now(self) -> Optional[str]:
        return self.current or self.home

    @property
    def away(self) -> bool:
        return bool(self.current and self.current != self.home)


@dataclass
class Language:
    pref: str = "hinglish"             # the phrase a prompt can use in a sentence
    mix:  Dict[str, float] = field(default_factory=dict)

    @property
    def instruction(self) -> str:
        """One sentence, for the point of generation.

        Placed last in a prompt rather than among the context blocks: 122
        characters saying "write in Gujarati" lost to 2,700 characters of
        stored notes that happened to be in Hinglish, because the notes read
        as a demonstration. Naming the script matters too — "Punjabi mixed
        with English" came back as Hinglish, since an ambiguous instruction
        resolves toward whichever mixed register the model knows best.
        """
        if self.mix and len(self.mix) > 1:
            ordered = sorted(self.mix.items(), key=lambda kv: -kv[1])
            first, second = ordered[0][0], ordered[1][0]
            return (f"They speak {first} mixed with {second}. Write in that "
                    f"blend — mostly {first}, with {second} woven through the "
                    f"way someone bilingual actually talks.")
        return (f"They speak {self.pref}. Write in {self.pref} — this is not "
                f"optional, and applies to a short greeting as much as to a "
                f"long reply.")


@dataclass
class Companion:
    name:         str = "Nancy"
    name_history: List[str] = field(default_factory=list)
    relationship: str = "companion"    # son | daughter | friend | companion | caretaker
    warmth:       float = 0.9
    humour:       float = 0.6
    slangs:       List[str] = field(default_factory=list)
    voice_type:   str = "preset"
    voice_id:     Optional[str] = None

    @property
    def is_familial(self) -> bool:
        """A companion styled as a relative. Its name is reserved
        unconditionally, because "mera beta Shubham" is ambiguous between the
        companion and an actual son."""
        return self.relationship in ("son", "daughter", "mother", "father",
                                     "brother", "sister")


@dataclass
class Rhythm:
    """Declared only. What was OBSERVED lives beside it in user_patterns and is
    deliberately never merged in — "she says 6:30 but has been talking at 9 for
    a week" is either a routine change or a decline, and collapsing the two
    loses the question."""
    wake:     Optional[str] = None
    sleep:    Optional[str] = None
    meals:    Dict[str, str] = field(default_factory=dict)     # {"lunch": "13:00"}
    routines: List[dict] = field(default_factory=list)         # label, label_native, at


@dataclass
class Declared:
    user_id:      str
    caregiver_id: Optional[str] = None
    name:         Optional[str] = None
    age_group:    Optional[str] = None

    place:     Place     = field(default_factory=Place)
    language:  Language  = field(default_factory=Language)
    companion: Companion = field(default_factory=Companion)
    rhythm:    Rhythm    = field(default_factory=Rhythm)
    interests: Dict[str, List[str]] = field(default_factory=dict)


# ── assembly ──────────────────────────────────────────────────────────────────

def _profile(user_id: str) -> dict:
    try:
        from memory.profile_store import get_user_profile
        return get_user_profile(user_id) or {}
    except Exception as e:
        print(f"[Declared] profile read failed: {e}")
        return {}


def _persona(user_id: str) -> dict:
    try:
        from supabase_store import get_client
        rows = (get_client().table("bot_personas").select("*")
                .eq("user_id", user_id).limit(1).execute()).data or []
        return rows[0] if rows else {}
    except Exception as e:
        print(f"[Declared] persona read failed: {e}")
        return {}


def _patterns(user_id: str) -> list:
    try:
        from supabase_store import get_client
        return (get_client().table("user_patterns").select("*")
                .eq("user_id", user_id).execute()).data or []
    except Exception as e:
        print(f"[Declared] patterns read failed: {e}")
        return []


def _timezone(user_id: str) -> str:
    try:
        from memory.time_context import get_user_timezone
        return get_user_timezone(user_id)
    except Exception:
        return "Asia/Kolkata"


def get_declared(user_id: str) -> Declared:
    """Assemble everything the person has stated. Eager: three queries, then
    every read downstream is free. At this scale that is nothing beside the
    model calls already happening, and it is far easier to reason about than
    lazy properties that fire a query when touched inside a loop."""
    p  = _profile(user_id)
    bp = _persona(user_id)
    pats = _patterns(user_id)

    rhythm = Rhythm()
    for r in pats:
        # declared_at only. observed_at is memory's business.
        at = (r.get("declared_at") or "")[:5]
        if not at:
            continue
        kind = r.get("kind")
        if kind == "wake":
            rhythm.wake = at
        elif kind == "sleep":
            rhythm.sleep = at
        elif kind == "meal" and r.get("label"):
            rhythm.meals[r["label"]] = at
        elif kind == "routine":
            rhythm.routines.append({
                "label":        r.get("label"),
                "label_native": r.get("label_native"),
                "at":           at,
            })

    personality = bp.get("personality") or {}

    return Declared(
        user_id      = user_id,
        caregiver_id = bp.get("caregiver_id"),
        name         = p.get("name"),
        age_group    = p.get("age_group"),

        place = Place(
            # home_location is the field named for this; `location` is the
            # older one it falls back to.
            home     = p.get("home_location") or p.get("location"),
            current  = p.get("current_location"),
            timezone = _timezone(user_id),
        ),
        language = Language(
            pref = p.get("language_pref") or "hinglish",
            mix  = bp.get("language_mix") or {},
        ),
        companion = Companion(
            name         = bp.get("bot_name") or "Nancy",
            name_history = bp.get("bot_name_history") or [],
            relationship = bp.get("relationship") or "companion",
            warmth       = float(personality.get("warmth", 0.9)),
            humour       = float(personality.get("humor", 0.6)),
            slangs       = bp.get("slangs") or [],
            voice_type   = bp.get("voice_type") or "preset",
            voice_id     = bp.get("voice_id"),
        ),
        rhythm    = rhythm,
        interests = _declared_interests(user_id),
    )


def _declared_interests(user_id: str) -> Dict[str, List[str]]:
    """Interests the person named, as opposed to ones inferred from what they
    talk about. Both are real; only one is something they said.

    Clusters carry source='declared' for these, and the cleaner leaves them
    alone — otherwise a stated preference could be swept as junk for the crime
    of only having been mentioned once.
    """
    try:
        from supabase_store import get_client
        rows = (get_client().table("interest_clusters")
                .select("label,pillar,attributes")
                .eq("user_id", user_id).eq("status", "active")
                .execute()).data or []
    except Exception as e:
        print(f"[Declared] interests read failed: {e}")
        return {}

    out: Dict[str, List[str]] = {}
    for r in rows:
        attrs = r.get("attributes") or {}
        if not isinstance(attrs, dict) or attrs.get("source") != "declared":
            continue
        cat = attrs.get("category") or "other"
        out.setdefault(cat, []).append(r["label"])
    return out

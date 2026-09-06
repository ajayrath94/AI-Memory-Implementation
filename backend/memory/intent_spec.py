"""
INTENT SPECS — what each kind of message may see, and what must be true of it.

The composer used to receive every context source regardless of what it was
trying to say, and infer relevance. It inferred badly: a 20:00 blood-pressure
nudge asked about lunch because 13:00 Lunch was sitting in the routine block,
and another named the 07:00 Thyronorm at night. Both were "fixed" by adding a
hint, which narrows the odds without removing the cause — the model could still
reach for anything it was shown.

So each intent declares its own scope. A medication reminder does not see the
routine, because the only relevant item is the one that is due and that arrives
as an explicit hint. A recommendation does not see medication. Nothing is left
to inference that can be decided here.

CHECKS are the other half: assertions the output must satisfy, run by the
simulation harness. A rule that is not checked drifts back within a week.
"""

# ── what each intent may see ──────────────────────────────────────────────────
# Sources are the keys of context_builder._SOURCES. Persona and language are
# implicit — every message needs both.

SCOPE = {
    "boundary": {
        # Something just finished and something is coming. It has both a reason
        # to exist and a direction, so curiosity would only displace one of
        # them — which it did, three times, before the gate was inverted.
        "sources": ["memory", "routine", "tone", "voice"],
        "task": ("Continue the conversation. The hints say what just happened "
                 "and what is next; both belong in the message."),
        "forbid_medication": True,
        # In the prompt as well as the flag. The flag is only read by
        # run_checks, which judges a message after it exists — nothing stopped
        # one being written, and a greeting duly told her to take her
        # Thyronorm. A separate reminder names the right drug at the right
        # hour; a greeting that guesses gets it wrong.
        "forbid_note": ("Do NOT mention any medicine, tablet, dose or dawai. "
                        "Not one word about medication."),
    },
    "greeting": {
        # No curiosity and no probe. Both ask, and a greeting gives — the first
        # draft was hijacked by a probe and every register came out as a
        # question with "good morning" bolted on.
        "sources": ["memory", "routine", "tone"],
        "task": ("Write their morning message. The instruction in the hints "
                 "decides the register and is not optional."),
        "forbid_medication": True,
        # In the prompt as well as the flag. The flag is only read by
        # run_checks, which judges a message after it exists — nothing stopped
        # one being written, and a greeting duly told her to take her
        # Thyronorm. A separate reminder names the right drug at the right
        # hour; a greeting that guesses gets it wrong.
        "forbid_note": ("Do NOT mention any medicine, tablet, dose or dawai. "
                        "Not one word about medication."),
        "no_curiosity": True,
    },
    "check_in": {
        # The only intent that asks about something it does not know. Every
        # other kind of message has a reason to exist already — a boundary, a
        # greeting, a reminder — and curiosity would displace it.
        "curiosity": True,
        "sources": ["memory", "routine", "interests", "patterns", "recent", "voice", "tone"],
        "task": ("You are starting the conversation — they have not said "
                 "anything yet. Write your opening line.\n"
                 "Do NOT mention any medicine, tablet, dose or dawai. A "
                 "separate reminder handles those at the right hour and names "
                 "the right one; a greeting that guesses at medication usually "
                 "names the wrong drug."),
        # A check-in is a greeting, not a nudge. Naming a drug here turns a warm
        # note into a medical instruction, and the drug named is often the wrong
        # one because nothing said which is due.
        "forbid_medication": True,
        # In the prompt as well as the flag. The flag is only read by
        # run_checks, which judges a message after it exists — nothing stopped
        # one being written, and a greeting duly told her to take her
        # Thyronorm. A separate reminder names the right drug at the right
        # hour; a greeting that guesses gets it wrong.
        "forbid_note": ("Do NOT mention any medicine, tablet, dose or dawai. "
                        "Not one word about medication."),
    },
    "medication": {
        # Deliberately NOT "routine": the whole day's schedule is what made it
        # pick lunch at 8pm. The due item comes in as a hint instead.
        "sources": ["memory", "patterns"],
        "task": ("A medication is due right now. Remind them warmly and name "
                 "it. One line. Do not mention meals, walks, or anything else "
                 "from their day — only the dose that is due."),
        "forbid_medication": False,
    },
    "recommendation": {
        "sources": ["memory", "interests", "patterns", "integrations"],
        "task": ("Suggest one thing they might enjoy right now, drawn from "
                 "what they already like. Offer, do not insist."),
        # Used when there is nothing in their interests to draw on — better
        # than the stitched templates, which opened an explore offer with a
        # medication reminder.
        "fixed": "Bahar nikle hain? Kuch acha mile toh bataiyega.",
        "forbid_medication": True,
        # In the prompt as well as the flag. The flag is only read by
        # run_checks, which judges a message after it exists — nothing stopped
        # one being written, and a greeting duly told her to take her
        # Thyronorm. A separate reminder names the right drug at the right
        # hour; a greeting that guesses gets it wrong.
        "forbid_note": ("Do NOT mention any medicine, tablet, dose or dawai. "
                        "Not one word about medication."),
    },
    "safety": {
        # Nothing but who they are and where they are. A safety check that
        # wanders into hobbies is worse than useless.
        "sources": [],
        # And with nothing to draw on, the composer has nothing personal to
        # say — it broke character three times out of three and fell back to a
        # template about morning chai. This fires when an elderly person is
        # away from home at 2am, which is the moment the system most needs to
        # be reliable, so it does not go near a model.
        "fixed": "Aap theek ho? Itni raat ho gayi hai — sab theek hai na?",
        "always_fixed": True,
        "task": ("They are away from home and it is late. Check they are "
                 "alright. Calm and brief — do not alarm them."),
        "forbid_medication": True,
        # In the prompt as well as the flag. The flag is only read by
        # run_checks, which judges a message after it exists — nothing stopped
        # one being written, and a greeting duly told her to take her
        # Thyronorm. A separate reminder names the right drug at the right
        # hour; a greeting that guesses gets it wrong.
        "forbid_note": ("Do NOT mention any medicine, tablet, dose or dawai. "
                        "Not one word about medication."),
    },
}

DEFAULT_INTENT = "check_in"


def scope_for(intent: str) -> dict:
    return SCOPE.get(intent) or SCOPE[DEFAULT_INTENT]


# ── what must be true of the output ───────────────────────────────────────────
# Each returns None if the message is acceptable, or a string saying what is
# wrong. The harness runs these over every composed message; compose() runs the
# character check inline because that one must never reach a user.

def check_in_character(text: str, **_) -> str:
    """The model addresses the operator when the profile is thin — "I don't
    have any information about them, could you share a bit?" — which would go
    to an elderly user as a push notification."""
    tells = (
        "i don't have", "i do not have", "i don't know", "could you share",
        "could you tell me", "to write a", "let me know", "as an ai",
        "i'd need", "i would need", "no information", "not enough context",
        "based on the information provided", "here's a", "here is a",
    )
    low = text.lower()
    for t in tells:
        if t in low:
            return f"broke character: {t!r}"
    return None


def check_length(text: str, **_) -> str:
    """One or two sentences. Anything longer stops being a note and becomes a
    speech, which is not what a companion sounds like."""
    if len(text) > 320:
        return f"too long ({len(text)} chars)"
    return None


def check_names_due_item(text: str, due_labels=None, **_) -> str:
    """A medication reminder that does not name the drug is not a reminder."""
    if not due_labels:
        return None
    low = text.lower()
    # First word of the label — "BP tablet (amlodipine)" should match on "bp"
    # or "amlodipine", not require the exact parenthesised string.
    for label in due_labels:
        parts = [p.strip("()").lower() for p in str(label).split() if len(p) > 2]
        if any(p in low for p in parts):
            return None
    return f"names none of the due items {due_labels}"


def check_no_medication(text: str, all_medications=None, **_) -> str:
    """A check-in should not name drugs. When it does it is usually the wrong
    drug, picked from the routine because it read well."""
    if not all_medications:
        return None
    low = text.lower()
    for med in all_medications:
        parts = [p.strip("()").lower() for p in str(med).split() if len(p) > 3]
        for p in parts:
            if p in low:
                return f"check-in named a medication: {p!r}"
    return None


def check_no_stale_routine(text: str, current_hour=None, routine=None, **_) -> str:
    """Mentioning an item from a different part of the day. The 20:00 nudge
    asking about lunch is the case this exists for."""
    if current_hour is None or not routine:
        return None
    low = text.lower()
    for item in routine:
        try:
            h = int(str(item.get("time_of_day", ""))[:2])
        except Exception:
            continue
        label = (item.get("label") or "").lower()
        if not label:
            continue
        gap = min(abs(h - current_hour), 24 - abs(h - current_hour))
        if gap > 4 and label.split()[0] in low:
            return (f"mentions {label!r} ({h:02d}:00) at {current_hour:02d}:00, "
                    f"{gap}h away")
    return None


CHECKS = [
    check_in_character,
    check_length,
    check_names_due_item,
    check_no_medication,
    check_no_stale_routine,
]


def run_checks(text: str, intent: str = DEFAULT_INTENT, **facts) -> list:
    """Every failure, not just the first — one message can be wrong twice."""
    if not text:
        return []
    spec = scope_for(intent)
    problems = []
    for fn in CHECKS:
        if fn is check_names_due_item and intent != "medication":
            continue
        if fn is check_no_medication and not spec.get("forbid_medication"):
            continue
        p = fn(text, **facts)
        if p:
            problems.append(p)
    return problems

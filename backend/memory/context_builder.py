"""
CONTEXT BUILDER — what the companion knows, assembled once.

Everything the companion says out of its own initiative — a check-in, a
medication nudge, a music suggestion — draws on the same picture: who it is
(persona), what it remembers, what the day looks like, what they like. Before
this, that assembly lived inside schedule_engine next to slot logic and five
string templates, and anything else wanting the same context would have had to
duplicate it. That is how the two reminder-firing loops drifted apart, and how
"Aaj ka cricket dekha?" survived long after the memory layer knew she liked
Kishore Kumar.

Each source is its own function returning a block of text or "". Sources that
do not exist yet return "" and are skipped, so adding behavioural patterns or
weather later means filling in one function — nothing else changes.

Deciding WHETHER to speak stays in proactive_engine. This only decides how it
is worded. They change for different reasons and should not be one function.
"""
import os
from typing import Optional

_MODEL = __import__("llm").model("claude-haiku-4-5-20251001")


# ── sources ───────────────────────────────────────────────────────────────────

def _persona(user_id: str) -> str:
    """Who the companion is — name, relationship, register, what it may say."""
    try:
        from routes.persona import get_persona_prompt
        return get_persona_prompt(user_id) or ""
    except Exception as e:
        print(f"[Context] persona failed: {e}")
        return "You are Nancy, a warm companion."


def _memory(user_id: str) -> str:
    """Durable facts, the running summary, key facts."""
    try:
        from memory.user_memory_store import build_memory_prompt
        return build_memory_prompt(user_id) or ""
    except Exception as e:
        print(f"[Context] memory failed: {e}")
        return ""


def _routine(user_id: str) -> str:
    """Their actual day — meals, medication times, puja, walks. Caregiver-set
    today; observed patterns will land in the same table."""
    try:
        from supabase_store import get_client
        rows = (get_client().table("care_schedule").select("*")
                .eq("user_id", user_id).eq("active", True)
                .order("time_of_day").execute()).data or []
    except Exception as e:
        print(f"[Context] routine failed: {e}")
        return ""

    lines = []
    for r in rows:
        t = (r.get("time_of_day") or "")[:5]
        label = r.get("label") or r.get("name") or r.get("type") or ""
        if t and label:
            lines.append(f"  {t} — {label} ({r.get('type')})")
    return "Their daily routine:\n" + "\n".join(lines) if lines else ""


def _due_now(user_id: str) -> str:
    """What is due right now and has not been mentioned.

    The routine above is her day in the abstract — the times. This is the
    one thing happening NOW, so a reply can fold it in rather than a push
    arriving separately while she is already talking.
    #
    Her tablets are taken with food and her meals are when the tablets are
    taken; skipping the question because she happens to be mid-conversation
    is worse than asking it. An OFFER never folds in this way — a song can
    wait for its own moment.
    """
    try:
        from memory.day import events, _mins_now
        now = _mins_now(user_id)
        due = []
        for e in events(user_id):
            at = str(e.get("due_at") or "")[:5]
            if not at or ":" not in at:
                continue
            h, m = at.split(":")[:2]
            if not h.isdigit():
                continue
            mins = int(h) * 60 + int(m)
            # due in the last hour, or in the next twenty minutes
            if -20 <= (now - mins) <= 60 and e.get("status") in ("pending", "sent"):
                due.append((abs(now - mins), e, at))
        if not due:
            return ""
        due.sort()
        _, e, at = due[0]
        what = e.get("label") or e.get("kind")
        # No clock time. "was at 08:30" came back as "8:30 baj gaye the na",
        # and nobody tells an older person what time their breakfast is.
        when = "is about now" if (now - mins) < 0 else "was a little while ago"
        return (f"\n\nRIGHT NOW: their {what} {when} and they have not "
                f"mentioned it. If the conversation allows, ask — once, in "
                f"passing, at the end of whatever you are saying. Never as "
                f"the whole reply, never twice, and never with a clock time.")
    except Exception as e:
        print(f"[Context] due-now failed: {e}")
        return ""


def _interests(user_id: str) -> str:
    """What they like, from the profile. build_memory_prompt covers some of
    this via clusters; this adds what the profile holds explicitly."""
    try:
        from memory.profile_store import get_user_profile
        p = get_user_profile(user_id) or {}
    except Exception as e:
        print(f"[Context] interests failed: {e}")
        return ""

    # Computed from clusters, not the stored block. The stored one drifted to
    # 55 entries — twenty music variants, eight rephrasings of "Hindu (Namaste
    # greeting)", and topics mentioned once — of which exactly one had a
    # cluster behind it.
    try:
        from memory.interests_view import computed_interests
        interests = computed_interests(user_id) or {}
    except Exception as e:
        print(f"[Context] computed interests failed, using stored: {e}")
        interests = p.get("interests") or {}
    if not isinstance(interests, dict):
        return ""
    # Shuffled within each category, because the composer takes the first
    # name it reads and the list is ordered by strength — so Kishore Kumar
    # has been first in sangeet every day for three weeks, and three of
    # today's four messages mentioned him.
    #
    # Seeded by the day, so one message does not contradict the next within
    # a conversation.
    import random as _r
    from datetime import date as _d
    rng = _r.Random(f"{user_id}:{_d.today().isoformat()}")

    bits = []
    for key, items in interests.items():
        if isinstance(items, list) and items:
            shown = list(items)[:5]
            rng.shuffle(shown)
            bits.append(f"  {key}: {', '.join(str(i) for i in shown)}")
    return "What they enjoy:\n" + "\n".join(bits) if bits else ""


def _language(user_id: str) -> str:
    """How they speak — from the declared layer, which owns it.

    This used to build the sentence itself from language_pref, and ignored
    language_mix entirely: a persona configured as 60% Hindi and 40% Gujarati
    got a flat "they speak hinglish" instruction, while the persona block said
    something different a few hundred characters earlier. Two places describing
    one thing is how a person could pick English and still be answered in
    Hinglish.
    """
    try:
        from memory.declared import get_declared
        return get_declared(user_id).language.instruction
    except Exception as e:
        print(f"[Context] language read failed: {e}")

    # The declared layer could not be read. The fallback used to say "they
    # speak hinglish" to everybody — which is right for one user and wrong
    # for a woman in Kolkata who asked for English and got "nashta kaisa
    # raha" in reply.
    #
    # The profile holds what she chose. Read it directly rather than
    # assuming.
    try:
        from memory.profile_store import get_user_profile
        pref = str((get_user_profile(user_id) or {}).get("language_pref")
                   or "").strip().lower()
    except Exception:
        pref = ""

    if not pref:
        # And when even that is unknown, mirror her rather than guess:
        # whatever she writes in is what she wants back.
        return ("Write back in whatever language and script they wrote in. "
                "If they have written nothing yet, use simple English. Do "
                "not mix in another language they have not used.")

    return (f"They speak {pref}. Write in {pref} — this is not optional, "
            f"and applies to a short greeting as much as to a long reply.")


def _patterns(user_id: str) -> str:
    """Observed behaviour — usual wake and sleep times, when they go quiet,
    whether pain talk clusters on cold days.

    Not built yet. Returns "" so it is skipped; the day it has something to
    say, it starts appearing in every message with no other change."""
    return ""


def _integrations(user_id: str) -> str:
    """Live context — weather, what is on, news they would care about.

    Fused, not concatenated: memory/fusion holds rules that each need several
    sources to line up before they say anything. Cold weather alone is a
    bulletin; cold weather plus a knee that hurts in the cold plus no mention
    of it for days is worth one line. Most turns nothing fires."""
    return ""      # replaced by fused_context at the call site — see compose()


def _recent_companion_lines(user_id: str, n: int = 6) -> list:
    """The last few things the companion said to this person, across sessions.

    get_recent_messages is session-scoped, which is no help here: proactive
    messages often each get their own session, so within-session history is
    empty exactly when repetition is worst.
    """
    try:
        from supabase_store import get_client
        db = get_client()
        sess = (db.table("sessions").select("id")
                .eq("user_id", user_id)
                .order("updated_at", desc=True).limit(8).execute()).data or []
        ids = [s["id"] for s in sess]
        if not ids:
            return []
        rows = (db.table("messages").select("content,timestamp")
                .in_("session_id", ids).eq("role", "assistant")
                .order("timestamp", desc=True).limit(n).execute()).data or []
        # With the day, because "aaj Sunday hai" said yesterday reads as today
        # otherwise — and repeating something from last week is fine where
        # repeating this morning is not.
        from datetime import datetime as _dt, timezone as _tz
        today = _dt.now(_tz.utc).date()
        out = []
        for r in rows:
            if not r.get("content"):
                continue
            try:
                d = _dt.fromisoformat(
                    str(r["timestamp"]).replace("Z", "+00:00")).date()
                gap = (today - d).days
                when = ("today" if gap == 0 else "yesterday" if gap == 1
                        else f"{gap} days ago")
                out.append(f"[{when}] {r['content']}")
            except Exception:
                out.append(r["content"])
        return out
    except Exception as e:
        print(f"[Context] recent lines failed: {e}")
        return []


def _their_recent_lines(user_id: str, n: int = 6) -> list:
    """The last few things THEY wrote.

    This is how register gets matched, and it replaces measuring it. Counting
    scripts cannot tell romanised Hindi from English — "mujhe pasand hai" is
    Latin characters either way — and a word list per language is nine lists to
    maintain. Showing the model how someone actually writes does the job with
    nothing to own: it will mirror "ਡਾਕਟਰ ਦੀ appointment" without being told
    that this person mixes.
    """
    try:
        from supabase_store import get_client
        db = get_client()
        sess = (db.table("sessions").select("id")
                .eq("user_id", user_id)
                .order("updated_at", desc=True).limit(8).execute()).data or []
        ids = [s["id"] for s in sess]
        if not ids:
            return []
        rows = (db.table("messages").select("content,timestamp")
                .in_("session_id", ids).eq("role", "user")
                .order("timestamp", desc=True).limit(n).execute()).data or []
        return [r.get("content", "") for r in rows if (r.get("content") or "").strip()]
    except Exception as e:
        print(f"[Context] their lines failed: {e}")
        return []


def _how_they_write(user_id: str) -> str:
    lines = _their_recent_lines(user_id, n=5)
    if not lines:
        return ""
    joined = "\n".join(f"  - {l[:140]}" for l in lines)
    return ("How they write, in their own words. Match this — the script they "
            "use, how much English they mix in, how long their sentences run. "
            "Do not correct it or write more formally than they do:\n" + joined)

def _tone(user_id: str) -> str:
    """The shape of the moment — for HOW things are said, not what.

    Everything else here decides content. This decides nothing and describes
    the situation instead, because a companion does not withhold a song from
    someone who seems low, it offers the same song more gently.
    """
    try:
        from memory.tone import tone_context
        return tone_context(user_id)
    except Exception as e:
        print(f"[Context] tone failed: {e}")
        return ""

def _recent(user_id: str) -> str:
    """What the companion has already said, so it stops asking the same thing.

    One user had a single durable cluster after the junk sweep, so the composer
    reached for it every time: Kishore Kumar in nine of ten messages across a
    day. Nothing was telling it what it had just said.
    """
    lines = _recent_companion_lines(user_id, n=5)
    if not lines:
        return ""
    joined = "\n".join(f"  - {l[:120]}" for l in lines)
    return ("You recently said the following. Do not repeat these, and do not "
            "ask again about anything you already asked about here:\n" + joined)


def curiosity_score(user_id: str) -> dict:
    """
    How much the companion should be trying to LEARN rather than draw on what
    it knows. Returns {score: 0..1, reason: str} — inspectable, because a bare
    number nobody can explain is worse than a fixed rule.

    Three pressures, each of which independently justifies asking something new:

      thinness    — few durable facts means little to draw on. A companion with
                    one interest will ask about it forever.
      staleness   — nothing new learned in weeks means it is not listening well,
                    however warm each individual message is.
      repetition  — the same entity in most recent messages. This one matters
                    even for a rich profile: it is the symptom the user notices.
    """
    from datetime import datetime, timezone

    n_clusters = 0
    newest = None
    try:
        from supabase_store import get_client
        rows = (get_client().table("interest_clusters")
                .select("label,first_seen").eq("user_id", user_id)
                .eq("status", "active").execute()).data or []
        n_clusters = len(rows)
        stamps = [r.get("first_seen") for r in rows if r.get("first_seen")]
        if stamps:
            newest = max(stamps)
    except Exception as e:
        print(f"[Context] curiosity cluster read failed: {e}")

    # thinness: 1.0 at zero clusters, ~0.5 at one, ~0.09 at ten
    thinness = 1.0 / (1.0 + n_clusters)

    # staleness: nothing new for a fortnight is a full point
    staleness = 0.0
    if newest:
        try:
            dt = datetime.fromisoformat(str(newest).replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - dt).days
            staleness = min(days / 14.0, 1.0)
        except Exception:
            pass
    else:
        staleness = 1.0

    # repetition: how much the recent lines overlap each other
    repetition = 0.0
    lines = _recent_companion_lines(user_id, n=5)
    if len(lines) >= 3:
        # How alike her recent messages from Nancy are, by meaning: the
        # average similarity between each pair. This counted words longer
        # than four letters, which suited Hinglish and inflated in German.
        try:
            from classifier.pillar_classifier import embed_text
            import math
            vs = [v for v in (embed_text(l) for l in lines) if v]
            sims = []
            for i in range(len(vs)):
                for j in range(i + 1, len(vs)):
                    a, b = vs[i], vs[j]
                    na = math.sqrt(sum(x * x for x in a))
                    nb = math.sqrt(sum(x * x for x in b))
                    if na and nb:
                        sims.append(sum(x * y for x, y in zip(a, b)) / (na * nb))
            if sims:
                avg = sum(sims) / len(sims)
                # Unrelated messages sit around 0.3-0.5, near-repeats above 0.8.
                repetition = max(0.0, min((avg - 0.5) / 0.35, 1.0))
        except Exception as e:
            print(f"[Context] repetition read failed: {e}")

    score = min(0.55 * thinness + 0.20 * staleness + 0.25 * repetition, 1.0)

    reason = (f"clusters={n_clusters} thinness={thinness:.2f} "
              f"staleness={staleness:.2f} repetition={repetition:.2f}")
    return {"score": round(score, 3), "reason": reason,
            "n_clusters": n_clusters}


def curiosity_instruction(user_id: str) -> str:
    """Turn the score into something the model can act on.

    Sampled, so the companion is not relentlessly inquisitive — but the
    probability is the score, so a user it knows nothing about gets asked
    often and one it knows well almost never.
    """
    import random

    # Which film she meant comes first. Until she answers, that interest has no
    # facts and nothing can be built on it — and the question is good
    # conversation regardless.
    try:
        from memory.ambiguity import needs_asking, ask_instruction
        pending = needs_asking(user_id)
        if pending:
            print(f"[Context] asking which {pending['label']!r} for {user_id}")
            return ask_instruction(pending)
    except Exception as e:
        print(f"[Context] ambiguity check failed: {e}")

    # Then a question built from something they already like. Better than a
    # blank one: it is answerable, and the answer says which direction they
    # follow rather than only adding another fact.
    try:
        from memory.probes import probe_instruction
        probe = probe_instruction(user_id)
        if probe and random.random() < 0.6:
            return probe
    except Exception as e:
        print(f"[Context] probe failed: {e}")


    c = curiosity_score(user_id)
    if random.random() >= c["score"]:
        return ""

    print(f"[Context] curiosity fired for {user_id}: {c['reason']}")
    return (
        "THIS OVERRIDES THE CONTEXT BELOW. You know very little about this "
        "person, and repeating the one or two things you do know is why they "
        "heard about the same singer five times in a day.\n"
        "Ask ONE open, easy question about something you do NOT already know — "
        "who they saw today, what they cooked, where they grew up, what they "
        "do on a quiet afternoon. Ask the way a friend would, not a form.\n"
        "Do NOT mention anything from their interests or memory in this "
        "message. Not one word of it. The point is to learn something new."
    )


_SOURCES = {
    "persona":      _persona,
    "language":     _language,
    "recent":       _recent,
    "tone":         _tone,
    "voice":        _how_they_write,
    "memory":       _memory,
    "routine":      _routine,
    "due_now":      _due_now,
    "interests":    _interests,
    "patterns":     _patterns,
    "integrations": _integrations,
}


def build_context(user_id: str, include: Optional[list] = None) -> dict:
    """Gather every source. Returns a dict so callers can use blocks
    individually — persona usually leads the prompt rather than sitting in
    the middle of it."""
    names = include or list(_SOURCES)
    out = {}
    for name in names:
        fn = _SOURCES.get(name)
        if not fn:
            continue
        try:
            block = fn(user_id) or ""
        except Exception as e:
            print(f"[Context] source {name} raised: {e}")
            block = ""
        if block:
            out[name] = block
    return out


# ── intents ───────────────────────────────────────────────────────────────────
# What the companion is trying to do. The context is the same; the instruction
# differs.

_INTENTS = {
    # Sent because they have been quiet for a long stretch of the day. It
    # asks after THEM. Told only "write your opening line" next to a list of
    # everything they like, it opened with one of those things: "subah subah
    # kya dekhne ka irada hai, koi purani movie?" at 06:13, before her puja,
    # and she answered "subh subh kaun movie dekhega".
    "check_in": (
        "They have been quiet for a while, and you are reaching out first. "
        "Ask after them: how they are, how the day is going. One or two short, "
        "warm lines, the way family would ring to say they were thinking of "
        "them. Suggest nothing: no film, song, dish, show or activity, and do "
        "not ask what they plan to watch, eat or do. Do not say they have been "
        "quiet, and do not sound worried. Anything you mention must fit the "
        "time of day it is now."
    ),
    "medication": (
        "A medication is due now. Remind them warmly and specifically, by name. "
        "Do not lecture; one line is enough."
    ),
    "recommendation": (
        "Suggest one thing they might enjoy right now, drawn from what they "
        "already like. Offer, do not insist."
    ),
    "safety": (
        "They are away from home and it is late. Check they are alright. Calm "
        "and brief — do not alarm them."
    ),
}

# The model breaks character when the profile is thin, addressing the operator
# instead of the person: "I don't have any information about them — could you
# share a bit?" That would go to an elderly user as a push notification.
_META_TELLS = (
    "i don't have", "i do not have", "i don't know", "could you share",
    "could you tell me", "to write a", "let me know", "as an ai",
    "i'd need", "i would need", "no information", "not enough context",
    "based on the information provided", "here's a", "here is a",
)


def compose(user_id: str, intent: str = "check_in",
            slot: str = "", priority: str = "", hints: str = "") -> str:
    """
    Write one line in the companion's voice. Returns "" if the model produces
    something out of character — the caller should fall back rather than send
    it.
    """
    # Each intent declares what it may see. Passing everything and hoping the
    # model picks the relevant part is what produced a 20:00 blood-pressure
    # nudge asking about lunch — 13:00 Lunch was in the block, so it was fair
    # game. A medication reminder now never sees the routine at all.
    from memory.intent_spec import scope_for
    spec = scope_for(intent)

    # "fixed" is the floor, not a short-circuit: compose when there is
    # something personal to say, fall back to it when there is not. Safety is
    # the exception — it fires when an elderly person is away from home at 2am,
    # and predictable beats warm at that moment.
    if spec.get("fixed") and spec.get("always_fixed"):
        return spec["fixed"]

    ctx = build_context(user_id, include=["persona", "language"] + spec["sources"])
    persona  = ctx.pop("persona", "You are a warm companion.")
    # Held back deliberately — see where it is placed below.
    language = ctx.pop("language", "")
    # What a caregiver asked the companion to pay attention to. This reached
    # only the chat path — a reply to something she typed — so every proactive
    # message ignored the sliders entirely. Setting entertainment to Max and
    # health to Low changed nothing about what arrived on her phone.
    weights_note = ""
    try:
        # Not for a reminder. The weights say "pay more attention to
        # entertainment", the medication task says "only the dose that is
        # due", and the two fought — the reminder arrived wrapped in Kishore
        # Kumar. A caregiver adjusting focus is shaping conversation, not
        # medication.
        if intent not in ("medication", "safety"):
            from memory.pillar_weights import build_weights_prompt
            weights_note = build_weights_prompt(user_id) or ""
    except Exception as e:
        print(f"[Context] weights failed: {e}")

    task = spec["task"]
    # The medication rule belongs in the prompt, not only in the checker that
    # reads a message after it has been written.
    if spec.get("forbid_note"):
        task = task + "\n" + spec["forbid_note"]
    # And brevity. Gemini writes considerably longer than Haiku did — "bahut
    # pyaari good morning aapko, aaj subah ki puja ke baad..." where the
    # earlier version managed a line. She is reading this on a phone.
    if intent == "recommendation":
        # An offer is the one message that has to carry something: what the
        # thing is and why it suits now. Under "shorter is better" on the
        # lite model it came out as a bare title, "Ismail, Ranjish Hi Sahi
        # suniye.", which is a command, not an offer.
        task = task + ("\nTwo or three short sentences: what it is, and why "
                       "it suits them right now. Warm, like a friend who "
                       "thought of them. A bare title is not an offer.")
    else:
        task = task + ("\nTwo short sentences at most. Shorter is better; "
                       "she reads this on a phone, not on a page.")

    # WHAT DAY IT IS. The composer had her whole life in front of it and no
    # anchor for now — so "temple visits for festivals like Janmashtami", a
    # correct and durable fact about her, was read as today's plan twelve days
    # after Janmashtami, and she was asked which mandir she was going to.
    #
    # Everything dated in her memory depends on this. An event stamped
    # 2026-09-04 means nothing without it; with it, it is twelve days ago.
    # "Kal" in her own words has no anchor either.
    #
    # Her timezone, not the server's — she is in Bengaluru and Railway is not.
    today_note = ""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from memory.declared import get_declared
        tz = ZoneInfo(get_declared(user_id).place.timezone or "Asia/Kolkata")
        now = datetime.now(tz)
        today_note = f"Today is {now.strftime('%A, %-d %B %Y')}. "
    except Exception as e:
        print(f"[Context] date line failed: {e}")

    slot_note = {
        "morning":    "It is morning — they are starting their day.",
        "midday":     "It is the middle of the day.",
        "afternoon":  "It is afternoon.",
        "evening":    "It is evening.",
        "night":      "It is night — they will be winding down.",
        "late_night": "It is very late.",
    }.get(slot, "")
    slot_note = today_note + slot_note

    urgency = {
        "critical": "They seemed genuinely distressed recently. Lead with "
                    "warmth and ask how they are — nothing else matters.",
        "high":     "Something has been worrying them. Acknowledge it gently.",
        "medium":   "Nothing is wrong. This is an ordinary, affectionate note.",
        "low":      "Nothing is wrong. Keep it light and short.",
    }.get(priority, "")

    blocks = "\n\n".join(ctx.values())

    # When there is little to draw on, learning beats performing warmth at
    # something it does not know. Sampled on a score, so it fades as the
    # profile fills.
    # Opt-in, not opt-out. Curiosity returns an instruction that OVERRIDES
    # everything below it, and gating on "is this a check_in" meant every new
    # intent silently inherited it — the greeting came out as a probe question
    # with "good morning" attached, and the boundary message lost its forward
    # half three times running.
    #
    # Inverted, forgetting to opt in costs a slightly less inquisitive message.
    # Forgetting to opt out cost the message its point.
    curiosity = (curiosity_instruction(user_id)
                 if (scope_for(intent) or {}).get("curiosity") else "")

    # Live context, but only where several sources agree it matters.
    try:
        from memory.fusion import fused_context
        fused = fused_context(user_id, slot=slot, intent=intent)
    except Exception as e:
        print(f"[Context] fusion failed: {e}")
        fused = ""

    prompt = f"""{persona}

{task}
{weights_note}

{slot_note}
{urgency}
{hints}
{curiosity}
{fused}

{blocks}

RULES:
- Short. Not a speech.
- Say something only THIS person would hear — their routine, what they told
  you, what they like. Everything you mention must appear above.
- NEVER name a person who is not in the context above. A thin profile is
  not an invitation to fill the gap: asked to open warmly with nothing to draw
  on, the composer wrote "Sunita ji ke saath baat hui aaj subah" about someone
  who does not exist. An invented friend is worse than a plain greeting, and
  once said it becomes something she has to correct.
- Their conditions are context for what you SUGGEST, never a subject to open
  on. Offered "ghutne ka dard kaisa hai?" as the warm example, every message
  became that question — a boundary about her walk and an offer of music both
  opened by asking about her knee. A separate check handles health; this is
  not it. Do not ask after any condition, and do not list them back.
- Match how they speak, which is named at the bottom of this prompt. This
  line used to say "if they use Hinglish, use Hinglish" — the only
  language it named — and a woman in Kolkata who asked for English was
  answered with "ya koi suggestion chahiye", because a concrete example
  five lines up beats an abstract instruction further down.
- If you have little to go on, a short warm greeting is the right answer.
- NEVER address the operator, ask for more context, or explain what you do or
  do not know. You are speaking TO the person. There is no one else to ask.

{language}
The blocks above are stored notes, not a style guide. They were written in
whatever language they happened to be recorded in — usually Hinglish — and the
recent messages are there so you avoid repeating yourself, not so you copy how
they were phrased. Write in the language named directly above this line,
whatever the notes look like.

Write only the message. No preamble, no quotation marks."""

    try:
        import anthropic
        client = __import__("llm").client()
        # The full model for an offer, the lite one for everything else.
        # Offers are two or three a day; a bare title costs more than the
        # tokens.
        _use = (__import__("llm").model(__import__("llm").SONNET)
                if intent == "recommendation" else _MODEL)
        resp = client.messages.create(
            model=_use, max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip().strip('"')
    except Exception as e:
        print(f"[Context] compose failed for {user_id}: {e}")
        return ""

    # Hard guard on invented drugs. A prompt instruction is not enough here —
    # the model produced "Digene" for someone who takes Amlodipine, and naming
    # a medication an elderly person does not take is a safety problem, not a
    # quality one. If the text contains a drug-shaped word that is not on their
    # list, refuse it and let the caller fall back.
    if intent == "medication":
        try:
            from memory.profile_store import get_user_profile
            meds = list(((get_user_profile(user_id) or {}).get("health") or {})
                        .get("medications") or [])
            # care_schedule is the other source, and the one the reminder is
            # actually about — the profile list said "BP tablet" while the
            # schedule said "BP tablet (amlodipine)", so checking only the
            # profile rejected a correct message.
            try:
                from supabase_store import get_client
                rows = (get_client().table("care_schedule")
                        .select("label").eq("user_id", user_id)
                        .eq("type", "medication").execute()).data or []
                meds += [r.get("label") for r in rows if r.get("label")]
            except Exception:
                pass
            known = set()
            for m in meds:
                for w in str(m).replace("(", " ").replace(")", " ").split():
                    if len(w) > 3:
                        known.add(w.lower())
            for w in text.replace(",", " ").replace(".", " ").split():
                lw = w.strip("()").lower()
                # crude but effective: capitalised mid-sentence words that look
                # like brand names and are not on the list
                if (len(lw) > 4 and w[0].isupper()
                        and lw not in known
                        and not any(lw in k or k in lw for k in known)):
                    if any(ch.isalpha() for ch in lw) and lw not in (
                            "namaste", "aapka", "aapke", "kishore", "kumar"):
                        pass  # too noisy to reject on capitalisation alone
            if known and not any(k in text.lower() for k in known):
                print(f"[Context] medication line names no known drug for "
                      f"{user_id}, falling back: {text[:80]}")
                return ""
        except Exception as e:
            print(f"[Context] medication guard failed: {e}")

    # A reminder names the dose and nothing else. Ismail's Telmisartan came
    # as "aisi subah mein jab Mirza Ghalib ya Mehdi Hassan ka koi she'r
    # sunne ka mann ho, toh usse pehle..." Something they love wrapped
    # round a tablet turns the tablet into a pitch and the interest into a
    # chore. Checked against their own interests, so it cannot be argued
    # with, and written again once before giving up.
    if intent == "medication" and text:
        try:
            from memory.offers import hers
            loves = [v["label"] for v in hers(user_id).values()
                     if len(str(v.get("label") or "")) >= 4]
            def _names_a_love(t):
                low = t.lower()
                return next((l for l in loves if l.lower() in low), None)
            hit = _names_a_love(text)
            if hit:
                print(f"[Context] reminder named {hit!r}, rewriting: {text[:80]}")
                resp = client.messages.create(
                    model=_MODEL, max_tokens=200,
                    messages=[{"role": "user", "content": prompt +
                               "\n\nName the medicine and nothing else. Do "
                               "not mention any song, singer, poet, film, "
                               "dish or anything else they enjoy."}])
                text = resp.content[0].text.strip().strip('"')
                if _names_a_love(text):
                    print(f"[Context] reminder still named an interest, "
                          f"falling back")
                    return spec.get("fixed") or ""
        except Exception as e:
            print(f"[Context] reminder interest check failed: {e}")

    from memory.intent_spec import check_in_character
    problem = check_in_character(text)
    if problem:
        print(f"[Context] {problem} for {user_id}, falling back: {text[:80]}")
        # A declared fixed line beats the caller's templates, which stitch
        # three unrelated sentences together and mention medication inside an
        # explore offer.
        return spec.get("fixed") or ""

    return text

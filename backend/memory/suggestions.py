"""
SUGGESTIONS — what the companion offered, and what came back.

Without this the loop is open: the companion says "Lata ji ka gaana sunoge?",
the user says "nahi, abhi mann nahi hai", and nothing connects the two. The
refusal reaches the extractor as an unattached negative with no subject, so the
companion learns nothing and offers the same thing tomorrow.

WEIGHTS
Reactions are not equal, and the differences matter more than they look:

  accepted            +0.2   Weak on purpose. For an elderly person talking to a
                             companion styled as their son, "haan chalao" is
                             often politeness — declining feels rude. Real
                             evidence is them raising it themselves later, which
                             already flows through normal extraction at full
                             weight.
  declined_timing      0.0   "Abhi nahi", "baad mein" says something about the
                             moment, not the thing. Counting it against the
                             interest would teach the companion to stop offering
                             what someone likes because they were tired once.
  declined_preference -0.4   "Mann nahi hai", "pasand nahi". Meaningful, but one
                             is not a verdict: three of these drive current_state
                             negative and the interest drops out on its own.
  no_response         -0.1   Ambiguous. They may not have seen it. Barely counts,
                             but a run of them says the suggestions are landing
                             badly.

Nothing here decides that something is disliked. The weights feed sentiment,
derive_trajectory averages it, and computed_dislikes reads the result — so the
threshold lives in one place rather than being restated as a rule.
"""
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

# After this a reply is about something else. Two hours was far too generous —
# by then any "nahi" belongs to a different conversation.
PENDING_MINUTES = 30

REACTION_WEIGHT = {
    "accepted":            0.2,
    "declined_timing":     0.0,
    "declined_preference": -0.4,
    "no_response":         -0.1,
}


# ── choosing what to offer ────────────────────────────────────────────────────


def _last_reaction_was_refusal(user_id: str, cluster_id: str) -> bool:
    """Did they turn this down the last time it came up?

    Deliberately reads the most recent reaction rather than the rolled-up
    sentiment: recency matters more than the average when the question is
    "should I offer this again", and a single clear refusal should settle it
    even if the running average has not caught up.
    """
    try:
        from supabase_store import get_client
        rows = (get_client().table("suggestions")
                .select("reaction,reacted_at")
                .eq("user_id", user_id).eq("cluster_id", cluster_id)
                .not_.is_("reaction", "null")
                .order("reacted_at", desc=True).limit(1).execute()).data or []
    except Exception as e:
        print(f"[Suggest] last-reaction read failed: {e}")
        return False
    return bool(rows) and rows[0].get("reaction") == "declined_preference"


def _moment(user_id: str) -> dict:
    """Everything about now that should bear on what is offered.

    All of this already existed and none of it reached the picker, which is how
    idli-dosa arrived at 8:41pm.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    out = {"now_min": 12 * 60, "rhythm": {}, "at_home": True, "weather": None}
    try:
        from memory.declared import get_declared
        d = get_declared(user_id)
        tz = ZoneInfo(d.place.timezone)
        now = datetime.now(tz)
        out["now_min"] = now.hour * 60 + now.minute
        out["at_home"] = not d.place.away
        out["rhythm"] = {
            "wake":     d.rhythm.wake,
            "sleep":    d.rhythm.sleep,
            "meals":    d.rhythm.meals,
            "routines": d.rhythm.routines,
        }
    except Exception as e:
        print(f"[Suggest] moment read failed: {e}")

    try:
        from memory.fusion import _weather
        out["weather"] = _weather(user_id)
    except Exception:
        pass
    return out


def _weather_blocks(category: str, weather: dict) -> bool:
    """Rain does not stop a song. It does stop gardening."""
    if not weather or category != "shauk":
        return False
    desc = (weather.get("description") or "").lower()
    return any(w in desc for w in ("rain", "storm", "shower", "thunder"))


def pick_suggestion(user_id: str) -> Optional[dict]:
    """
    Choose the cluster worth surfacing, rather than letting the composer reach
    for whatever reads well. Returns {cluster_id, label, category} or None.

    Prefers things they like and have not been offered recently. A cluster that
    was declined on preference is skipped outright — the point of recording
    reactions is to stop offering.
    """
    try:
        from supabase_store import get_client
        db = get_client()
        rows = (db.table("interest_clusters")
                .select("id,label,pillar,relationship,current_state,"
                        "event_count,strength,attributes")
                .eq("user_id", user_id).eq("status", "active")
                .order("strength", desc=True).limit(40).execute()).data or []
    except Exception as e:
        print(f"[Suggest] cluster read failed: {e}")
        return None

    if not rows:
        return None

    # The moment. None of this reached the picker before, which is how a lunch
    # dish was offered at 8:41pm: it ordered by strength and took the first
    # thing not offered recently.
    moment = _moment(user_id)
    from memory.categories import offerable_now, busy_with_routine
    if busy_with_routine(moment["now_min"], moment["rhythm"]):
        print(f"[Suggest] {user_id} is mid-routine — staying quiet")
        return None

    # Anything offered in the last few days, whatever the outcome — repeating
    # yourself is its own failure.
    recent_ids = set()
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        prev = (db.table("suggestions").select("cluster_id")
                .eq("user_id", user_id).gte("created_at", since)
                .execute()).data or []
        recent_ids = {p["cluster_id"] for p in prev if p.get("cluster_id")}
    except Exception as e:
        print(f"[Suggest] recent read failed: {e}")

    best = None
    eligible = []
    for r in rows:
        if r["id"] in recent_ids:
            continue
        if (r.get("pillar") or "") in ("HEALTH_WELLNESS", "FAMILY"):
            continue
        state = r.get("current_state")
        if state is not None and state < 0:
            continue                      # the average has turned against it

        # The average alone is not enough. One preference decline against a
        # stated liking leaves current_state at +0.067 — still positive — so
        # someone could say "mujhe unke gaane pasand nahi" and be offered the
        # same thing tomorrow. A recent explicit no overrides an old yes.
        if _last_reaction_was_refusal(user_id, r["id"]):
            continue
        rel = (r.get("relationship") or "").lower()
        if rel in ("concern", "person", "feeling", "action"):
            continue

        # Wrong time is a hard no, not a ranking penalty. Food after dinner,
        # a film at breakfast, gardening in the rain — each is worse than
        # saying nothing, and saying nothing is a correct answer.
        attrs = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        cat = attrs.get("category") or ""
        if cat:
            if not offerable_now(cat, moment["now_min"], moment["rhythm"],
                                 moment["at_home"]):
                continue
            if _weather_blocks(cat, moment["weather"]):
                continue

        eligible.append(r)

    if not eligible:
        return None

    # Drawn by strength rather than taken in order. Ordering by strength and
    # keeping the first survivor meant the same subject won every time until
    # its three-day cooldown, then the next one did — ten picks in a row
    # returned Kumar Sanu, and before that ten returned Shakira. Preference
    # without variety is mechanical, and she notices.
    #
    # Squared, so a strong interest is clearly favoured without the weaker
    # ones becoming unreachable: at 8.9 against 4.0, Kishore Kumar comes up
    # about five times as often as Gadar, not always and not never.
    import random
    weights = [max(float(r.get("strength") or 1.0), 0.1) ** 2 for r in eligible]
    best = random.choices(eligible, weights=weights, k=1)[0]
    # The category comes along: it decides what kind of thing can be fetched
    # for this — a song, a recipe, or nothing at all.
    attrs = best.get("attributes")
    return {"cluster_id": best["id"], "label": best["label"],
            "pillar": best.get("pillar"),
            "attributes": attrs if isinstance(attrs, dict) else {}}


def record_suggestion(user_id: str, cluster_id: Optional[str], label: str,
                      intent: str = "recommendation",
                      session_id: Optional[str] = None) -> Optional[str]:
    """Write down that we offered this, so the next message can be read as a
    reply to it."""
    try:
        from supabase_store import get_client
        row = (get_client().table("suggestions").insert({
            "user_id": user_id, "cluster_id": cluster_id,
            "label": label[:200], "intent": intent,
            "session_id": session_id or None,
        }).execute()).data
        return row[0]["id"] if row else None
    except Exception as e:
        print(f"[Suggest] record failed: {e}")
        return None


# ── reading the reply ─────────────────────────────────────────────────────────

def pending_suggestion(user_id: str) -> Optional[dict]:
    """The open suggestion, if there is one and it is still fresh."""
    try:
        from supabase_store import get_client
        since = (datetime.now(timezone.utc) - timedelta(minutes=PENDING_MINUTES)).isoformat()
        rows = (get_client().table("suggestions")
                .select("id,cluster_id,label,intent,created_at")
                .eq("user_id", user_id).is_("reaction", "null")
                .gte("created_at", since)
                .order("created_at", desc=True).limit(1).execute()).data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[Suggest] pending read failed: {e}")
        return None


def classify_reaction(offer_label: str, user_text: str) -> Optional[str]:
    """
    Is this reply about the offer, and if so what kind of no?

    The distinction between "not now" and "not this" is the whole point. A
    keyword check cannot make it — "nahi, abhi mann nahi hai" and "nahi, mujhe
    woh pasand nahi" share their first word and mean opposite things.
    """
    prompt = f"""The companion offered: "{offer_label}"
The person replied: "{user_text}"

Is the reply a response to that offer? Answer with ONE word:

accepted            — they said yes, or asked for it
declined_timing     — no for now: busy, tired, later, not in the mood right now
declined_preference — no to the thing itself: they do not like it, do not want it
unrelated           — the reply is about something else entirely

"Not in the mood right now" is declined_timing. "I don't like that" is
declined_preference. When the reply could be either DECLINE, choose
declined_timing — treating a tired evening as a dislike would make the
companion stop offering something they enjoy.

But a reply that simply talks about something else is "unrelated", not a
decline. "My knee is really hurting today" answers nothing; the person changed
the subject, and the offer is still open. Only call it a decline if they are
actually saying no to what was offered.

One word, nothing else."""
    try:
        import anthropic
        client = __import__("llm").client()
        resp = client.messages.create(
            model=__import__("llm").model("claude-haiku-4-5-20251001"), max_tokens=10,
            messages=[{"role": "user", "content": prompt}])
        answer = resp.content[0].text.strip().lower().strip(".")
        if answer in REACTION_WEIGHT or answer == "unrelated":
            return answer
        print(f"[Suggest] unrecognised reaction {answer!r}")
        return None
    except Exception as e:
        print(f"[Suggest] classify failed: {e}")
        return None


def apply_reaction(user_id: str, suggestion: dict, reaction: str,
                   session_id: Optional[str] = None) -> bool:
    """Close the suggestion and let the reaction move the cluster's sentiment.

    The weight becomes an ordinary event, so derive_trajectory folds it into
    current_state the same way a spoken preference would. No special path, and
    the "three declines" threshold is emergent rather than written down.
    """
    weight = REACTION_WEIGHT.get(reaction)
    if weight is None:
        return False

    try:
        from supabase_store import get_client
        db = get_client()
        db.table("suggestions").update({
            "reaction": reaction,
            "reacted_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", suggestion["id"]).execute()

        cid = suggestion.get("cluster_id")
        if cid:
            db.table("user_behavioral_events").insert({
                "user_id": user_id, "cluster_id": cid,
                "session_id": session_id or None,
                "pillar": "GENERAL", "sub_pillar": "reaction",
                "value": suggestion.get("label", "")[:200],
                "surface_form": reaction,
                "strength": 0.3, "sentiment": weight, "salience": 0.4,
                "event_type": reaction[:40],
                "relationship_type": "preference",
                "source": "suggestion_reaction",
            }).execute()

            from memory.profile_enricher import recompute_cluster_trajectory
            recompute_cluster_trajectory(user_id, cid)

        print(f"[Suggest] {suggestion.get('label')!r} -> {reaction} ({weight:+})")
        return True
    except Exception as e:
        print(f"[Suggest] apply failed: {e}")
        return False


def handle_reply(user_id: str, user_text: str,
                 session_id: Optional[str] = None) -> Optional[str]:
    """
    Called on each user message. Costs nothing when no suggestion is open,
    which is most turns.
    """
    pending = pending_suggestion(user_id)
    if not pending:
        return None

    reaction = classify_reaction(pending.get("label", ""), user_text)
    if not reaction or reaction == "unrelated":
        # Leave it open — they may still answer. The expiry sweep will close it.
        return None

    apply_reaction(user_id, pending, reaction, session_id)
    return reaction


def expire_stale(user_id: Optional[str] = None) -> int:
    """Close suggestions nobody answered. Silence is weak evidence, but a run of
    it says the suggestions are landing badly."""
    try:
        from supabase_store import get_client
        db = get_client()
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=PENDING_MINUTES)).isoformat()
        q = (db.table("suggestions")
             .select("id,user_id,cluster_id,label")
             .is_("reaction", "null").lt("created_at", cutoff))
        if user_id:
            q = q.eq("user_id", user_id)
        rows = q.execute().data or []
    except Exception as e:
        print(f"[Suggest] expire read failed: {e}")
        return 0

    for r in rows:
        apply_reaction(r["user_id"], r, "no_response")
    return len(rows)

def moment_facts(user_id: str, moment: dict = None) -> str:
    """The world as it is, for whoever is writing the next message.

    Shared by offers and boundaries on purpose: an offer that knows it is
    raining and a follow-up that does not would contradict each other an hour
    apart.
    """
    m = moment or _moment(user_id)
    lines = []

    w = m.get("weather") or {}
    if w:
        bits = []
        temp = w.get("temp_c")
        if temp is not None:
            bits.append(f"{round(float(temp))}°C")
        if w.get("description"):
            bits.append(str(w["description"]))
        if bits:
            lines.append("Weather where they are: " + ", ".join(bits) + ".")
        # The route writes this in their language and it is better than
        # anything assembled from the raw fields.
        if w.get("advice"):
            lines.append(str(w["advice"]))

    v = m.get("valence")
    flags = m.get("flags") or []
    if v is not None and v <= -0.3:
        lines.append(
            "The last few conversations were heavy. Do NOT mention that or ask "
            "about it. Offer something familiar rather than something new — "
            "this is not the afternoon to introduce them to a singer they have "
            "never heard of.")
    elif v is not None and v >= 0.3:
        lines.append("The last few conversations went well.")

    # Named plainly, because an offer that cuts across a bad knee is worse than
    # no offer. What to do about it is the composer's judgement.
    # Deliberately NOT told. "Do not raise it" was in the instruction and both
    # the offer and the boundary opened with "aapke ghutne ka dard kaisa hai" —
    # naming a thing is more tempting than not naming it, and the only reliable
    # way to keep it out of the message is to keep it out of the prompt.
    #
    # It still shapes the choice: pick_suggestion reads the same flags and
    # leans familiar over novel. The composer simply never learns why.

    if not m.get("at_home"):
        lines.append("They are away from home at the moment.")

    if not lines:
        return ""
    return ("\n\nWHAT IS TRUE RIGHT NOW — facts, not instructions about tone:\n"
            + "\n".join(f"- {l}" for l in lines))

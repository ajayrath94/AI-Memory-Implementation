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
                .select("id,label,pillar,relationship,current_state,event_count,strength")
                .eq("user_id", user_id).eq("status", "active")
                .order("strength", desc=True).limit(40).execute()).data or []
    except Exception as e:
        print(f"[Suggest] cluster read failed: {e}")
        return None

    if not rows:
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
    for r in rows:
        if r["id"] in recent_ids:
            continue
        if (r.get("pillar") or "") in ("HEALTH_WELLNESS", "FAMILY"):
            continue
        state = r.get("current_state")
        if state is not None and state < 0:
            continue                      # they told us they did not want it
        rel = (r.get("relationship") or "").lower()
        if rel in ("concern", "person", "feeling", "action"):
            continue
        best = r
        break

    if not best:
        return None
    return {"cluster_id": best["id"], "label": best["label"],
            "pillar": best.get("pillar")}


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
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=10,
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

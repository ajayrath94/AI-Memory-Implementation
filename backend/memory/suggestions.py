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

# Unless it is her FIRST word since the offer. Pranayam was offered at 10:03,
# closed as no_response at 10:33, and at 10:53 she answered it — "abhi puja
# karna hai, sham ko dekhenge", a plain not-now — to nothing. She reads her
# phone when she reads it. Nothing else has been said in between, so there
# is no other conversation for her reply to belong to.
FIRST_REPLY_MINUTES = 180

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




# Cached for the day, because the note it reads only changes at session end.
_SETTLED: dict = {}


def _decided_today(user_id: str) -> set:
    """Categories she has already made up her mind about today.

    Read from the day's note in the thread. If she has said she is cooking
    chicken, food is settled; if she has said she is going to the temple,
    bhakti is. Everything else stays open.

    The note is written at session end, so a plan made at breakfast is known
    once that conversation closes — the same lag the thread has generally.
    """
    from datetime import date
    key = (user_id, date.today().isoformat())
    if key in _SETTLED:
        return _SETTLED[key]

    try:
        from memory.thread import recent_days
        rows = recent_days(user_id, 1)
        if not rows:
            _SETTLED[key] = set()
            return set()
        today_note = rows[0]
        if str(today_note.get("happened_on"))[:10] != date.today().isoformat():
            _SETTLED[key] = set()
            return set()
        note = str(today_note.get("text") or "")
    except Exception as e:
        print(f"[Suggest] settled read failed: {e}")
        return set()

    if len(note) < 10:
        _SETTLED[key] = set()
        return set()

    prompt = f"""Someone's day so far:

{note}

Which of these have they already DECIDED about, so that suggesting an
alternative would be unwelcome? JSON only:

{{"settled": ["khana", "sangeet", "dekhna", "bhakti", "shauk"]}}

  khana    they have said what they are eating or cooking
  sangeet  they have said what they are listening to
  dekhna   they have said what they are watching
  bhakti   they have said where they are going or what they are observing
  shauk    they have said what they are doing with their time

Only when they have SAID SO. "Planned to get chicken for lunch" settles
khana. "Had breakfast" does not settle anything — everyone eats breakfast.

An empty list is the usual answer.

No prose."""

    try:
        from llm import ask
        import json as _j
        raw = ask(prompt, max_tokens=120).replace("```json", "").replace("```", "")
        out = {str(s).strip().lower()
               for s in (_j.loads(raw.strip()).get("settled") or [])}
    except Exception as e:
        print(f"[Suggest] settled check failed: {e}")
        out = set()

    _SETTLED[key] = out
    return out

_DECLINING: dict = {}


def _declining(user_id: str) -> set:
    """Subjects she enjoys less each time. Cached for the day."""
    from datetime import date as _d
    key = (user_id, _d.today().isoformat())
    if key in _DECLINING:
        return _DECLINING[key]
    out = set()
    try:
        from memory.topics import declining
        for d in (declining(user_id) or []):
            s = str(d.get("subject") or "").strip().lower()
            if s:
                out.add(s)
    except Exception as e:
        print(f"[Suggest] declining read failed: {e}")
    _DECLINING[key] = out
    return out

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
                        "event_count,strength,attributes,last_event")
                .eq("user_id", user_id).eq("status", "active")
                # Events share this table and are not things to offer. "Beta
                # Arjun aaya tha" is a memory, not a suggestion.
                .neq("kind", "event")
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

    # What she has already decided today.
    #
    # She said at breakfast she was going to the market for chicken and would
    # make curry for lunch. The picker knew none of it — it reads her stored
    # interests and nothing about today — so it would have offered her khichdi
    # while the chicken was on the stove.
    #
    # Offering an alternative to someone who has decided is worse than
    # offering nothing: it says plainly that the thing she said was not heard.
    settled = _decided_today(user_id)
    if settled:
        print(f"[Suggest] {user_id} has settled: {', '.join(settled)}")

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

    # What this day of the week favours. A rhythm overrides the draw
    # outright; a lean only makes something likelier, which is where most
    # patterns live — two Sundays out of three is not certainty.
    try:
        from memory.leanings import leanings as _leanings
        _lean = _leanings(user_id)
    except Exception as _le:
        print(f"[Suggest] leaning read failed: {_le}")
        _lean = {}

    best = None
    eligible = []
    for r in rows:
        if r["id"] in recent_ids:
            continue
        if (r.get("pillar") or "") in ("HEALTH_WELLNESS", "FAMILY"):
            continue

        # She has already decided about this. Offering an alternative to
        # someone who has made up her mind says plainly that the thing she
        # said was not heard.
        _a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        if settled and (_a.get("category") or "") in settled:
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

        # Something she is souring on. topics tracks how she feels about each
        # subject over weeks, and declining() reports it — "was +0.7, now
        # -0.1" — and until now only the dashboard read it. A thing she
        # enjoys less each time she mentions it should not keep being offered.
        if r["label"].lower() in _declining(user_id):
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
    # Strength squared, lifted by what this weekday favours.
    #
    # A rhythm — three mentions, seventy per cent on one day — overrides the
    # draw outright and is handled before this. A lean is the shoulder of
    # that: two Sundays out of three makes chicken likelier on a Sunday than
    # khichdi, without pretending to be certain.
    weights = []
    for r in eligible:
        w = max(float(r.get("strength") or 1.0), 0.1) ** 2
        lift = _lean.get(str(r.get("label") or "").lower(), 0.0)
        if lift:
            w *= (1.0 + lift)
            print(f"[Suggest] {r['label']} leans into today (+{lift})")
        weights.append(w)
    best = random.choices(eligible, weights=weights, k=1)[0]
    # The category comes along: it decides what kind of thing can be fetched
    # for this — a song, a recipe, or nothing at all.
    attrs = best.get("attributes")
    # WHEN she last had this, and at what hour.
    #
    # The picker handed the composer a label and nothing else, so "chole" —
    # which she ate two days ago — was offered as though it were a new idea.
    # The dates were already there: last_event on the cluster, and every day
    # in subject_mentions.
    #
    # It changes the offer rather than only the choice. Never mentioned is an
    # introduction; two days ago is "phir se chole?"; three weeks ago is
    # "bahut din se khichdi nahi banayi", which is a warmer thing and
    # impossible without the date.
    last_at, last_on, days_ago = None, None, None
    try:
        from datetime import date as _date   # datetime is imported at module level; re-importing it here shadowed it for the whole function and broke the recent-offers lookup above
        rows = (db.table("subject_mentions").select("happened_on")
                .eq("user_id", user_id).ilike("subject", f"%{best['label']}%")
                .order("happened_on", desc=True).limit(1).execute()).data or []
        if rows:
            last_on = str(rows[0]["happened_on"])[:10]
        # The hour comes from the cluster's last event — the day alone cannot
        # tell a breakfast from a late supper, and an offer at the wrong hour
        # is the thing that made a dish arrive at 8:41pm.
        if best.get("last_event"):
            last_at = str(best["last_event"])
            if not last_on:
                last_on = last_at[:10]
        if last_on:
            days_ago = (_date.today() - _date.fromisoformat(last_on)).days
    except Exception as e:
        print(f"[Suggest] last-seen read failed: {e}")

    return {"cluster_id": best["id"], "label": best["label"],
            "pillar": best.get("pillar"),
            "last_on": last_on,          # the day she last had it
            "last_at": last_at,          # and the hour, where known
            "days_ago": days_ago,
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

def _her_words_since(user_id: str, since_iso: str) -> int:
    """How many messages she has written since then, not counting the one
    being handled now (it is saved before this runs, so one is allowed)."""
    try:
        from supabase_store import get_client
        db = get_client()
        sess = [r["id"] for r in (db.table("sessions").select("id")
                .eq("user_id", user_id).gte("updated_at", since_iso)
                .limit(5).execute()).data or []]
        if not sess:
            return 0
        rows = (db.table("messages").select("timestamp")
                .in_("session_id", sess).eq("role", "user")
                .gt("timestamp", since_iso).limit(10).execute()).data or []
        return len(rows)
    except Exception as e:
        print(f"[Suggest] her-words read failed: {e}")
        return 99                    # unknown: fall back to the short rule


def pending_suggestion(user_id: str) -> Optional[dict]:
    """The open suggestion, if there is one and it is still hers to answer.

    Fresh (30 minutes), or older but her first word since (3 hours).
    """
    try:
        from supabase_store import get_client
        since = (datetime.now(timezone.utc)
                 - timedelta(minutes=FIRST_REPLY_MINUTES)).isoformat()
        rows = (get_client().table("suggestions")
                .select("id,cluster_id,label,intent,created_at")
                .eq("user_id", user_id).is_("reaction", "null")
                .gte("created_at", since)
                .order("created_at", desc=True).limit(1).execute()).data or []
        if not rows:
            return None
        r = rows[0]
        made = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
        if made.tzinfo is None:
            made = made.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - made).total_seconds() / 60
        if age <= PENDING_MINUTES:
            return r
        # Older: only if this is the first thing she has said since.
        return r if _her_words_since(user_id, made.isoformat()) <= 1 else None
    except Exception as e:
        print(f"[Suggest] pending read failed: {e}")
        return None


def _said_after(user_id: str, since_iso: str) -> str:
    """What the companion said after the offer, if anything — the latest
    line, which is what a reply most often answers."""
    try:
        from supabase_store import get_client
        db = get_client()
        made = datetime.fromisoformat(str(since_iso).replace("Z", "+00:00"))
        if made.tzinfo is None:
            made = made.replace(tzinfo=timezone.utc)
        # A minute's grace: the offer itself is saved as a message too.
        after = (made + timedelta(minutes=1)).isoformat()
        sess = [r["id"] for r in (db.table("sessions").select("id")
                .eq("user_id", user_id).gte("updated_at", after)
                .limit(5).execute()).data or []]
        if not sess:
            return ""
        rows = (db.table("messages").select("content,timestamp")
                .in_("session_id", sess).eq("role", "assistant")
                .gt("timestamp", after).order("timestamp", desc=True)
                .limit(1).execute()).data or []
        return str(rows[0].get("content") or "")[:300] if rows else ""
    except Exception as e:
        print(f"[Suggest] said-after read failed: {e}")
        return ""


def classify_reaction(offer_label: str, user_text: str,
                      said_since: str = "") -> Optional[str]:
    """
    Is this reply about the offer, and if so what kind of no?

    The distinction between "not now" and "not this" is the whole point. A
    keyword check cannot make it — "nahi, abhi mann nahi hai" and "nahi, mujhe
    woh pasand nahi" share their first word and mean opposite things.
    """
    # What came between. "Haan krdia phone" was credited to an offer of
    # Sukhsagar as a yes — it answered the next message, which asked about
    # her phone call. The offer log then said mornings work, and pushed more.
    later = ""
    if said_since:
        later = (f'\nAFTER the offer, the companion also said: "{said_since}"\n'
                 "A reply usually answers the LATEST thing said. If this "
                 "reply answers that later message rather than the offer, "
                 "it is unrelated to the offer.\n")
    prompt = f"""The companion offered: "{offer_label}"{later}
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
    # Twice if the first try fails. One failed call at 14:53 lost "Haan acha
    # gana hai yei" — asked again later, the same words came back "accepted"
    # — and a lost yes means nothing is learned from the one thing she
    # clearly liked that day.
    for attempt in (1, 2):
        try:
            import anthropic
            client = __import__("llm").client()
            resp = client.messages.create(
                model=__import__("llm").model("claude-haiku-4-5-20251001"), max_tokens=10,
                messages=[{"role": "user", "content": prompt}])
            answer = (resp.content[0].text or "").strip().lower().strip(".").split()[0:1]
            answer = answer[0] if answer else ""
            if answer in REACTION_WEIGHT or answer == "unrelated":
                print(f"[Suggest] {offer_label[:40]!r} + {user_text[:40]!r} -> {answer}")
                return answer
            print(f"[Suggest] unrecognised reaction {answer!r} (try {attempt})")
        except Exception as e:
            print(f"[Suggest] classify failed (try {attempt}): {e}")
    return None


def apply_reaction(user_id: str, suggestion: dict, reaction: str,
                   session_id: Optional[str] = None,
                   reply_text: str = "") -> bool:
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
        upd = {"reaction": reaction,
               "reacted_at": datetime.now(timezone.utc).isoformat()}
        if reply_text:
            # Her words, not only the label: "abhi puja karna hai, sham ko
            # dekhenge" says WHEN, which "declined_timing" does not.
            try:
                db.table("suggestions").update({**upd, "reply_text": reply_text[:300]}) \
                    .eq("id", suggestion["id"]).execute()
                upd = None
            except Exception:
                pass                      # column not there yet
        if upd:
            db.table("suggestions").update(upd).eq("id", suggestion["id"]).execute()

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

    reaction = classify_reaction(pending.get("label", ""), user_text,
                                 _said_after(user_id, pending.get("created_at")))
    if not reaction or reaction == "unrelated":
        # Leave it open — they may still answer. The expiry sweep will close it.
        return None

    apply_reaction(user_id, pending, reaction, session_id, reply_text=user_text)
    return reaction


def expire_stale(user_id: Optional[str] = None) -> int:
    """Close suggestions nobody answered. Silence is weak evidence, but a run of
    it says the suggestions are landing badly."""
    try:
        from supabase_store import get_client
        db = get_client()
        # Closed as no_response only once even a first reply would be too
        # late. Closing at 30 minutes is what lost "sham ko dekhenge": the
        # offer was already marked ignored when she answered it.
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(minutes=FIRST_REPLY_MINUTES)).isoformat()
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

# What makes weather worth a sentence. Not a temperature — a change, or
# something she would act on.
DROP_C = 4.0          # colder than yesterday. Her knee notices a fall.
RISE_C = 6.0          # warmer. Less interesting, but a jump is a jump.
COLD_C = 12.0         # cold in its own right, whatever yesterday was
HOT_C = 36.0

_WET = ("rain", "drizzle", "shower", "storm", "thunder", "snow")


def _weather_yesterday(user_id: str):
    """What it was the last time we looked. None on the first day."""
    from datetime import date, timedelta
    try:
        from supabase_store import get_client
        rows = (get_client().table("weather_log").select("temp_c,description")
                .eq("user_id", user_id)
                .lt("on_day", date.today().isoformat())
                .order("on_day", desc=True).limit(1).execute()).data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[Weather] history read failed: {e}")
        return None


def _remember_weather(user_id: str, temp, desc: str):
    """One row a day. Cheap, and it is the only way to know a change."""
    from datetime import date
    try:
        from supabase_store import get_client
        get_client().table("weather_log").upsert({
            "user_id": user_id, "on_day": date.today().isoformat(),
            "temp_c": temp, "description": desc,
        }, on_conflict="user_id,on_day").execute()
    except Exception as e:
        print(f"[Weather] write failed: {e}")


def weather_worth_saying(user_id: str, w: dict) -> str:
    """One line, or "" — and "" is the common answer.

    Returns a fact, never a phrasing. "Mausam theek hai" used to be in this
    block and it is an opinion; given one, the composer says it back.
    """
    if not w:
        return ""

    temp = w.get("temp_c")
    desc = str(w.get("description") or "").lower()
    try:
        temp = float(temp) if temp is not None else None
    except Exception:
        temp = None

    was = _weather_yesterday(user_id)
    if temp is not None:
        _remember_weather(user_id, temp, desc)

    # Rain first. She walks in the evening, and an umbrella is a thing she can
    # act on — which is the whole test.
    if any(word in desc for word in _WET):
        t = f", {round(temp)}°C" if temp is not None else ""
        return f"It is raining where they are{t}."

    if temp is None:
        return ""

    if temp <= COLD_C:
        return f"It is cold where they are, {round(temp)}°C."
    if temp >= HOT_C:
        return f"It is very hot where they are, {round(temp)}°C."

    # And a change from yesterday. The number alone is not news; the
    # difference is what anyone would remark on.
    if was and was.get("temp_c") is not None:
        try:
            delta = temp - float(was["temp_c"])
        except Exception:
            return ""
        if delta <= -DROP_C:
            return (f"It is {abs(round(delta))}° colder than yesterday, "
                    f"{round(temp)}°C.")
        if delta >= RISE_C:
            return (f"It is {round(delta)}° warmer than yesterday, "
                    f"{round(temp)}°C.")

    # A pleasant day is not news, and passing it guarantees it gets used.
    return ""


def recent_window(user_id: str, hours: int = 6) -> str:
    """What she has been saying today, for the offer to take its tone from.

    Boundaries read the conversation; recommendations never did. So an offer
    at three in the afternoon knew nothing about lunch — which is how "garma
    garm chole" arrived two days after she had eaten chole.

    Returns her lines only. What the companion said is not the signal.
    """
    from datetime import datetime, timezone, timedelta
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        from supabase_store import get_client
        db = get_client()
        sess = (db.table("sessions").select("id")
                .eq("user_id", user_id).gte("updated_at", since)
                .order("updated_at", desc=True).limit(3).execute()).data or []
        said = []
        for s in sess:
            said += [str(m.get("content") or "")[:160] for m in
                     (db.table("messages").select("content,timestamp")
                      .eq("session_id", s["id"]).eq("role", "user")
                      .gte("timestamp", since).order("timestamp")
                      .limit(20).execute()).data or []]
    except Exception as e:
        print(f"[Suggest] window read failed: {e}")
        return ""

    said = [s for s in said if len(s.strip()) > 1][-8:]
    if not said:
        return ""

    return ("\n\nWhat she has said today:\n"
            + "\n".join("- " + s for s in said)
            + "\nLet this shape WHAT you offer and HOW you say it — a quiet "
              "day takes a gentler offer than a talkative one, and something "
              "she has already done today is not an offer. Do not refer back "
              "to it; she knows what she said.")


def moment_facts(user_id: str, moment: dict = None) -> str:
    """The world as it is, for whoever is writing the next message.

    Shared by offers and boundaries on purpose: an offer that knows it is
    raining and a follow-up that does not would contradict each other an hour
    apart.
    """
    m = moment or _moment(user_id)
    lines = []

    # Only when it would change what she does. Three messages one morning
    # were all about the weather, and the breakfast boundary never mentioned
    # breakfast — the weather was the only concrete thing in this block, and
    # always is.
    _w = weather_worth_saying(user_id, m.get("weather") or {})
    if _w:
        lines.append(_w)
        # The route writes this in their language and it is better than
        # anything assembled from the raw fields.
        if False:   # the raw weather dict is gone — see weather_worth_saying
            lines.append(str(w["advice"]))

    v = m.get("valence")
    flags = m.get("flags") or []
    # Deliberately NOT told she is low. The instruction said do not
    # mention it, do not ask whether she is alright, do not say she
    # seems worried — and the composer wrote "aap thodi pareshaan lag
    # rahi hain, sab theek hai na?" twice in a row.
    #
    # The same lesson as her knee: a negative instruction teaches the
    # subject. What the composer does not know, it cannot hand back to
    # her as a question.
    #
    # It still shapes the choice — pick_suggestion reads the same
    # valence and leans familiar over novel on a hard afternoon.
    if v is not None and v >= 0.3:
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
        # Where, and what it means. "They are away from home at the moment"
        # became "kyunki aap abhi bahar hain" — you are out right now — to a
        # woman sitting in her son's flat in Bengaluru, where she is staying
        # for weeks, away from her own home in Surat. Away from home is a
        # place she lives for now, not a trip out of the door.
        where, home = "", ""
        try:
            from memory.declared import get_declared
            d = get_declared(user_id)
            where, home = (d.place.current or ""), (d.place.home or "")
        except Exception:
            pass
        lines.append(
            (f"They are staying in {where}" if where else "They are staying away")
            + (f", away from their own home in {home}" if home else ", away from their own home")
            + ". That is where they are living for now, indoors and settled — "
              "not out of the house. Never say they are out or outside.")

    if not lines:
        return ""
    return ("\n\nWHAT IS TRUE RIGHT NOW — facts, not instructions about tone:\n"
            + "\n".join(f"- {l}" for l in lines))

"""
SCHEDULE ENGINE
Determines what Nancy should say and when, based on:
  - Time of day
  - User profile (health, interests, family)
  - User memory (recent events, trends)
  - Last session data (what was discussed)

Schedule slots:
  morning    06:00 - 10:00  medicine + breakfast + warm opener
  midday     10:00 - 14:00  activity + interest check
  afternoon  14:00 - 17:00  rest check + conversation
  evening    17:00 - 20:00  interest-based (cricket/music/news)
  night      20:00 - 23:00  medicine + emotional check-in + good night
  late_night 23:00 - 06:00  (no proactive calls, emergency only)

Priority stack per slot:
  1. CRITICAL  — health emergency / stress crisis
  2. HIGH      — health follow-up / emotional support
  3. MEDIUM    — routine health nudge / interest chat
  4. LOW       — general warm check-in
"""

import os
from datetime import datetime, timezone
from typing import Optional


# ── Time slot detection ────────────────────────────────────────────────────────

def get_time_slot(hour: int = None, user_id: str = "") -> str:
    # Server time is UTC in production. Using it meant 13:31 IST resolved to
    # hour=8 and slot "morning" — a "Good morning" greeting sent at half past
    # one in the afternoon, every proactive message shifted 5.5h early, and the
    # late_night suppression window landing on the wrong half of the day.
    if hour is None:
        try:
            from memory.time_context import time_context
            hour = time_context(user_id)["hour"]
        except Exception as e:
            print(f"[Schedule] time_context failed, falling back to server "
                  f"time (WRONG SLOT LIKELY): {e}")
            hour = datetime.now().hour
    if   6  <= hour < 10: return "morning"
    elif 10 <= hour < 14: return "midday"
    elif 14 <= hour < 17: return "afternoon"
    elif 17 <= hour < 20: return "evening"
    elif 20 <= hour < 23: return "night"
    else:                  return "late_night"


def get_greeting(slot: str, name: str = "") -> str:
    greet = name and f"{name}," or ""
    greetings = {
        "morning":   f"Subah ki chai ho gayi {greet}",
        "midday":    f"Kya chal raha hai {greet}",
        "afternoon": f"Dopahar mein kaisa lag raha hai {greet}",
        "evening":   f"Shaam ho gayi {greet}",
        "night":     f"Raat ho gayi {greet}",
        "late_night": f"Sab theek hai {greet}",
    }
    return greetings.get(slot, f"Hello {greet}")


# ── Priority detection ─────────────────────────────────────────────────────────

def detect_priority(memory: dict, profile: dict) -> tuple:
    """
    Returns (priority_level, reason) based on memory + profile.
    priority_level: 'critical' | 'high' | 'medium' | 'low'
    """
    if not memory:
        return "low", "no_memory"

    trends    = memory.get("pillar_trend", {})
    alerts    = trends.get("alerts", []) if isinstance(trends, dict) else []
    fp        = memory.get("behavioural_fingerprint", {})
    health    = profile.get("health", {}) if profile else {}
    conditions = health.get("conditions", [])

    # CRITICAL — emergency signals
    if any("distress" in a.lower() or "emergency" in a.lower() for a in alerts):
        return "critical", "emergency_detected"

    # HIGH — stress/sadness trending + health concern
    pillar_trends = trends.get("pillar_trends", {}) if isinstance(trends, dict) else {}
    stress_rising  = pillar_trends.get("STRESS")  == "rising"
    sadness_rising = pillar_trends.get("SADNESS") == "rising"
    health_rising  = pillar_trends.get("HEALTH_WELLNESS") == "rising"

    if (stress_rising or sadness_rising) and conditions:
        return "high", "stress_plus_health"
    if stress_rising or sadness_rising:
        return "high", "emotional_distress"
    if health_rising and conditions:
        return "high", "health_concern"

    # MEDIUM — routine health or emotional
    if conditions:
        return "medium", "health_routine"
    if any(a for a in alerts):
        return "medium", "alert_present"

    return "low", "general_checkin"


# ── Script generators ──────────────────────────────────────────────────────────

def _health_followup(profile: dict, memory: dict, slot: str) -> str:
    health     = profile.get("health", {})
    conditions = health.get("conditions", [])
    name       = profile.get("name", "")
    greeting   = get_greeting(slot, name)

    parts = [greeting]

    if slot == "morning":
        if conditions:
            cond_str = " aur ".join(conditions[:2])
            parts.append(f"Aaj {cond_str} ka dhyan rakhna.")
        meds = health.get("medications", [])
        if meds:
            parts.append("Dawai li subah ki?")
        else:
            parts.append("Aaj kaisa feel ho raha hai?")

    elif slot == "evening":
        if conditions:
            parts.append(f"Din bhar kaisa raha? {conditions[0]} mein koi improvement?")

    elif slot == "night":
        if conditions:
            parts.append("Raat ki dawai li? Aur aaj ka din kaisa gaya?")

    return " ".join(parts)


def _emotional_support(profile: dict, memory: dict, slot: str) -> str:
    name     = profile.get("name", "")
    family   = profile.get("family", {})
    children = family.get("children", [])
    greeting = get_greeting(slot, name)

    summary = memory.get("summary", "")
    parts   = [greeting]

    parts.append("Aaj kaisa feel kar rahe ho?")

    if children:
        child = children[0] if isinstance(children[0], str) else "beta/beti"
        parts.append(f"{child} ka call aaya aaj?")
    else:
        parts.append("Koi baat karni ho toh main yahan hoon.")

    return " ".join(parts)


def _interest_chat(profile: dict, memory: dict, slot: str) -> str:
    name      = profile.get("name", "")
    interests = profile.get("interests", {})
    greeting  = get_greeting(slot, name)
    parts     = [greeting]

    sports        = interests.get("sports", [])
    music         = interests.get("music", [])
    entertainment = interests.get("entertainment", [])

    # Use interests directly from profile — no keyword matching
    if sports:
        sport_str = sports[0] if sports else "sports"
        parts.append(f"Aaj ka {sport_str} dekha?")
        parts.append("Kaisa laga?")
    elif music:
        music_str = music[0] if music else "purane gaane"
        parts.append(f"{music_str} sun rahe the aaj?")
    elif entertainment:
        ent_str = entertainment[0] if entertainment else "kuch"
        parts.append(f"{ent_str} dekh rahe ho aajkal?")
    else:
        parts.append("Aaj din mein kya kiya? Kuch interesting?")

    return " ".join(parts)


def _medicine_reminder(user_id: str, profile: dict, slot: str, hour: int = None) -> str:
    """
    Build a medication reminder from the REAL care_schedule — actual drug,
    time, dose — instead of a generic "subah ki dawai" guess. Falls back to
    the old generic string if no schedule exists.
    """
    name     = profile.get("name", "")
    name_str = f"{name}," if name else ""

    try:
        from memory.care_reader import get_due_schedule_items
        due = get_due_schedule_items(user_id, hour=hour)
    except Exception as e:
        print(f"[MedReminder] reader failed: {e}")
        due = []

    meds_due = [d for d in due if d.get("type") == "medication"]
    if meds_due:
        lines = []
        for m in meds_due:
            label = m.get("label", "dawai")
            dose  = m.get("dose")
            notes = m.get("notes")
            overdue = m.get("delta_min", 0) < -10
            piece = label
            if dose:
                piece += f" ({dose})"
            piece += " lena reh toh nahi gaya?" if overdue else " le lena"
            if notes:
                piece += f" — {notes}"
            lines.append(piece)
        return f"{name_str} ek reminder: {'; '.join(lines)}."

    # Fallback: no schedule entered
    health = profile.get("health", {})
    if not health.get("medications", []):
        return ""
    if slot == "morning":
        return f"Ek reminder {name_str} subah ki dawai leni hai!"
    elif slot == "night":
        return f"{name_str} raat ki dawai li kya?"
    return ""


def _general_checkin(profile: dict, memory: dict, slot: str) -> str:
    name     = profile.get("name", "")
    greeting = get_greeting(slot, name)
    summary  = memory.get("summary", "") if memory else ""

    parts = [greeting]

    if slot == "morning":
        parts.append("Aaj ka din achha jayega!")
        parts.append("Chai ke saath kya plan hai?")
    elif slot == "evening":
        parts.append("Shaam mein kya chal raha hai?")
        parts.append("Kuch batao aaj ka haal!")
    elif slot == "night":
        parts.append("Aaj ka din kaisa raha?")
        parts.append("Neend achhi aaye, kal baat karte hain.")
    else:
        parts.append("Kya chal raha hai? Baat karo mujhse!")

    return " ".join(parts)


# ── Main script generator ──────────────────────────────────────────────────────

def generate_proactive_script(
    user_id: str,
    hour: int = None,
    force_slot: str = None,
    action: str = None,
    hints: str = "",
    # What the decision chose. Without it this re-derived the dose from the
    # clock and found a different answer — her 07:00 thyronorm and 08:00
    # amlodipine in one message, an hour early.
    #
    # Whoever decides something passes it on. Nobody looks it up twice.
    detail: str = "",
) -> dict:
    """
    Generate a proactive message for Nancy to open with.

    Returns:
      {
        "script":    "Nancy's opening message",
        "slot":      "morning/evening/etc",
        "priority":  "critical/high/medium/low",
        "reason":    "why this script was chosen",
        "should_call": True/False  (whether to make a voice call)
      }
    """
    from memory.profile_store import get_user_profile
    from memory.user_memory_store import get_user_memory

    profile  = get_user_profile(user_id) or {}
    memory   = get_user_memory(user_id) or {}
    slot     = force_slot or get_time_slot(hour, user_id)
    priority, reason = detect_priority(memory, profile)

    # Don't proactively contact during late night unless critical
    if slot == "late_night" and priority != "critical":
        return {
            "script":      "",
            "slot":        slot,
            "priority":    priority,
            "reason":      "late_night_suppressed",
            "should_call": False,
        }

    # Generate script based on priority
    if priority == "critical":
        script     = _emotional_support(profile, memory, slot)
        should_call = True

    elif priority == "high":
        if reason == "emotional_distress":
            script = _emotional_support(profile, memory, slot)
        else:
            script = _health_followup(profile, memory, slot)
        should_call = True

    elif priority == "medium":
        if slot in ("morning", "night"):
            script = _health_followup(profile, memory, slot)
        else:
            script = _interest_chat(profile, memory, slot)
        should_call = False

    else:  # low
        if slot in ("morning", "night"):
            reminder = _medicine_reminder(user_id, profile, slot, hour)
            general  = _general_checkin(profile, memory, slot)
            script   = f"{reminder} {general}".strip() if reminder else general
        else:
            script = _interest_chat(profile, memory, slot)
        should_call = False

    # The templates above are now the fallback. Try the composer first: it has
    # the persona, the memory and the care schedule, so it can say something
    # only this person would hear.
    # One composer, in context_builder — this used to be a second
    # implementation here, and two copies of the same thing is how the
    # reminder-firing loops drifted apart.
    from memory.context_builder import compose
    # The caller knows what it decided; a medication reminder should not be
    # worded as a general check-in. Without this the 20:00 Amlodipine nudge
    # came out as "how are your knees feeling tonight?" and never named the
    # drug.
    intent = {
        "MEDICATION_REMINDER": "medication",
        "GREETING":            "greeting",
        "BOUNDARY":            "boundary",
        "SAFETY_INFO":         "safety",
        "EXPLORE_OFFER":       "recommendation",
        "RECOMMENDATION":      "recommendation",
    }.get(action or "", "check_in")
    # Name the dose that is actually due. Without this the medication intent
    # has no drug data at all — it saw neither the routine nor a hint — and
    # invented one: "aap ka Digene ka dose abhi le lena chahiye" for a woman
    # who takes Amlodipine.
    hints = hints or ""
    if intent == "medication":
        try:
            from memory.care_reader import get_due_schedule_items
            # The decision already chose ONE dose — proactive_engine sorts the
            # due medications and takes the first, deliberately, so that two
            # tablets an hour apart are two reminders an hour apart.
            #
            # Looking them up again here by hour threw that away: a 45-minute
            # window at 07:16 reached 08:01, so her 07:00 thyronorm and her
            # 08:00 amlodipine both went into one message and she was told to
            # take her BP tablet three quarters of an hour early.
            #
            # Honour what was decided. The lookup is only for when nothing
            # was passed.
            if detail:
                labels = [detail]
            else:
                due = get_due_schedule_items(user_id, hour=hour) or []
                labels = [d.get("label") for d in due
                          if d.get("label") and d.get("type") == "medication"]
            if labels:
                hints = ("The dose due right now is: " + ", ".join(labels) +
                         ". Name it exactly. Do not name any other medicine.")
        except Exception as e:
            print(f"[Schedule] due-item hint failed: {e}")

    # For a recommendation, choose the thing FIRST rather than letting the
    # composer reach for whatever reads well. Two reasons: it skips anything
    # offered recently or already declined, and it means we know what was
    # offered when the reply comes back.
    if intent == "greeting":
        from memory.greeting import task_for
        hints = (hints + "\n" if hints else "") + task_for(user_id)

    # What last night left. On a greeting or the first boundary of the day —
    # she said she had a cold on Tuesday and nothing asked after it on
    # Wednesday, which is the whole reason this exists.
    # The first message of the day, not every message. hint() marks it
    # raised, so a greeting and a boundary in the same morning would both
    # consume it and only the first would ask.
    if intent in ("greeting", "boundary") and (hour or 0) < 11:
        try:
            from memory.carry import hint as _carry_hint
            hints = (hints or "") + _carry_hint(user_id)
        except Exception as _ce:
            print(f"[Carry] morning hint failed: {_ce}")

    if intent == "boundary":
        from memory.day import boundary as day_boundary, boundary_hint
        b = day_boundary(user_id)
        if b:
            hints = (hints + "\n" if hints else "") + boundary_hint(user_id, b)

    # What is true right now, for whoever is writing. An offer before her walk
    # could not say "chhata le jaana" because the weather was fetched on every
    # pick and thrown away.
    if intent in ("recommendation", "boundary", "greeting"):
        try:
            from memory.suggestions import moment_facts
            mf = moment_facts(user_id)
            if mf:
                hints = (hints or "") + mf

            # And where she is, if she has just got there. away.py was built
            # for this and nothing ever called it — so a woman two days into
            # a strange city was told nothing about it, while her son got an
            # email saying local emergency resources had been surfaced.
            from memory.away import hint as away_hint
            ah = away_hint(user_id)
            if ah:
                hints = (hints or "") + "\n\n" + ah

            # And what day it is in the country she lives in. Carried by the
            # breakfast message rather than pushed separately — she is up,
            # her puja is done, and there is a natural pause. A festival wish
            # at nine at night is a day too late.
            from memory.festivals import hint_for as festival_hint

            from memory.festivals import hint_for as festival_hint

            # Once a day, in the first message. Not in every one.
            #
            # Four of five offers opened with "Happy Gandhi Jayanti", and so
            # did every real message she got that day — breakfast, lunch and
            # the evening. A festival is a fact that is true all day, always
            # in the prompt, and always safe, so the composer opens with it,
            # the way it did with the weather.
            #
            # The comment two sections up already said this: carried by the
            # breakfast message, because a wish at nine at night is a day too
            # late. It just never checked whether one had gone already.
            from datetime import date as _fd
            from supabase_store import get_client as _fgc
            _already = False
            try:
                _r = (_fgc().table("user_profile").select("festival_wished_on")
                      .eq("user_id", user_id).limit(1).execute()).data or []
                _already = bool(_r and str(_r[0].get("festival_wished_on") or "")
                                == _fd.today().isoformat())
            except Exception:
                pass

            fh = "" if _already else festival_hint(user_id)
            if fh:
                hints = (hints or "") + fh
                try:
                    _fgc().table("user_profile").update(
                        {"festival_wished_on": _fd.today().isoformat()}
                    ).eq("user_id", user_id).execute()
                except Exception as _fe:
                    print(f"[Schedule] festival stamp failed: {_fe}")
        except Exception as e:
            print(f"[Schedule] moment facts failed: {e}")

    # What she does on THIS day of the week, before anything is drawn.
    #
    # Promotion counts distinct days, so chicken on four Sundays and khichdi
    # on four scattered days both come back as "4 days" — and only the first
    # lets you say, on a Sunday morning, "aaj Sunday hai, chicken banayengi?"
    #
    # A reason beats a probability, so a rhythm due today outranks the
    # weighted draw. The day goes in the words: naming it shows she has been
    # noticed rather than merely predicted.
    _rhythm_fired = False
    try:
        from memory.rhythms import due_today, hint as rhythm_hint
        for _r in due_today(user_id):
            _rhythm_fired = True
            hints = (hints or "") + rhythm_hint(_r)
            print(f"[Rhythm] {user_id}: {_r['subject']} on {_r['weekday']}s "
                  f"({_r['on_that_day']}/{_r['of']})")
            break
    except Exception as _re:
        print(f"[Rhythm] check failed: {_re}")

    # An offer should know what kind of day she is having. Boundaries read
    # the conversation and recommendations never did.
    if intent == "recommendation":
        try:
            from memory.suggestions import recent_window
            hints = (hints or "") + recent_window(user_id)
        except Exception as _we:
            print(f"[Schedule] window failed: {_we}")

    # If a message is going to name something she likes, name the one that
    # was CHOSEN — not whichever the model happens to know best.
    #
    # Kishore Kumar appeared in three of four messages one day and twice more
    # the next, none of them through the offer path. He is her strongest
    # interest, so he is in the thread, the summary and the cluster block,
    # and a composer told it may mention an interest reaches for him every
    # time. Shuffling the list changed nothing, because the list is not where
    # he comes from.
    #
    # So: pick one, expand it a step, and say that is the only one.
    # Occasionally, not every time.
    #
    # Three of four boundaries one day carried a song — "Pal Bhar Ke Liye" at
    # breakfast, "Chaudhvin Ka Chand" at lunch, a dosa in the evening. Each
    # was a fair suggestion and together they made every message an offer,
    # when a boundary is meant to ask about her day.
    #
    # Seeded by the day and the slot, so it is stable within a conversation:
    # the same boundary regenerated does not change its mind.
    _may_offer = False
    # Never on a medication reminder. Its own task says name the dose and
    # nothing else, and "baad mein garam-garam dosa ka maza lenge" went out
    # attached to her thyroid tablet.
    if intent not in ("recommendation", "medication") and not _rhythm_fired:
        import hashlib as _h
        from datetime import date as _d
        _seed = f"{user_id}:{_d.today().isoformat()}:{slot or ''}"
        # roughly one boundary in three
        _may_offer = int(_h.md5(_seed.encode()).hexdigest(), 16) % 3 == 0

    if _may_offer:
        try:
            from memory.suggestions import pick_suggestion as _ps
            from memory.artefacts import what_to_offer as _wto
            _p = _ps(user_id)
            if _p:
                _o = _wto(user_id, _p)
                _thing = _o.get("subject") or _p["label"]
                _because = _o.get("with_")
                hints = (hints or "") + (
                    f"\n\nIf you mention something she enjoys, mention "
                    f"{_thing}"
                    + ""
                    + ". That one, and nothing else. Do not name any other "
                      "artist, film or dish, whatever else you know she "
                      "likes — and do NOT credit it to anyone else. "
                      "'Kishore Kumar ka Chaudhvin Ka Chand' is Rafi's song "
                      "with the wrong singer's name on it, which came from "
                      "telling the composer WHY the song was chosen. One mention, at "
                      "most, and only if the message has room for it.")
                print(f"[Offer] {user_id}: boundary may mention {_thing}")
        except Exception as _oe:
            print(f"[Offer] boundary pick failed: {_oe}")

    picked = None
    # A rhythm is a reason, and a reason beats a probability. If she has a
    # Sunday and it is Sunday, that IS the offer — drawing a second one on top
    # gives the composer two things to choose between and it picks whichever
    # reads better, which is not a decision anyone made.
    if intent == "recommendation" and not _rhythm_fired:
        try:
            from memory.suggestions import pick_suggestion
            picked = pick_suggestion(user_id)
            if picked:
                # Fetch something she can actually act on. Offering "Kishore
                # Kumar" is a conversation about an interest; offering a song
                # she can tap is an offer. Returns None often — no key, no
                # result, or a category that should never fetch — and the hint
                # falls back to naming the subject, which is what this did
                # before.
                # How long since she last had it. The same subject is three
                # different offers depending on when — and the picker was
                # handing over a label with no date, so chole she ate two days
                # ago arrived as a fresh idea.
                _d = picked.get("days_ago")
                if _d is not None:
                    if _d <= 3:
                        hints = ((hints + "\n") if hints else "") + (
                            f"They had {picked['label']} {'today' if _d == 0 else f'{_d} day(s) ago'}. "
                            f"So this is picking something up, not introducing "
                            f"it — 'phir se' rather than 'try kijiye'.")
                    elif _d >= 14:
                        hints = ((hints + "\n") if hints else "") + (
                            f"It has been {_d} days since {picked['label']} "
                            f"came up. That gap is itself the reason to "
                            f"mention it — 'bahut din se' — and it should not "
                            f"sound like the first time.")

                # One step out, before falling back to a variation on the
                # same subject. The adjacency list was being generated and
                # thrown away: Kishore Kumar expanded to Lata, Rafi and
                # R.D. Burman, and the offer went out as another Kishore
                # jukebox because nothing read it.
                try:
                    from memory.artefacts import offer_hint
                    _oh = offer_hint(user_id, picked)
                    if _oh:
                        hints = (hints or "") + _oh
                except Exception as _oe:
                    print(f"[Offer] adjacency failed: {_oe}")

                from memory.artefacts import (fetch_artefact, as_hint,
                                               fetch_along_axis, axis_hint)
                cat = ((picked.get("attributes") or {}).get("category")
                       if isinstance(picked.get("attributes"), dict) else None)

                # Fetch for the thing being OFFERED, not the thing drawn.
                #
                # The hint said "offer R.D. Burman because of Kishore Kumar"
                # and then a Kishore Kumar jukebox was attached, because this
                # used picked["label"] regardless. The composer took the link,
                # reasonably, and the offer came out as Kishore again.
                from memory.artefacts import what_to_offer
                _o = what_to_offer(user_id, picked)
                _subject = _o.get("subject") or picked["label"]

                art = fetch_artefact(user_id, cat or "", _subject)
                if not art:
                    # Nothing for the adjacent thing — fall back to a step
                    # along an axis from the original, which is what this did
                    # before adjacency existed.
                    art = fetch_along_axis(user_id, picked)
                    if art:
                        hints = (hints + "\n" if hints else "") + axis_hint(art)
                        _subject = picked["label"]
                if art and _subject != picked["label"]:
                    hints = (hints + "\n" if hints else "") + as_hint(art, _subject)
                elif art and _subject == picked["label"]:
                    hints = (hints + "\n" if hints else "") + as_hint(art, _subject)
                picked["artefact"] = art
                picked["offering"] = _subject
        except Exception as e:
            print(f"[Schedule] pick_suggestion failed: {e}")

    composed = compose(user_id, intent=intent, slot=slot,
                       priority=priority, hints=hints)

    if composed and picked:
        try:
            from memory.suggestions import record_suggestion
            record_suggestion(user_id, picked.get("cluster_id"),
                              picked["label"], intent="recommendation")
        except Exception as e:
            print(f"[Schedule] record_suggestion failed: {e}")
    if composed:
        script = composed
    elif action in ("BOUNDARY", "RECOMMENDATION", "GREETING"):
        # When composing fails, send nothing rather than a template.
        #
        # Credits ran out on 21 September and three of four boundaries went
        # out as templates: "Aaj ka cricket dekha?" twice — once after she had
        # said she does not watch cricket — and "Raat ki dawai li?" at dinner,
        # though boundaries are never meant to mention medicine. The templates
        # read a profile filled in from a form weeks ago; they cannot know
        # anything she has said since.
        #
        # A missed boundary costs nothing. A wrong one teaches her the
        # companion is not listening.
        print(f"[Schedule] compose failed for {action} — sending nothing "
              f"rather than a template")
        script = ""
    elif action == "CHECK_IN":
        # The exception. Hours of silence during waking time is a welfare
        # question, and that should still arrive even when composing fails —
        # but plainly, claiming nothing about her day.
        name = (profile or {}).get("name") or ""
        script = f"{name} ji, sab theek hai? Bas yaad aayi aapki." if name \
                 else "Sab theek hai? Bas yaad aayi aapki."

    if not script:
        print(f"[Schedule] EMPTY script for {user_id} action={action} "
              f"slot={slot} priority={priority} reason={reason}")
    return {
        "script":      script,
        "slot":        slot,
        "priority":    priority,
        "reason":      reason,
        "should_call": should_call,
    }


# ── Should Nancy speak first? ──────────────────────────────────────────────────

def should_nancy_open(
    user_id: str,
    last_seen_hours: float,
    opened_app: bool = True,
) -> bool:
    """
    Decide if Nancy should speak first when user opens the app.

    Rules:
    - User hasn't been seen in 4+ hours → yes
    - It's a new day slot since last session → yes
    - High priority detected → always yes
    - Otherwise → no, wait for user
    """
    from memory.profile_store import get_user_profile
    from memory.user_memory_store import get_user_memory

    if not opened_app:
        return False

    # Always open if user hasn't been seen in 4+ hours
    if last_seen_hours >= 4:
        return True

    # Check priority
    profile  = get_user_profile(user_id) or {}
    memory   = get_user_memory(user_id) or {}
    priority, _ = detect_priority(memory, profile)

    if priority in ("critical", "high"):
        return True

    return False
def _care_schedule_context(user_id: str, slot: str) -> str:
    """What the user's day actually looks like around now.

    care_schedule holds their real routine — meals, medication times, morning
    puja, evening walk. The templates ignored it entirely and asked everyone
    "Aaj ka cricket dekha?" regardless of whether they follow cricket.
    """
    try:
        from supabase_store import get_client
        rows = (get_client().table("care_schedule").select("*")
                .eq("user_id", user_id).eq("active", True)
                .order("time_of_day").execute()).data or []
    except Exception:
        return ""
    if not rows:
        return ""

    lines = []
    for r in rows:
        t = (r.get("time_of_day") or "")[:5]
        label = r.get("label") or r.get("name") or r.get("type") or ""
        if t and label:
            lines.append(f"  {t} — {label} ({r.get('type')})")
    return "Their daily routine:\n" + "\n".join(lines) if lines else ""


def _compose_script(user_id: str, slot: str, priority: str, reason: str,
                    profile: dict, memory: dict) -> str:
    """
    Write the opening line in the companion's own voice.

    Replaces the hand-built templates, which had four problems visible in one
    sample: they said "Aaj Knee pain aur Chronic knee pain ka dhyan rakhna"
    because the condition list had near-duplicates; they asked everyone about
    cricket regardless of interest; they produced identical text for different
    people; and they ignored the persona entirely, so a companion styled as the
    user's son spoke exactly like the default one.

    Falls back to the caller's template on any failure — a proactive message
    that errors should degrade to something generic, not to silence.
    """
    import os

    try:
        from routes.persona import get_persona_prompt
        persona = get_persona_prompt(user_id)
    except Exception:
        persona = "You are Nancy, a warm companion."

    try:
        from memory.user_memory_store import build_memory_prompt
        recall = build_memory_prompt(user_id) or ""
    except Exception:
        recall = ""

    routine = _care_schedule_context(user_id, slot)
    name = profile.get("name") or ""

    slot_note = {
        "morning":    "It is morning — they are starting their day.",
        "midday":     "It is the middle of the day.",
        "afternoon":  "It is afternoon.",
        "evening":    "It is evening.",
        "night":      "It is night — they will be winding down.",
        "late_night": "It is very late.",
    }.get(slot, "")

    urgency = {
        "critical": "They seemed genuinely distressed recently. Lead with warmth "
                    "and ask how they are — nothing else matters right now.",
        "high":     "Something has been worrying them. Acknowledge it gently.",
        "medium":   "Nothing is wrong. This is an ordinary, affectionate check-in.",
        "low":      "Nothing is wrong. Keep it light and short.",
    }.get(priority, "")

    prompt = f"""{persona}

You are starting the conversation — they have not said anything yet. Write your
opening line.

{slot_note}
{urgency}

{routine}

{recall}

RULES:
- One or two sentences. This is a greeting, not a speech.
- Say something only THIS person would hear. Their routine, what they told you
  before, what they like. Never a generic question about cricket or the weather
  unless you know they care about it.
- If something in their routine is happening around now, that is usually the
  most natural thing to mention.
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
- Use their name{f" ({name})" if name else ""} naturally, not in every sentence.
- Match how they speak. If they use Hinglish, use Hinglish.
- Do not invent events, appointments, or things they did not tell you. If their
  routine above does not mention coffee, do not ask about coffee. Everything you
  reference must appear in the routine or the memory above, verbatim or close.
- If you have little to go on, a short warm greeting is the right answer. Say
  "Namaste, kaise ho aap?" and nothing more.
- NEVER address the operator, ask for more context, or explain what you do or do
  not know. You are speaking to the person, not about them. There is no one else
  to ask. Output that begins "I don't have" or asks for information about them is
  always wrong.

Write only the message itself. No preamble, no quotation marks."""

    try:
        import anthropic
        client = __import__("llm").client()
        resp = client.messages.create(
            model=__import__("llm").model("claude-haiku-4-5-20251001"),
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip().strip('"')

        # The model sometimes breaks character when the profile is thin —
        # "I don't have any information about Sim's routine... could you share
        # a bit about them?" — which would go to an elderly user as a push
        # notification. Reject it and let the caller fall back to the template.
        low = text.lower()
        _META = (
            "i don't have", "i do not have", "i don't know", "could you share",
            "could you tell me", "to write a", "let me know", "as an ai",
            "i'd need", "i would need", "no information", "not enough context",
            "based on the information provided", "here's a", "here is a",
        )
        if any(m in low for m in _META):
            print(f"[Schedule] composer broke character for {user_id}, "
                  f"falling back: {text[:80]}")
            return ""

        return text if text else ""
    except Exception as e:
        print(f"[Schedule] compose failed for {user_id}: {e}")
        return ""

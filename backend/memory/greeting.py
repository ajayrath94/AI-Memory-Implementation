"""
GREETING — the morning message.

Everything built so far needs material: enrichment, axes, probes, offers. It
works well in month three and poorly on day two, and the first fortnight is
exactly when someone decides whether this is worth having. A greeting needs
nothing. She has a morning, and that is enough.

IT GIVES, IT DOES NOT ASK
A check-in asks how she is because she has been quiet. A greeting has no reason
to ask — it opens the day and leaves. That difference is the whole point: one
is a companion checking on her, the other is a companion being there.

THREE REGISTERS, CHOSEN IN CODE
Not left to the model, which reading a history of aches would pick sympathy
every time.

    good      the last conversations went well — match her energy
    dull      they did not — cheerful, and lifting rather than consoling
    quiet     nothing recent at all — gentle, nothing demanded

CHEERFUL IS NOT A CLAIM
The failure mode for the middle register is "aaj acha din hoga!" — which is
what a poster says. To someone who mentioned last night that her knee hurts,
brightness without substance reads as not having been heard.

So cheerfulness is carried by what is OFFERED rather than asserted: the sun is
out, her puja is at half six, she said she was planting something. Lift by
giving her something real, never by insisting the day will be good.

NEVER THE DIFFICULTY
A greeting that opens on yesterday's pain makes her difficulty the subject
every morning, and turns a companion into a health monitor. The tone layer
supplies the situation; this says nothing about it.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict

# Below this the recent conversations were heavy.
DULL_BELOW = -0.15
# And above it they went well.
GOOD_ABOVE = 0.25

# Longer than this without a word and the register goes gentle, whatever the
# valence of conversations that are no longer recent.
QUIET_AFTER_HOURS = 36


def register(user_id: str) -> str:
    """good | dull | quiet — decided here rather than by the model."""
    try:
        from memory.time_context import time_context
        mins = time_context(user_id).get("minutes_since_last")
        if mins is not None and mins > QUIET_AFTER_HOURS * 60:
            return "quiet"
    except Exception as e:
        print(f"[Greeting] silence check failed: {e}")

    try:
        from supabase_store import get_client
        since = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        rows = (get_client().table("sessions").select("valence")
                .eq("user_id", user_id).not_.is_("valence", "null")
                .gte("created_at", since)
                .order("created_at", desc=True).limit(4).execute()).data or []
    except Exception as e:
        print(f"[Greeting] mood read failed: {e}")
        return "quiet"

    vals = [float(r["valence"]) for r in rows if r.get("valence") is not None]
    if not vals:
        return "quiet"

    avg = sum(vals) / len(vals)
    if avg <= DULL_BELOW:
        return "dull"
    if avg >= GOOD_ABOVE:
        return "good"
    # Neither clearly good nor clearly heavy. Gentle is the safe middle: a
    # register that is wrong in the quiet direction costs far less than one
    # that is wrong in the cheerful direction.
    return "quiet"


_TASKS = {
    "good": (
        "Good morning. The last few conversations went well, so match that — "
        "brisk, warm, a little energy. Mention one concrete thing from their "
        "morning or something they told you they were doing. Do not ask how "
        "they are; they are fine, and asking would make the message about "
        "checking on them."
    ),
    "dull": (
        "Good morning. The last few conversations were heavy — do NOT mention "
        "that, do not sympathise, and do not ask about it. Be cheerful, but "
        "carry the cheer in something REAL you are giving them: the weather, "
        "something in their routine, something they said they enjoy. "
        "\"Aaj acha din hoga\" is what a poster says and lands as not having "
        "listened. Lift by offering something concrete, never by claiming the "
        "day will be good."
    ),
    "quiet": (
        "Good morning. There has been nothing from them recently — say so in "
        "no way at all. No 'kahan gayab ho gaye', no note of absence: that is "
        "a reproach dressed as concern. Gentle and short. Give them one small "
        "thing — the weather, the hour, something of theirs — and leave room. "
        "Ask nothing."
    ),
}


def task_for(user_id: str) -> str:
    """The instruction line, with the register already decided."""
    reg = register(user_id)
    print(f"[Greeting] {user_id}: {reg}")

    # Real weather or none. The model wrote "aaj bahar dhoop achi hai" with no
    # idea whether it was sunny — and on a wet Bengaluru morning that is a
    # companion visibly not looking out of the window, which for a product
    # whose whole value is knowing her is worse than saying nothing.
    line = ""
    try:
        from memory.fusion import _weather
        w = _weather(user_id) or {}
        temp = w.get("temp_c") if w.get("temp_c") is not None else w.get("temp")
        desc = w.get("description") or w.get("condition") or ""
        if temp is not None or desc:
            bits = []
            if temp is not None:
                bits.append(f"{round(float(temp))}°C")
            if desc:
                bits.append(str(desc))
            # The route already writes advice in their language — better than
            # anything composed from raw fields here.
            if w.get("advice"):
                bits.append(str(w["advice"]))
            line = ("\n\nThe weather where they are, right now: "
                    + ", ".join(bits) +
                    ". Use it only if it gives you something worth saying — "
                    "cold before their walk, rain before they go out. Never "
                    "describe weather you have not been told.")
    except Exception as e:
        print(f"[Greeting] weather read failed: {e}")

    if not line:
        line = ("\n\nYou do not know what the weather is. Do not mention it "
                "at all.")
    return _TASKS.get(reg, _TASKS["quiet"]) + line + (
        "\n\nNO QUESTION. Not one — not 'kya kehte hain', not 'kaisa lag raha "
        "hai', not a question mark anywhere. A question makes them owe you an "
        "answer first thing in the morning, and the point of this message is "
        "to give them something and leave. End on a statement.\n"
        "One or two sentences. This is the first thing they read today."
    )


def due(user_id: str, now_min: Optional[int] = None) -> bool:
    """Is it their morning, and have they not been greeted today?

    Against their declared wake time, not a clock. Someone who wakes at nine
    should not be greeted at seven, and someone who wakes at five should not
    wait.
    """
    from zoneinfo import ZoneInfo
    try:
        from memory.declared import get_declared
        d = get_declared(user_id)
        tz = ZoneInfo(d.place.timezone)
        now = datetime.now(tz)
        if now_min is None:
            now_min = now.hour * 60 + now.minute

        wake = d.rhythm.wake or "07:00"
        h, m = str(wake)[:5].split(":")
        wake_min = int(h) * 60 + int(m)
    except Exception as e:
        print(f"[Greeting] due check failed: {e}")
        return False

    # From waking until ninety minutes after. Later than that it is not a
    # morning greeting, it is an interruption.
    if not (wake_min <= now_min <= wake_min + 90):
        return False

    try:
        from supabase_store import get_client
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        sent = (get_client().table("proactive_events").select("id")
                .eq("user_id", user_id).eq("action", "GREETING")
                .gte("created_at", start.astimezone(timezone.utc).isoformat())
                .limit(1).execute()).data or []
        return not sent
    except Exception as e:
        print(f"[Greeting] ledger check failed: {e}")
        return False

"""
PROBES — questions built from what an interest is made of.

Curiosity has been telling the model NOT to mention anything it knows, which
was the right fix for the wrong problem: a companion that had learned one thing
about someone said it five times in a day, so the instruction became "ask about
something else entirely". That stops the repetition and gives up the best
material there is.

With interests enriched there is a third option. Sholay has a music director,
a cast, a year; Kishore Kumar has an era and the films he sang for. A question
built from one of those is not a repetition and not a blank sheet:

    "Sholay ka sangeet R.D. Burman ka tha — unka sangeet pasand hai aapko?"

That is a suggestion and a probe in one message. She can answer it warmly
whether or not she takes it up, and either way it says something about which
DIRECTION she follows — cast, music, era — which is the thing worth learning
and the thing a generic question cannot teach.

ONLY VERIFIED FACTS
The model got the music director wrong on all three films tried: S.D. for R.D.
Burman, a singer named as a composer, and a composer who died before the film
was made. So a question may only be built from something Wikipedia or OMDb
confirmed. An inferred fact can decide WHAT to ask about; it cannot appear in
the question.

These are films and singers she has known for fifty years. Being confidently
wrong about them is worse than being dull.

ASKED ONCE
Recorded on the cluster, because asking the same question twice is exactly the
failure the blank-curiosity instruction was written to prevent.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, List

# Which facts make a question worth asking, and how to phrase the probe.
# Ordered: the first that is available and unasked wins, so the most
# discriminating axis is tried first.
PROBES: List[dict] = [
    {
        "axis":  "music",
        "field": "music",
        "for":   ("dekhna",),
        # The strongest probe available. A composer connects one film to a
        # hundred other things, and it is a connection she may never have made
        # herself — which is where the surprise in a good offer comes from.
        "ask":   'The music for "{label}" was by {value}. Ask whether they '
                 'like {value}\'s work more broadly — as something you just '
                 'thought of, not as a quiz.',
    },
    {
        "axis":  "cast",
        "field": "cast",
        "for":   ("dekhna",),
        # Two names, so she can prefer one. "Did you like Dharmendra or
        # Amitabh in it" is answerable in a way "did you like the cast" is not.
        "ask":   'The cast of "{label}" included {value}. Ask which of them '
                 'they liked most in it.',
    },
    {
        "axis":  "director",
        "field": "director",
        "for":   ("dekhna",),
        "ask":   '"{label}" was directed by {value}. Ask if they have seen '
                 'anything else of his.',
    },
    {
        "axis":  "era",
        "field": "year",
        "for":   ("dekhna",),
        "ask":   '"{label}" came out in {value}. Ask what else they were '
                 'watching around then — the era, not the film.',
    },
]


def _asked(attrs: dict) -> List[str]:
    return list((attrs or {}).get("probed") or [])


def pick_probe(user_id: str) -> Optional[Dict]:
    """A question built from a verified fact, or None.

    None is the common answer — nothing enriched, nothing verified, or
    everything already asked — and the caller falls back to ordinary curiosity.
    """
    try:
        from supabase_store import get_client
        rows = (get_client().table("interest_clusters")
                .select("id,label,attributes,strength")
                .eq("user_id", user_id).eq("status", "active")
                .order("strength", desc=True).limit(30).execute()).data or []
    except Exception as e:
        print(f"[Probe] cluster read failed: {e}")
        return None

    for r in rows:
        attrs = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        cat   = attrs.get("category") or ""
        facts = attrs.get("facts") or {}

        # Verified only. Inferred facts may choose what to ask about; they may
        # not appear in the question.
        verified = facts.get("verified") or {}
        if not verified:
            continue

        asked = _asked(attrs)
        for probe in PROBES:
            if cat not in probe["for"] or probe["axis"] in asked:
                continue
            value = verified.get(probe["field"])
            if not value:
                continue
            if isinstance(value, list):
                # Two names is a choice; six is a list to sit through.
                value = ", ".join(str(v) for v in value[:2])

            return {
                "cluster_id": r["id"],
                "label":      r["label"],
                "axis":       probe["axis"],
                "value":      str(value),
                "instruction": probe["ask"].format(label=r["label"], value=value),
            }
    return None


def mark_probed(user_id: str, cluster_id: str, axis: str) -> bool:
    """Remember that this was asked. Asking twice is the failure the blank
    curiosity instruction was written to prevent."""
    try:
        from supabase_store import get_client
        db = get_client()
        rows = (db.table("interest_clusters").select("attributes")
                .eq("id", cluster_id).limit(1).execute()).data or []
        if not rows:
            return False
        attrs = rows[0].get("attributes")
        attrs = attrs if isinstance(attrs, dict) else {}
        probed = _asked(attrs)
        if axis not in probed:
            probed.append(axis)
        attrs["probed"] = probed
        attrs["probed_at"] = datetime.now(timezone.utc).isoformat()
        db.table("interest_clusters").update(
            {"attributes": attrs}).eq("id", cluster_id).execute()
        return True
    except Exception as e:
        print(f"[Probe] mark failed: {e}")
        return False


def probe_instruction(user_id: str) -> str:
    """The line for the composer, and it records that the question was asked.

    Recorded on the way out rather than on a reply, because a question that
    went unanswered has still been asked — repeating it would be worse than
    losing the answer.
    """
    p = pick_probe(user_id)
    if not p:
        return ""

    mark_probed(user_id, p["cluster_id"], p["axis"])
    print(f"[Probe] {user_id}: {p['axis']} of {p['label']!r}")

    return (
        "Ask them ONE thing, built on something they already like:\n"
        f"  {p['instruction']}\n"
        "Say it the way a person would who had just remembered it — a thought, "
        "not a fact being delivered and not a quiz. Do not mention anything "
        "else they like in this message; one thread is the whole point."
    )

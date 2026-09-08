"""
A profile that says one thing once.

Add to memory/profile_cleaner.py, or run standalone.

Shobha's profile carried twenty-one health concerns, five conditions and six
medications. Nearly all of them were one knee and one tablet said different
ways:

    Knee pain · knee pain management · Knee health · Knee pain recovery ·
    knees health · knee pain medication status · knee discomfort in heat ·
    knee pain since yesterday

    unspecified medication for knee pain · pain medication · Regular knee
    pain medication · medication for knee · dawai · medicines expense

The extractor appends a fresh phrasing every session and never checks what is
already there. The list goes in every prompt, so the composer saw twenty-one
reminders that her knee is the most salient thing about her — and duly opened
every message by asking about it.

WHAT THIS KEEPS
The standing fact, not the episode. "Chronic knee pain" survives; "knee pain
since yesterday" does not — that is a Tuesday, and the session it came from
already recorded it. "Dawai" is not a medication and "medicines expense" is
not one either; both go.
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# More than this and the list is noise whatever it contains.
CAP = 6


def collapse(kind: str, items: list) -> list:
    """The few real facts behind a list of restatements."""
    if not items or len(items) <= 2:
        return items

    listing = "\n".join(f"- {i}" for i in items)
    prompt = f"""These are {kind} recorded about one elderly person over
several weeks. Most are the same thing written differently.

{listing}

Return the distinct ones, as JSON: {{"items": ["...", "..."]}}

Merge restatements. "Knee pain", "knee pain management" and "knees health" are
one entry — keep the plainest wording.

Keep only what is STANDING. "Chronic knee pain" stays; "knee pain since
yesterday" is an episode and goes. "Medication compliance" is a worry about a
habit, not a condition, and goes.

For medications, keep only named drugs or clear descriptions. "Dawai" is the
word for medicine, not a medicine. "Medicines expense" is about money.

At most {CAP}. Fewer is better. No prose, only JSON."""

    try:
        from llm import ask
        raw = ask(prompt, max_tokens=400)
        raw = raw.replace("```json", "").replace("```", "").strip()
        out = json.loads(raw).get("items") or []
    except Exception as e:
        print(f"[Clean] {kind} failed: {e}")
        return items

    out = [str(x).strip() for x in out if str(x).strip()]
    return out[:CAP] if out else items


def clean_profile(user_id: str, dry_run: bool = True) -> dict:
    from memory.profile_store import get_user_profile
    from supabase_store import get_client

    p = get_user_profile(user_id) or {}
    health = p.get("health") or {}
    if not isinstance(health, dict):
        return {}

    before, after = {}, {}
    for key in ("concerns", "conditions", "medications", "symptoms"):
        items = health.get(key)
        if not isinstance(items, list) or not items:
            continue
        before[key] = list(items)
        after[key] = collapse(key, items)

    for key in after:
        print(f"\n{key}: {len(before[key])} → {len(after[key])}")
        for x in after[key]:
            print("   -", x)

    if dry_run:
        print("\n(dry run — nothing written)")
        return after

    health.update(after)
    get_client().table("user_profile").update(
        {"health": health}).eq("user_id", user_id).execute()
    print("\nwritten")
    return after


if __name__ == "__main__":
    uid = sys.argv[1] if len(sys.argv) > 1 else "default"
    wet = "--write" in sys.argv
    clean_profile(uid, dry_run=not wet)

"""
PROFILE CLEANER — distillation pass for profile list fields.

Sibling of cluster_cleaner, same philosophy, different target. Profile health
and interest lists accumulate the same phrasing every session in slightly
different words:

    "knee pain", "Knee health", "knees", "knee pain/dard",
    "Knee pain recovery", "knee pain management", "knees health"

String canonicalisation (profile_store._merge_list) already removes the free
wins — case, punctuation, hedge debris. What is left needs judgement that
regex cannot supply, and that cosine alone gets wrong: per entity_resolver's
measurements, "joint pain"/"back pain" scores 0.92, ABOVE pairs that should
merge. Cosine is symmetric and cannot express "one is broader than the other".

Unlike cluster_cleaner there is no vector pre-filter here. A profile list is
small enough (tens of items) to hand the model whole, so the candidate-finding
stage buys nothing and would cost an embedding call per item.

WHAT MUST NOT HAPPEN: medications carry state that looks like noise.
"blood pressure tablet (old)" and "blood pressure tablet (new)" differ by one
word and describe a medication SWITCH — collapsing them destroys the only
record that a change occurred. The prompt is explicit about this, and
medications default to off.
"""
import os
import json
from typing import Optional

_MODEL = "claude-haiku-4-5-20251001"

# Lists this pass will consider. "medications" is deliberately absent — see
# the module docstring. Pass include_medications=True to override.
HEALTH_KEYS   = ("conditions", "concerns")
INTEREST_KEYS = ("sports", "music", "entertainment", "religion", "hobbies")

MIN_ITEMS = 4          # below this, fragmentation isn't worth an LLM call


def _plan(list_name: str, section: str, items: list) -> dict:
    """Ask Haiku which entries are the same thing said differently."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    numbered = "\n".join(f"  [{i}] {it}" for i, it in enumerate(items))

    domain_rule = ""
    if section == "health":
        domain_rule = """
This is a HEALTH list for an elderly person. Extra care:
- A symptom, a diagnosis, and a treatment are DIFFERENT: "knee pain" (symptom),
  "arthritis" (diagnosis) and "knee pain management" (ongoing care) do not merge
  with each other — but all three BELONG in this list. Do not drop an entry for
  being about treatment, medication timing, or care rather than a symptom; a
  caregiver needs those most of all. Only drop entries that state no fact at
  all.
- Different body parts never merge: "knee pain" vs "back aching badly".
- Distinct observations never merge, even about one body part: "Possible
  swelling", "Pain while walking", "Pain at rest" are three separate clinical
  facts and must all survive.
- Anything describing a CHANGE or a comparison over time ("now improving",
  "recurrence", "since yesterday", "old"/"new") records history. Keep it.
- A caregiver may read this list. A wrong merge hides information from them."""
    else:
        domain_rule = """
This is an INTERESTS list. Specifics are the value — "Dilip Kumar films" and
"Devdas" are not the same entry, and a named work should never be absorbed into
a general category. Merge only pure restatements."""

    prompt = f"""You are cleaning one list from a person's memory profile.

LIST: {list_name}
{numbered}
{domain_rule}

Group entries that refer to the SAME real thing said in different words.
Merge ONLY pure restatements — synonyms, translations, looser or tighter
wording for the identical thing:
  "knee pain" / "knees" / "Knee health" / "knee pain/dard"  -> same thing
  "medication compliance" / "Regular medication compliance" -> same thing

Do NOT merge:
- broader vs narrower ("arthritis" vs "knee pain")
- different instances of a kind ("back pain" vs "knee pain")
- merely related or co-occurring things
- anything where you are unsure

For each group, pick the clearest existing entry as canonical — prefer the
plainest wording, and prefer an entry that keeps meaningful detail over one
that loses it.

Also list any entry that is not a real item at all — meaning it states no
fact about this person: "health issue reported", "possibly chronic",
"urgent health concern". These say nothing specific.

An entry IS a real item if it names something concrete, even vaguely worded:
"knees" is about her knees and should merge with other knee entries rather than
be dropped. Dropping is for empty commentary only — when in doubt, merge or
leave alone instead.

When unsure, leave an entry alone. A wrong merge silently destroys
information; a missed merge just leaves the list slightly longer.

Return ONLY JSON:
{{
  "merges": [{{"canonical": "knee pain", "absorb": [1, 4, 7], "reason": "same symptom reworded"}}],
  "drops":  [{{"index": 2, "reason": "classifier commentary, not a condition"}}]
}}
"absorb" and "index" are the [n] numbers above. "canonical" must be one of the
listed entries, verbatim. Empty lists if nothing to do. No prose."""

    resp = client.messages.create(
        model=_MODEL, max_tokens=1500,
        messages=[{"role": "user", "content": prompt}])
    txt = resp.content[0].text.strip()
    if txt.startswith("```"):
        txt = txt.split("```")[1].replace("json", "", 1).strip()
    try:
        return json.loads(txt)
    except Exception as e:
        print(f"[ProfileCleaner] plan parse failed: {e} | raw={txt[:200]}")
        return {"merges": [], "drops": []}


def _match_index(items: list, wanted: str) -> Optional[int]:
    """Locate the model's canonical in the list. It usually copies verbatim but
    sometimes recases or trims, so fall back to a normalised comparison rather
    than discarding the whole group."""
    if wanted in items:
        return items.index(wanted)
    norm = wanted.strip().lower()
    for i, it in enumerate(items):
        if it.strip().lower() == norm:
            return i
    return None


def _apply(items: list, plan: dict) -> tuple:
    """Return (new_list, changes). Ignores anything malformed rather than
    trusting the model's indices blindly."""
    n         = len(items)
    removed   = {}          # index -> reason
    canonical = {}          # index -> replacement text

    for d in plan.get("drops") or []:
        i = d.get("index")
        if isinstance(i, int) and 0 <= i < n:
            removed[i] = d.get("reason") or "dropped"

    # Canonicals are protected: the model sometimes emits groups that reference
    # each other ("Shopping" -> "shopping" AND "shopping" -> "Shopping"), and
    # honouring both would delete every copy of the entry.
    keepers = set()
    for m in plan.get("merges") or []:
        keep = m.get("canonical")
        if not keep:
            continue
        idx = _match_index(items, keep)
        if idx is None:
            print(f"[ProfileCleaner] canonical {keep!r} not in list — skipping group")
            continue
        keepers.add(idx)

    for m in plan.get("merges") or []:
        keep = m.get("canonical")
        if not keep:
            continue
        keep_idx = _match_index(items, keep)
        if keep_idx is None:
            continue
        for i in m.get("absorb") or []:
            if not (isinstance(i, int) and 0 <= i < n):
                continue
            if i == keep_idx or i in keepers:
                continue        # never absorb another group's canonical
            removed[i] = f"merged into {items[keep_idx]!r}: {m.get('reason', '')}".strip()
        canonical[keep_idx] = items[keep_idx]

    # A drop must not remove the last copy of something other entries merged into.
    for i in list(removed):
        if i in keepers and "merged into" not in removed[i]:
            del removed[i]

    new = [it for i, it in enumerate(items) if i not in removed]
    changes = [(items[i], reason) for i, reason in sorted(removed.items())]
    return new, changes


def clean_profile(user_id: str, dry_run: bool = True,
                  include_medications: bool = False) -> dict:
    """
    Distil a user's profile list fields. Defaults to dry_run: unlike clusters,
    a profile has no second copy, so applying is opt-in.
    """
    from supabase_store import get_client

    db   = get_client()
    rows = db.table("user_profile").select("*").eq("user_id", user_id).execute().data
    if not rows:
        return {"status": "no_profile", "user_id": user_id}
    profile = rows[0]

    health_keys = list(HEALTH_KEYS) + (["medications"] if include_medications else [])
    sections = (("health", profile.get("health") or {}, health_keys),
                ("interests", profile.get("interests") or {}, list(INTEREST_KEYS)))

    report  = {"user_id": user_id, "dry_run": dry_run, "sections": {}}
    updates = {}

    for section_name, block, keys in sections:
        if not isinstance(block, dict):
            continue
        new_block, section_changed = dict(block), False
        for key in keys:
            items = block.get(key)
            if not isinstance(items, list) or len(items) < MIN_ITEMS:
                continue
            items = [i for i in items if isinstance(i, str)]
            try:
                plan = _plan(f"{section_name}.{key}", section_name, items)
            except Exception as e:
                print(f"[ProfileCleaner] {section_name}.{key} failed: {e}")
                continue
            new_items, changes = _apply(items, plan)
            if changes:
                section_changed = True
                new_block[key] = new_items
                report["sections"][f"{section_name}.{key}"] = {
                    "before": len(items), "after": len(new_items),
                    "removed": [{"item": it, "reason": r} for it, r in changes],
                }
        if section_changed:
            updates[section_name] = new_block

    if updates and not dry_run:
        db.table("user_profile").update(updates).eq("user_id", user_id).execute()
        report["applied"] = True
        print(f"[ProfileCleaner] applied to {user_id}: {list(updates)}")
    else:
        report["applied"] = False

    return report


# ── Simple dedup: pattern match, then vector similarity ───────────────────────

SIM_THRESHOLD = 0.90


def _norm(s: str) -> str:
    t = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s.lower())
    return " ".join(t.split())


def dedupe_list(items: list, threshold: float = SIM_THRESHOLD) -> tuple:
    """Return (kept, dropped). Exact-normalised match first, then cosine."""
    from memory.entity_resolver import embed_entity
    from classifier.pillar_classifier import cosine_similarity

    kept, dropped, seen, vecs = [], [], {}, []
    embed_failures = 0

    for item in items:
        if not isinstance(item, str) or not item.strip():
            continue
        key = _norm(item)
        if not key:
            continue

        if key in seen:
            dropped.append((item, f"duplicate of {seen[key]!r}"))
            continue

        vec = embed_entity(item)
        if not vec:
            embed_failures += 1
        match = None
        if vec:
            for kept_item, kept_vec in vecs:
                if kept_vec and cosine_similarity(vec, kept_vec) >= threshold:
                    match = kept_item
                    break

        if match:
            dropped.append((item, f"similar to {match!r}"))
        else:
            seen[key] = item
            kept.append(item)
            vecs.append((item, vec))

    if embed_failures:
        # Without vectors this degrades to exact-match dedup, which looks like
        # success while doing almost nothing. Say so loudly.
        print(f"[Dedupe] WARNING: {embed_failures}/{len(items)} embeddings failed "
              f"— only exact duplicates were removed")
    return kept, dropped


def dedupe_profile(user_id: str, dry_run: bool = True,
                   threshold: float = SIM_THRESHOLD) -> dict:
    """Dedupe every list field on a profile. Medications excluded — see module
    docstring."""
    from supabase_store import get_client

    db = get_client()
    rows = db.table("user_profile").select("*").eq("user_id", user_id).execute().data
    if not rows:
        return {"status": "no_profile"}
    profile = rows[0]

    targets = {
        "health":    ["conditions", "concerns"],
        "interests": ["sports", "music", "entertainment", "religion", "hobbies"],
        "family":    ["children", "grandchildren", "other"],
    }

    report, updates = {}, {}
    for section, keys in targets.items():
        block = profile.get(section)
        if not isinstance(block, dict):
            continue
        new_block, changed = dict(block), False
        for key in keys:
            items = block.get(key)
            if not isinstance(items, list) or len(items) < 2:
                continue
            kept, dropped = dedupe_list(items, threshold)
            if dropped:
                changed = True
                new_block[key] = kept
                report[f"{section}.{key}"] = {
                    "before": len(items), "after": len(kept),
                    "dropped": [{"item": i, "reason": r} for i, r in dropped],
                }
        if changed:
            updates[section] = new_block

    if updates and not dry_run:
        db.table("user_profile").update(updates).eq("user_id", user_id).execute()

    return {"user_id": user_id, "dry_run": dry_run,
            "applied": bool(updates and not dry_run), "sections": report}

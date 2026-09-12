"""
REACTIVATION — recall revives, it does not promote.

What was built does the opposite. A cluster recalled three times in one
conversation is PROMOTED into long-term storage, which is to say pushed down
and out of the way. So the things she returns to most often are the first to be
archived.

The intent was the reverse: a memory nobody touches sinks, and one that comes
up again is pulled back. That is what this does.

    w(t+Δ) = w(t) + δ · cos(M, M_query)

Proportional to the match. Something that barely resembles what she said gets
a nudge; something squarely about it gets a real lift. And the clock resets, so
the twenty-eight-day slide toward compression starts again.

WHY NOT JUST TOUCH THE TOP MATCH
Because a sentence can revive several things. "Beta ke saath cricket dekha" is
about her son and about cricket, and both should come back. Anything above the
floor is reactivated, not just the winner.

WHAT DOES NOT REVIVE
Events. They do not decay, so there is nothing to revive — and bumping an
event's strength each time she mentions it would make a single visit look like
a standing preference.
"""
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional

# Below this, a match is coincidence. Measured the same way the health merge
# was: restatements of one subject sit around 0.75, different subjects around
# 0.65, so 0.70 is the floor with room either side.
REVIVE_FLOOR = 0.70

# How much a perfect match is worth. A cluster at 0.2 that she mentions
# squarely comes back to 0.65 — visible again, without pretending it was never
# forgotten.
GAIN = 0.45

# Beyond this, strength stops climbing. Otherwise a subject she mentions daily
# accumulates forever and crowds out everything else.
CEILING = 10.0


def _db():
    from supabase_store import get_client
    return get_client()


def reactivate(user_id: str, text: str, floor: float = REVIVE_FLOOR) -> List[Dict]:
    """Revive whatever this touches. Returns what was revived.

    Called on every message she writes, so it has to be cheap: one embedding,
    then cosine against clusters already in memory.
    """
    if not (text or "").strip():
        return []

    try:
        from classifier.pillar_classifier import embed_text, cosine_similarity
        qv = embed_text(text[:400])
    except Exception as e:
        print(f"[Reactivate] embed failed: {e}")
        return []
    if not qv:
        return []

    try:
        rows = (_db().table("interest_clusters")
                .select("id,label,strength,centroid,kind")
                .eq("user_id", user_id).eq("status", "active")
                .neq("kind", "event")
                .limit(200).execute()).data or []
    except Exception as e:
        print(f"[Reactivate] read failed: {e}")
        return []

    now = datetime.now(timezone.utc).isoformat()
    revived = []

    for r in rows:
        cen = r.get("centroid")
        if isinstance(cen, str):
            try:
                cen = json.loads(cen)
            except Exception:
                cen = None
        if not cen:
            continue

        s = cosine_similarity(qv, cen)
        if s < floor:
            continue

        old = float(r.get("strength") or 0.0)
        new = min(CEILING, old + GAIN * s)

        try:
            _db().table("interest_clusters").update({
                "strength": round(new, 4),
                # The clock. Compression is measured from here, so a mention
                # buys another twenty-eight days.
                "last_event": now,
            }).eq("id", r["id"]).execute()
            revived.append({"label": r.get("label"), "score": round(s, 3),
                            "from": round(old, 2), "to": round(new, 2)})
        except Exception as e:
            print(f"[Reactivate] write failed for {r.get('label')}: {e}")

    if revived:
        print(f"[Reactivate] {user_id}: " +
              ", ".join(f"{x['label']} {x['from']}->{x['to']}" for x in revived))
    return revived


def dormant(user_id: str, days: int = 28) -> List[Dict]:
    """Clusters nobody has touched. What compression would take.

    Kept here rather than in the compressor so the rule lives in one place:
    dormant means untouched, not weak. A strong cluster she has not mentioned
    in a month is still dormant.
    """
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        return (_db().table("interest_clusters")
                .select("id,label,strength,last_event,kind")
                .eq("user_id", user_id).eq("status", "active")
                .neq("kind", "event")
                .lt("last_event", cutoff)
                .order("last_event").limit(100).execute()).data or []
    except Exception as e:
        print(f"[Reactivate] dormant read failed: {e}")
        return []


# A parent is only proposed for things that HAVE parents. A person does not
# belong under anything; a song belongs under its film, a dish under its
# cuisine.
_PARENTABLE = ("sangeet", "dekhna", "khana")


def _verify_parent(label: str, kind: str) -> bool:
    """Does the proposed parent exist outside the model's head?

    Only films can be checked — enrichment already resolves them through OMDb.
    A cuisine or an artist is taken on trust, which is a smaller risk: being
    wrong about "South Indian" as a parent of "dosa" costs little.
    """
    if kind != "film":
        return True
    try:
        from memory.enrich import _omdb
        return bool(_omdb(label))
    except Exception as e:
        print(f"[Parent] could not verify {label!r}: {e}")
        return False


def _propose_parent(label: str, category: str) -> Optional[dict]:
    """What does this belong under? Usually nothing.

    One call, and only when nothing existing matched — which is rare, since
    most writes merge into a cluster that is already there.
    """
    if category not in _PARENTABLE:
        return None

    from llm import ask
    prompt = f"""Someone mentioned liking: "{label}"

Is this PART of something larger? Reply with JSON only:
{{"parent": "...", "kind": "film|artist|cuisine|genre"}}
or {{"parent": null}}

Yes, when the thing is a piece of a larger work or category:
  a song -> the film it is from, when it is a film song
  a dish -> its cuisine
  a character -> the film

No, and this is the usual answer:
  a film is not part of a genre for this purpose — "Sholay" stands alone
  an artist stands alone
  a cuisine stands alone
  anything you are not sure about

Be strict. Naming the wrong film is worse than naming none, because it
claims a connection that is not there. If you cannot place it confidently,
answer null."""

    try:
        raw = ask(prompt, max_tokens=120).replace("```json", "").replace("```", "")
        d = json.loads(raw.strip())
    except Exception as e:
        print(f"[Parent] proposal failed for {label!r}: {e}")
        return None

    parent = (d.get("parent") or "").strip()
    if not parent or parent.lower() in ("null", "none"):
        return None
    if parent.lower() == (label or "").lower():
        return None

    kind = (d.get("kind") or "").strip().lower()
    if not _verify_parent(parent, kind):
        print(f"[Parent] {parent!r} did not verify — leaving {label!r} a root")
        return None
    return {"label": parent, "kind": kind}


def assign_parent(user_id: str, cluster_id: str, label: str,
                  category: str = "", pillar: str = "GENERAL") -> Optional[str]:
    """Put this under something, creating the parent if it is not there.

    Returns the parent's id, or None when the thing stands alone.
    """
    db = _db()

    proposed = _propose_parent(label, category)
    if not proposed:
        return None

    plabel = proposed["label"]

    # Already there? Reuse it — three songs from one film must find the same
    # parent, not create three.
    try:
        found = (db.table("interest_clusters").select("id")
                 .eq("user_id", user_id).eq("label", plabel)
                 .limit(1).execute()).data or []
    except Exception as e:
        print(f"[Parent] lookup failed: {e}")
        return None

    if found:
        pid = found[0]["id"]
    else:
        row = {
            "user_id": user_id, "label": plabel, "pillar": pillar,
            "kind": "interest", "status": "active",
            # Weaker than a thing she actually named. She likes the songs;
            # the film is an inference from that.
            "strength": 0.5,
            "attributes": {"category": category, "role": "parent",
                           "parent_kind": proposed.get("kind", "")},
        }
        try:
            from classifier.pillar_classifier import embed_text
            v = embed_text(plabel)
            if v:
                row["centroid"] = v
        except Exception:
            pass
        try:
            r = db.table("interest_clusters").insert(row).execute()
            pid = (r.data or [{}])[0].get("id")
        except Exception as e:
            print(f"[Parent] could not create {plabel!r}: {e}")
            return None

    if not pid:
        return None

    try:
        db.table("interest_clusters").update(
            {"parent_id": pid}).eq("id", cluster_id).execute()
        print(f"[Parent] {label!r} -> {plabel!r}")
    except Exception as e:
        print(f"[Parent] could not link: {e}")
        return None

    # Adopt the orphans. "Zinda" arrived before the film existed and got no
    # parent; when "O Rangrez" creates it, Zinda should move under it too.
    _adopt_orphans(user_id, pid, plabel, category)
    return pid


def _adopt_orphans(user_id: str, parent_id: str, parent_label: str,
                   category: str):
    """Parentless clusters that belong under a parent which now exists.

    Without this, order decides the shape: the first song of a soundtrack is
    always a root and only the later ones are filed properly.
    """
    try:
        rows = (_db().table("interest_clusters")
                .select("id,label,attributes")
                .eq("user_id", user_id).is_("parent_id", "null")
                .neq("id", parent_id).neq("kind", "event")
                .limit(60).execute()).data or []
    except Exception:
        return

    for r in rows:
        a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        if (a.get("category") or "") != category or a.get("role") == "parent":
            continue
        p = _propose_parent(r.get("label") or "", category)
        if p and p["label"].lower() == parent_label.lower():
            try:
                _db().table("interest_clusters").update(
                    {"parent_id": parent_id}).eq("id", r["id"]).execute()
                print(f"[Parent] adopted {r.get('label')!r} -> {parent_label!r}")
            except Exception:
                pass


def group_session(user_id: str, session_id: str, category: str = "") -> int:
    """Put this session's new clusters under a shared parent, if any found one.

    Returns how many were moved.

    "Zinda" is unplaceable on its own — several songs carry the name — and
    "O Rangrez" resolves to Bhaag Milkha Bhaag. Said in one conversation they
    are one soundtrack, and the one that placed itself places the rest.
    """
    db = _db()

    # What she named in this session. The behavioural event carries the
    # session, so it is the link between a conversation and its clusters.
    try:
        evs = (db.table("user_behavioral_events")
               .select("cluster_id")
               .eq("user_id", user_id).eq("session_id", session_id)
               .limit(40).execute()).data or []
    except Exception as e:
        print(f"[Group] session read failed: {e}")
        return 0

    ids = [e["cluster_id"] for e in evs if e.get("cluster_id")]
    if len(ids) < 2:
        return 0                      # one thing cannot group with itself

    try:
        rows = (db.table("interest_clusters")
                .select("id,label,parent_id,attributes,kind")
                .in_("id", ids).neq("kind", "event").execute()).data or []
    except Exception as e:
        print(f"[Group] cluster read failed: {e}")
        return 0

    # Same category only. Songs group with songs; a song and a dish mentioned
    # in one conversation are not one thing.
    def _cat(r):
        a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        return a.get("category") or ""

    if category:
        rows = [r for r in rows if _cat(r) == category]
    else:
        cats = {_cat(r) for r in rows if _cat(r)}
        if len(cats) != 1:
            return 0
        category = cats.pop()
        rows = [r for r in rows if _cat(r) == category]

    if len(rows) < 2:
        return 0

    # Did any of them place itself?
    parents = {r.get("parent_id") for r in rows if r.get("parent_id")}
    if len(parents) != 1:
        # None found a parent, or they found different ones. Two different
        # parents in one conversation is two subjects, not a grouping error.
        return 0

    pid = parents.pop()
    orphans = [r for r in rows if not r.get("parent_id")]
    if not orphans:
        return 0

    moved = 0
    for r in orphans:
        try:
            db.table("interest_clusters").update(
                {"parent_id": pid}).eq("id", r["id"]).execute()
            moved += 1
        except Exception as e:
            print(f"[Group] could not move {r.get('label')!r}: {e}")

    if moved:
        print(f"[Group] {user_id}: {moved} named together joined their parent")
    return moved

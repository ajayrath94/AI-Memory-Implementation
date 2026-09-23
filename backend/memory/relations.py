"""
RELATIONS — what links to what, and when it happened.

Merging was the wrong operation. It keeps one label and destroys the other, and
we were using it to say things that are not identity:

    metformin absorbed into "blood pressure"   loses the drug, and files a
                                               diabetes medicine under the
                                               wrong illness
    "knee pain" absorbed into "pain"           loses the knee
    "O Rangrez" absorbed into a film           loses the song

Four attempts at a merge rule, each trading one failure set for another, because
the question itself was wrong. An edge keeps both labels and says how they are
connected.

    metformin  ──treats──▶  diabetes
    Arjun      ──lives_in─▶ Delhi
    "Arjun left" ──about──▶ Arjun

STORED, NOT RE-DERIVED
The instability came from asking a model the same question repeatedly and
getting different answers — "diabetes" was a category on one call and a named
thing on the next. An edge is written once and looked up thereafter, so a
mistake is a row to correct rather than a behaviour that recurs.

WHAT STILL MERGES
Synonymy, and only that. "Ghutne ka dard" and "knee pain" are one thing said
twice, which is a judgement embeddings make well — high cosine, no relational
reasoning. Everything else becomes an edge.
"""
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional


# Nothing merges. Measured label to label:
#
#     Kishore Kumar / Kishore Kumar   1.000   identity
#     Kishore da    / Kishore Kumar   0.810   a synonym
#     Kumar Sanu    / Kishore Kumar   0.733   a different singer
#     ghutne ka dard / knee pain      0.731   a synonym, in another language
#
# Synonymy and difference overlap, and not by a little: a Hindi synonym scores
# BELOW two unrelated singers, because the embedding reads one as two languages
# for a thing and the other as two names of the same shape. No threshold
# separates them.
#
# So same_as is an edge like any other. Nothing is destroyed, retrieval follows
# the edge, and a wrong one is a row to delete rather than a label that is
# gone. Which was the conclusion the merge attempts kept pointing at.
# Low, because this only decides what to ASK about — the model decides.
#
# At 0.78 the pairs that matter were never proposed: ghutna / knee pain at
# 0.695, bagwani / gardening at 0.680. And no higher bar could have worked,
# because Kishore Kumar / Lata Mangeshkar — two different singers — scores
# 0.704, ABOVE both. Embeddings cannot separate "the same thing in two
# languages" from "two things of the same kind".
#
# So cosine narrows and the model rules. Two or three Flash-Lite calls when a
# new cluster appears, none otherwise.
SAME_AS = 0.62          # worth ASKING about, not worth merging on

TYPES = (
    "same_as",      # identity. the only case that merges.
    "part_of",      # a song of a film, an episode of a serial, a character
    "instance_of",  # a match of cricket, idli of South Indian food
    "treats",       # a drug and what it is for
    "symptom_of",   # swelling and the knee
    "about",        # an event and who or what it concerns
    "lives_in",     # a person and a place
    "does",         # a person and an occupation
    "related_to",   # worth recording, not worth traversing
)

# Symmetric types are stored once and read both ways rather than twice.
_SYMMETRIC = {"same_as", "related_to"}


def _db():
    from supabase_store import get_client
    return get_client()


# ── writing ───────────────────────────────────────────────────────────────────

def link(user_id: str, from_id: str, to_id: str, rtype: str,
         confidence: float = 1.0) -> bool:
    """Record that these two are connected. Idempotent."""
    if not (from_id and to_id) or from_id == to_id:
        return False
    if rtype not in TYPES:
        print(f"[Relations] unknown type {rtype!r}")
        return False

    now = datetime.now(timezone.utc).isoformat()
    try:
        _db().table("entity_relations").upsert({
            "user_id": user_id, "from_id": from_id, "to_id": to_id,
            "type": rtype, "confidence": round(float(confidence), 3),
            "last_seen": now,
        }, on_conflict="from_id,to_id,type").execute()
        return True
    except Exception as e:
        print(f"[Relations] link failed: {e}")
        return False


def unlink(from_id: str, to_id: str, rtype: str = "") -> bool:
    """Remove an edge. A wrong one is a row to delete, which was the point."""
    try:
        q = (_db().table("entity_relations").delete()
             .eq("from_id", from_id).eq("to_id", to_id))
        if rtype:
            q = q.eq("type", rtype)
        q.execute()
        return True
    except Exception as e:
        print(f"[Relations] unlink failed: {e}")
        return False


# ── reading ───────────────────────────────────────────────────────────────────

def relations_for(user_id: str, cluster_id: str,
                  rtype: str = "") -> List[Dict]:
    """Everything connected to this, in either direction.

    Direction is stored because "metformin treats diabetes" reads one way, but
    a symmetric type is read both ways from one row rather than needing two.
    """
    db = _db()
    out = []
    try:
        for row in (db.table("entity_relations").select("*")
                    .eq("user_id", user_id).eq("from_id", cluster_id)
                    .execute()).data or []:
            if rtype and row.get("type") != rtype:
                continue
            out.append({**row, "other_id": row["to_id"], "outgoing": True})

        for row in (db.table("entity_relations").select("*")
                    .eq("user_id", user_id).eq("to_id", cluster_id)
                    .execute()).data or []:
            if rtype and row.get("type") != rtype:
                continue
            out.append({**row, "other_id": row["from_id"],
                        "outgoing": row.get("type") in _SYMMETRIC})
    except Exception as e:
        print(f"[Relations] read failed: {e}")
    return out


def neighbours(user_id: str, cluster_id: str, rtype: str = "") -> List[Dict]:
    """The clusters on the other end, with their labels."""
    rels = relations_for(user_id, cluster_id, rtype)
    ids = [r["other_id"] for r in rels]
    if not ids:
        return []
    try:
        rows = (_db().table("interest_clusters")
                .select("id,label,kind,happened_on,strength,attributes")
                .in_("id", ids).execute()).data or []
    except Exception as e:
        print(f"[Relations] neighbour read failed: {e}")
        return []

    by_id = {r["id"]: r for r in rows}
    out = []
    for r in rels:
        n = by_id.get(r["other_id"])
        if n:
            out.append({**n, "relation": r["type"],
                        "outgoing": r.get("outgoing", True)})
    return out


def timeline_for(user_id: str, cluster_id: str) -> List[Dict]:
    """What happened, about this, in order.

    The thing nothing could answer before. Arjun is a node and his visits hang
    off it — "kab aaya tha" becomes a walk rather than a text search, and
    "how often does he come" becomes answerable at all.
    """
    evs = [n for n in neighbours(user_id, cluster_id, "about")
           if n.get("kind") == "event"]
    return sorted(evs, key=lambda e: str(e.get("happened_on") or ""),
                  reverse=True)


# ── synonymy: the only merge ──────────────────────────────────────────────────

def find_same_as(user_id: str, label: str,
                 embedding: List[float] = None) -> Optional[Dict]:
    """A cluster that IS this, not one that is merely about it.

    No model call. The question "are these two labels the same thing" is what
    embeddings are good at, and the relational reasoning that kept going wrong
    is not needed for it.
    """
    if not embedding:
        try:
            from classifier.pillar_classifier import embed_text
            embedding = embed_text(label)
        except Exception:
            return None
    if not embedding:
        return None

    try:
        from classifier.pillar_classifier import cosine_similarity
        # Against the LABEL, not the centroid. The centroid is a running mean
        # of everything in the cluster, so "Kishore Kumar" scored 0.764
        # against its own cluster — identity diluted by every song of his she
        # has mentioned. At that ceiling a synonym at 0.703 is
        # indistinguishable from a relation, and no threshold is meaningful.
        #
        # Synonymy is a question about two labels.
        rows = (_db().table("interest_clusters")
                .select("id,label,centroid,kind")
                .eq("user_id", user_id).eq("status", "active")
                .neq("kind", "event")
                .not_.is_("centroid", "null").limit(200).execute()).data or []
    except Exception as e:
        print(f"[Relations] same_as read failed: {e}")
        return None

    best, best_score = None, 0.0
    for r in rows:
        if str(r.get("label", "")).lower() == (label or "").lower():
            return {"id": r["id"], "label": r["label"], "score": 1.0}
        lv = embed_text(str(r.get("label") or ""))
        if not lv:
            continue
        s = cosine_similarity(embedding, lv)
        if s > best_score:
            best, best_score = r, s

    if not (best and best_score >= SAME_AS):
        return None

    # Above the bar means worth asking, not worth assuming. Kumar Sanu sits at
    # 0.733 against Kishore Kumar and is a different person; the score alone
    # cannot tell.
    try:
        from llm import ask
        a = ask(f'Are these two the same thing, or two different things?\n\n'
                f'A: "{label}"\nB: "{best["label"]}"\n\n'
                f'Same if they refer to the same thing, however differently '
                f'it is written — a nickname, an abbreviation, or HER WORD AND '
                f'THE ENGLISH FOR IT. "bagwani" and "gardening" are the same '
                f'activity and came back as different, because the rule said '
                f'"the same words in another language" and bagwani is not the '
                f'same words.\n\n'
                f'Different if they are two things of the same kind — two '
                f'singers, two films, two dishes. And different if one is a '
                f'body part and the other a condition: a knee is not knee '
                f'pain.\n\nOne word: same or different.',
                max_tokens=10).strip().lower()
    except Exception as e:
        print(f"[Relations] same_as check failed: {e}")
        return None

    if not a.startswith("same"):
        return None
    return {"id": best["id"], "label": best["label"],
            "score": round(best_score, 3)}


# ── migrating what is there ───────────────────────────────────────────────────

def adopt_parents(user_id: str) -> int:
    """parent_id becomes a part_of edge.

    Left in place rather than removed — both can be read while the edges earn
    trust, and nothing that reads parent_id breaks today.
    """
    try:
        rows = (_db().table("interest_clusters").select("id,parent_id")
                .eq("user_id", user_id).not_.is_("parent_id", "null")
                .execute()).data or []
    except Exception as e:
        print(f"[Relations] parent read failed: {e}")
        return 0

    n = 0
    for r in rows:
        if link(user_id, r["id"], r["parent_id"], "part_of"):
            n += 1
    if n:
        print(f"[Relations] {user_id}: {n} parent links became edges")
    return n


def extract_edges(user_id: str, text: str, cluster_ids: List[str]) -> int:
    """What connects the things this conversation mentioned. Returns how many.

    Only among clusters that already exist — this finds relationships, it does
    not create entities. Anything worth being a node became one earlier in the
    pipeline.
    """
    if not cluster_ids or len(cluster_ids) < 1:
        return 0

    db = _db()
    try:
        rows = (db.table("interest_clusters").select("id,label,kind")
                .in_("id", list(set(cluster_ids))).execute()).data or []
    except Exception as e:
        print(f"[Relations] cluster read failed: {e}")
        return 0

    # Everything she already has, so an edge can reach something mentioned
    # weeks ago — "Vikram Pune shift ho gaya" has to find the Vikram from
    # three sessions back, not only what is in this one.
    try:
        known = (db.table("interest_clusters").select("id,label,kind")
                 .eq("user_id", user_id).eq("status", "active")
                 .limit(80).execute()).data or []
    except Exception:
        known = rows

    by_label = {str(r["label"]).lower(): r["id"] for r in known}
    listing = "\n".join(f"- {r['label']}" for r in known[:60])
    if not listing:
        return 0

    prompt = f"""Someone said: "{text[:400]}"

These are things already known about them:
{listing}

What does this tell you about how any of them RELATE? Reply with JSON only:
{{"edges": [{{"from": "...", "to": "...", "type": "..."}}]}}

type is one of:
  part_of      a song of a film, an episode of a serial, a character
  instance_of  a match of cricket, idli of South Indian food
  treats       a medicine and the condition it is for
  symptom_of   swelling and the knee it is in
  lives_in     a person and where they live
  does         a person and their work
  about        an event and who or what it concerns
  related_to   connected, but none of the above

Use the labels EXACTLY as written above. Both ends must be in that list.

Only what this message tells you. Do not add what you happen to know about
the world — that Pune is in Maharashtra is true and is not something she
said.

An empty list is the usual answer. Most messages establish no new
relationship at all."""

    try:
        from llm import ask
        raw = ask(prompt, max_tokens=400).replace("```json", "").replace("```", "")
        found = json.loads(raw.strip()).get("edges") or []
    except Exception as e:
        print(f"[Relations] edge extraction failed: {e}")
        return 0

    n = 0
    for e in found:
        a = by_label.get(str(e.get("from", "")).strip().lower())
        b = by_label.get(str(e.get("to", "")).strip().lower())
        rtype = str(e.get("type", "")).strip().lower()
        if not (a and b) or rtype not in TYPES:
            continue
        if link(user_id, a, b, rtype):
            n += 1
            print(f"[Relations] {e.get('from')} --{rtype}--> {e.get('to')}")
    return n


def link_events(user_id: str, event_ids: List[str]) -> int:
    """Attach each event to whoever or whatever it is about.

    Separate from extract_edges because an event is not a thing she mentioned
    — it is something that happened, and the subject is usually named right
    there in the label: "Arjun arrived from Delhi" is about Arjun.
    """
    if not event_ids:
        return 0
    db = _db()
    try:
        evs = (db.table("interest_clusters").select("id,label")
               .in_("id", list(set(event_ids))).execute()).data or []
        people = (db.table("interest_clusters").select("id,label")
                  .eq("user_id", user_id).neq("kind", "event")
                  .eq("status", "active").limit(60).execute()).data or []
    except Exception as e:
        print(f"[Relations] event link read failed: {e}")
        return 0

    n = 0
    for ev in evs:
        label = str(ev.get("label") or "").lower()
        for p in people:
            name = str(p.get("label") or "").strip()
            # A name appearing in the event text is the subject. Crude, and
            # it holds because event labels are short and name what happened.
            if len(name) > 2 and name.lower() in label:
                if link(user_id, ev["id"], p["id"], "about"):
                    n += 1
                    print(f"[Relations] '{ev['label'][:30]}' --about--> {name}")
    return n


# One at a time. A new edge of these types ends the previous one rather than
# sitting beside it — he cannot live in two cities, and a drug treats the
# condition it treats.
#
# Everything else accumulates: she may like many singers, and an event is
# about whoever it is about.
_EXCLUSIVE = {"lives_in", "does", "treats"}


def link_current(user_id: str, from_id: str, to_id: str, rtype: str,
                 confidence: float = 1.0) -> bool:
    """Record this, and close whatever it replaces.

    The closed edge is kept. "He lived in Delhi until September" is a fact
    about her life, and deleting it to make room for Pune would lose it.
    """
    if rtype not in _EXCLUSIVE:
        return link(user_id, from_id, to_id, rtype, confidence)

    now = datetime.now(timezone.utc).isoformat()
    db = _db()

    try:
        open_edges = (db.table("entity_relations").select("id,to_id")
                      .eq("user_id", user_id).eq("from_id", from_id)
                      .eq("type", rtype).is_("ended_at", "null")
                      .execute()).data or []
    except Exception as e:
        print(f"[Relations] open-edge read failed: {e}")
        open_edges = []

    for e in open_edges:
        if e.get("to_id") == to_id:
            # Already the current answer. Touch it so the recency is right and
            # leave it open.
            try:
                db.table("entity_relations").update(
                    {"last_seen": now}).eq("id", e["id"]).execute()
            except Exception:
                pass
            return True
        try:
            db.table("entity_relations").update(
                {"ended_at": now}).eq("id", e["id"]).execute()
            print(f"[Relations] closed a {rtype} edge — it changed")
        except Exception as ex:
            print(f"[Relations] could not close: {ex}")

    return link(user_id, from_id, to_id, rtype, confidence)


def current(user_id: str, cluster_id: str, rtype: str) -> Optional[Dict]:
    """What is true NOW, for a type that has one answer.

    "Kahan rehta hai ab" — the open edge, not the most recent row, because a
    correction closes the old one the moment the new one arrives.
    """
    db = _db()
    try:
        rows = (db.table("entity_relations").select("to_id,first_seen")
                .eq("user_id", user_id).eq("from_id", cluster_id)
                .eq("type", rtype).is_("ended_at", "null")
                .order("first_seen", desc=True).limit(1).execute()).data or []
    except Exception as e:
        print(f"[Relations] current read failed: {e}")
        return None
    if not rows:
        return None

    try:
        c = (db.table("interest_clusters").select("id,label")
             .eq("id", rows[0]["to_id"]).limit(1).execute()).data or []
    except Exception:
        return None
    return {"id": c[0]["id"], "label": c[0]["label"],
            "since": rows[0].get("first_seen")} if c else None


def history(user_id: str, cluster_id: str, rtype: str = "") -> List[Dict]:
    """Everything that was ever true, in order, open and closed.

    Where someone has lived, what they have done. The closed edges are the
    point — an attribute would have overwritten them.
    """
    db = _db()
    try:
        q = (db.table("entity_relations").select("*")
             .eq("user_id", user_id).eq("from_id", cluster_id))
        if rtype:
            q = q.eq("type", rtype)
        rows = q.order("first_seen").execute().data or []
    except Exception as e:
        print(f"[Relations] history read failed: {e}")
        return []
    if not rows:
        return []

    ids = [r["to_id"] for r in rows]
    try:
        cl = (db.table("interest_clusters").select("id,label")
              .in_("id", ids).execute()).data or []
    except Exception:
        return []

    by_id = {c["id"]: c["label"] for c in cl}
    return [{
        "label": by_id.get(r["to_id"], "?"),
        "type": r.get("type"),
        "from": str(r.get("first_seen") or "")[:10],
        "to": str(r.get("ended_at") or "")[:10] or None,
        "current": not r.get("ended_at"),
    } for r in rows if r["to_id"] in by_id]

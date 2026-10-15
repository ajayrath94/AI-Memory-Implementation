"""
CLUSTER RESOLVER — decide which ongoing concern a new event belongs to.

One level up from entity resolution. Entity resolution answers "is this the
same *thing* said differently" (knee / ghutne ka dard -> knee pain). Cluster
resolution answers "does this belong to the same ongoing *concern*"
(amlodipine, blood pressure, BP medication -> one blood-pressure cluster).

Because a concern legitimately spans related-but-distinct entities, the LLM
judge here asks a broader question than the entity judge: not "same thing" but
"same ongoing situation".
"""

import os
import json
from typing import Optional, List

# A concern is broader than a synonym, so the floor sits a touch lower than the
# entity resolver's 0.87 — but still well above the ~0.81 noise floor measured
# on gemini-embedding-001.
CLUSTER_FLOOR = 0.84
MAX_CANDIDATES = 4


def _cosine(a, b) -> float:
    from classifier.pillar_classifier import cosine_similarity
    return cosine_similarity(a, b)


# ── What a status means to the writers ────────────────────────────────────
#
# active    a live group: matched, counted, shown.
# merged    the same thing as another group, which holds it now. Its id is
#           a forwarding address: attributes.merged_into says where to go.
# archived  decided against — a state ("Aram"), a generic word ("movie"), a
# dropped   word mistaken for a person ("Dhyanesh"), a bucket that was split.
#           Known, so not created again, but never brought back by a mention.
#
# Before this, every writer matched groups of any status and set the match
# back to "active", so a clean-up lasted only until she said the word again.

def _status(row: dict) -> str:
    return (row or {}).get("status") or "active"


def parked(row: dict) -> bool:
    """Archived or dropped: known, not to be revived by a mention."""
    return _status(row) not in ("active", "merged")


def _attrs(row: dict) -> dict:
    a = (row or {}).get("attributes")
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except Exception:
            a = {}
    return a if isinstance(a, dict) else {}


def follow(db, row: dict, fields: str = "id,label,status,attributes") -> dict:
    """The group a merged row now lives in. Follows merged_into (a few hops
    at most, in case a survivor was itself merged later) and returns that
    row; any other row is returned as it is."""
    seen = set()
    while row and _status(row) == "merged" and len(seen) < 5:
        seen.add(row.get("id"))
        to = _attrs(row).get("merged_into")
        if not to or to in seen:
            break
        got = (db.table("interest_clusters").select(fields)
               .eq("id", to).limit(1).execute()).data
        if not got:
            break
        row = got[0]
    return row


def find_cluster(user_id: str, label: str, pillar: str,
                 embedding: List[float]) -> Optional[str]:
    """
    Return the id of the cluster this event belongs to, or None for a new one.

    Reuses the embedding the entity resolver already computed — no extra call.
    """
    if not embedding:
        return None

    try:
        from supabase_store import get_client
        db = get_client()
        rows = (db.table("interest_clusters")
                .select("id,label,pillar,centroid,status,attributes")
                .eq("user_id", user_id)
                .eq("pillar", pillar)            # concerns don't cross pillars
                .not_.is_("centroid", "null")
                .limit(100)
                .execute()).data or []
    except Exception as e:
        print(f"[ClusterResolver] fetch failed: {e}")
        return None

    # Archived groups are not candidates: the old catch-all "Health" sits
    # close to every health word and would swallow a new concern into a
    # group nobody sees. Merged rows stay — they are the same thing under
    # another name — and a match on one is forwarded to where it went.
    rows = [r for r in rows if not parked(r)]
    by_id = {r["id"]: r for r in rows}

    scored = []
    for r in rows:
        cen = r.get("centroid")
        if isinstance(cen, str):
            try:
                cen = json.loads(cen)
            except Exception:
                continue
        if not cen:
            continue
        s = _cosine(embedding, cen)
        if s >= CLUSTER_FLOOR:
            scored.append({"id": r["id"], "label": r["label"], "score": round(s, 4)})

    if not scored:
        return None

    scored.sort(key=lambda x: x["score"], reverse=True)
    candidates = scored[:MAX_CANDIDATES]

    verdict = _adjudicate(label, candidates)
    if verdict:
        print(f"[ClusterResolver] {label!r} -> cluster {verdict['label']!r} "
              f"({[c['label'] for c in candidates]})")
        hit = by_id.get(verdict["id"]) or {"id": verdict["id"]}
        if _status(hit) == "merged":
            try:
                to = follow(db, hit)
            except Exception as e:
                print(f"[ClusterResolver] follow failed: {e}")
                return None
            if not to or _status(to) == "merged" or parked(to):
                return None
            print(f"[ClusterResolver] {verdict['label']!r} was merged -> "
                  f"{to.get('label')!r}")
            return to["id"]
        return verdict["id"]
    return None


def _adjudicate(label: str, candidates: List[dict]) -> Optional[dict]:
    """
    Does this new thing belong to one of these ongoing concerns?

    Broader than the entity judge: amlodipine BELONGS to a blood-pressure
    concern even though it is not a synonym for it. But knee pain does NOT
    belong to a blood-pressure concern, and cricket does not belong to a
    music concern — those are different situations.
    """
    listing = "\n".join(f"- {c['label']}" for c in candidates)
    prompt = f"""A person mentioned: "{label}"

They have these ongoing concerns / interests already tracked:
{listing}

Does "{label}" BELONG TO one of these ongoing concerns — i.e. is it part of
the same situation the person is dealing with over time?

Belongs (answer the concern name):
- a treatment, symptom, doctor, or medicine for a health concern already listed
  (amlodipine belongs to "blood pressure"; ankle swelling from BP meds belongs to "blood pressure")
- a specific instance of a listed interest (a particular match belongs to "cricket")

Does NOT belong (answer NEW):
- a different body part or condition (knee pain is not blood pressure)
- a different topic entirely
- a broader category than what is listed
- ANOTHER THING OF THE SAME KIND. Two films are two films: "Bhaag Milkha
  Bhaag" does not belong to "Sholay", and Kumar Sanu does not belong to
  Kishore Kumar. A specific match belongs to "cricket" because cricket is
  the ongoing interest and the match is an instance of it — but one named
  work is never an instance of another named work. If both are particular
  things rather than one being a category, answer NEW.
- a NAMED thing into an unnamed category. "Kishore Kumar" must not merge
  into "music", "dosa" must not merge into "food", "Sholay" must not merge
  into "films". The merge keeps the listed label, so a name would become a
  genre and the person or dish is gone. If what was mentioned has a name and
  the listed concern does not, answer NEW.

  This is about names versus CATEGORIES, not names versus names. A named work
  contains its named parts: "O Rangrez" belongs to "Bhaag Milkha Bhaag" and
  "Gabbar" belongs to "Sholay", because a song and a character are pieces of
  the film itself. "Music" and "films" are categories; a particular film is
  not.
- anything where the listed concern is VAGUER than what was mentioned.
  "Knee pain" must not merge into "pain": the merge keeps the listed label,
  so a specific complaint would become a general one and the detail is gone
  for good.

When unsure, answer NEW — a wrong merge corrupts the timeline.

Reply with exactly one line: the concern name verbatim, or NEW."""

    try:
        from google import genai
        client = __import__("llm").genai_client()
        resp = client.models.generate_content(
            model="gemini-flash-lite-latest", contents=prompt)
        answer = (resp.text or "").strip().strip('"').strip()

        if answer.upper() == "NEW" or not answer:
            return None
        for c in candidates:
            if answer.lower() == c["label"].lower():
                return c
        return None
    except Exception as e:
        print(f"[ClusterResolver] adjudication failed: {e}")
        return None

def _general_label(a: str, b: str) -> str:
    """Of two labels for one concern, return the more general (condition over instance)."""
    if a.strip().lower() == b.strip().lower():
        return a
    prompt = f"""Two labels describe the same ongoing concern:
- "{a}"
- "{b}"

Which is the more general name for the concern itself — the condition or theme,
rather than a specific instance, treatment, or detail?
Examples: between "amlodipine" and "blood pressure", choose "blood pressure".
Between "India match" and "cricket", choose "cricket".
Reply with exactly one of the two labels, verbatim. No other text."""
    try:
        from google import genai
        client = __import__("llm").genai_client()
        resp = client.models.generate_content(model="gemini-flash-lite-latest", contents=prompt)
        ans = (resp.text or "").strip().strip('"').strip()
        for lab in (a, b):
            if ans.lower() == lab.lower():
                return lab
        return a
    except Exception as e:
        print(f"[ClusterResolver] general-label pick failed: {e}")
        return a


def merge_clusters(user_id: str, keep_id: str, absorb_id: str, label: str = None):
    """
    Fold one cluster into another: repoint its events, sum the totals,
    recompute the centroid as the count-weighted mean, delete the absorbed row.
    """
    from supabase_store import get_client
    db = get_client()
    try:
        rows = (db.table("interest_clusters")
                .select("id,event_count,strength,centroid")
                .in_("id", [keep_id, absorb_id]).execute()).data or []
        by_id = {r["id"]: r for r in rows}
        keep, absorb = by_id.get(keep_id), by_id.get(absorb_id)
        if not keep or not absorb:
            return

        kn, an = keep.get("event_count") or 0, absorb.get("event_count") or 0
        kc, ac = keep.get("centroid"), absorb.get("centroid")
        merged_centroid = keep.get("centroid")
        if kc and ac and len(kc) == len(ac) and (kn + an) > 0:
            merged_centroid = [
                round((k * kn + a * an) / (kn + an), 6)
                for k, a in zip(kc, ac)
            ]

        db.table("user_behavioral_events").update(
            {"cluster_id": keep_id}).eq("cluster_id", absorb_id).execute()

        db.table("interest_clusters").delete().eq("id", absorb_id).execute()

        # Recompute the count from actual rows rather than summing — the summed
        # value can drift if any event was pointing at a stale cluster id.
        real = (db.table("user_behavioral_events")
                .select("id", count="exact")
                .eq("cluster_id", keep_id).execute())
        real_count = real.count if real.count is not None else (kn + an)

        update = {
            "event_count": real_count,
            "strength":    round((keep.get("strength") or 0) + (absorb.get("strength") or 0), 4),
            "centroid":    merged_centroid,
        }
        if label:
            update["label"] = label
        db.table("interest_clusters").update(update).eq("id", keep_id).execute()
        print(f"[ClusterResolver] merged {absorb_id} -> {keep_id}")
        return keep_id
    except Exception as e:
        print(f"[ClusterResolver] merge failed: {e}")
        return keep_id


def reconcile(user_id: str, cluster_id: str, pillar: str):
    """
    Deferred merge: after a cluster is created/updated, check whether any OTHER
    cluster in the same pillar is now close enough to be the same concern.

    Fixes the order-of-arrival problem — "amlodipine" arriving before the
    "blood pressure" cluster exists creates an orphan that this later folds in.
    """
    from supabase_store import get_client
    db = get_client()
    try:
        # Active only. Merging into a merged or archived survivor hid the
        # live group from everything that reads "active", and deleted it.
        rows = (db.table("interest_clusters")
                .select("id,label,event_count,centroid")
                .eq("user_id", user_id).eq("pillar", pillar)
                .eq("status", "active")
                .not_.is_("centroid", "null").limit(100).execute()).data or []
    except Exception as e:
        print(f"[ClusterResolver] reconcile fetch failed: {e}")
        return

    this = next((r for r in rows if r["id"] == cluster_id), None)
    if not this or not this.get("centroid"):
        return
    this_cen = this["centroid"]
    if isinstance(this_cen, str):
        try: this_cen = json.loads(this_cen)
        except Exception: return

    for r in rows:
        if r["id"] == cluster_id:
            continue
        cen = r.get("centroid")
        if isinstance(cen, str):
            try: cen = json.loads(cen)
            except Exception: continue
        if not cen:
            continue
        if _cosine(this_cen, cen) >= CLUSTER_FLOOR:
            # Same "belongs to same concern" judge, applied cluster-to-cluster.
            verdict = _adjudicate(r["label"], [{"id": this["id"], "label": this["label"]}])
            if verdict:
                # Keep the one with more events as the survivor.
                keep, absorb = (this, r) if (this.get("event_count") or 0) >= (r.get("event_count") or 0) else (r, this)
                # Survivor id is the bigger cluster (fewer rows to repoint), but
                # the LABEL should be the more general concern name, not whichever
                # instance happened to arrive first.
                label = _general_label(keep["label"], absorb["label"])
                merge_clusters(user_id, keep["id"], absorb["id"], label)
                return keep["id"]


# What each side of the comparison is. Deliberately coarse — a long list
# invites the model to split hairs, and every type here earns its place by
# appearing in a rule below.
_TYPES = ("condition", "medication", "symptom", "treatment", "person",
          "place", "occupation", "work", "part_of_work", "cuisine", "dish",
          "activity", "feeling", "other")


def _classify_pair(mention: str, candidate: str) -> Optional[dict]:
    """What are these two things? No judgement about their relationship.

    One call, and the model is only asked things it is reliably good at.
    """
    prompt = f"""Two things someone might remember. Classify each.

A: "{mention}"
B: "{candidate}"

Reply with JSON only:
{{"a": {{"form": "named|kind", "type": "..."}},
  "b": {{"form": "named|kind", "type": "..."}},
  "treats": "..."}}

form:
  named  a particular thing — metformin, Anupamaa, Arjun, Sholay, Delhi,
         Janmashtami, idli
  kind   a class of things — health, television, music, films, dawai, khana,
         bhakti, expenses, sport

  The test is whether you could point at exactly one of it. "Dawai" is the
  word for medicine, so it is a kind. "Metformin" is one drug, so it is named.

type: {" | ".join(_TYPES)}
  part_of_work  a song, an episode, a character — a piece of a larger work
  occupation    doctor, teacher — what someone does
  feeling       khushi, thakan, an empty house

treats: only when A is a medication — name the condition it is for, plainly
  ("diabetes", "blood pressure", "thyroid"). Otherwise "".

No prose."""

    try:
        from llm import ask
        raw = ask(prompt, max_tokens=200).replace("```json", "").replace("```", "")
        d = json.loads(raw.strip())
    except Exception as e:
        print(f"[Merge] classify failed: {e}")
        return None

    a, b = d.get("a") or {}, d.get("b") or {}
    if not (a.get("form") and b.get("form")):
        return None
    return {
        "a_form": str(a.get("form", "")).lower(),
        "a_type": str(a.get("type", "other")).lower(),
        "b_form": str(b.get("form", "")).lower(),
        "b_type": str(b.get("type", "other")).lower(),
        "treats": str(d.get("treats") or "").lower().strip(),
    }


def _should_merge(mention: str, candidate: str, c: dict) -> bool:
    """The rule. In code, so it cannot drift between domains.

    Every path that is not explicitly a merge is a refusal — an unlisted
    combination fragments rather than corrupting, and fragmentation is
    recoverable by a later mention.
    """
    a_form, a_type = c["a_form"], c["a_type"]
    b_form, b_type = c["b_form"], c["b_type"]

    # A name never becomes a class. This alone is four of the seven wrong
    # merges, and it needs no examples because it is structural: "diabetes"
    # into "health" is the same shape as "Kishore Kumar" into "music".
    # A category that is already one of her clusters IS a home — she has an
    # interest in cricket, so a match belongs to it, and "South Indian food"
    # is where idli goes. Refusing every kind cost twenty-three merges.
    #
    # What must not happen is a NAMED thing of the same type disappearing into
    # its own class: Kishore Kumar into music, Anupamaa into television,
    # diabetes into health. There the merge keeps the class and the name is
    # gone.
    if b_form == "kind":
        _SAME_KIND = {
            ("person", "person"), ("work", "work"), ("condition", "condition"),
            ("medication", "medication"), ("place", "place"),
            ("dish", "dish"), ("activity", "activity"),
        }
        if a_form == "named" and (a_type, b_type) in _SAME_KIND:
            return False
        # Only a genuine instance-of. The first attempt allowed anything
        # through and knee pain joined diabetes, because the classifier calls
        # diabetes a kind and knee pain a symptom — a pair that list happened
        # to permit.
        #
        # So: named things that are examples of the class, and nothing else.
        # A match is an instance of cricket, idli of South Indian food. A
        # condition is never an instance of another condition.
        return a_form == "named" and (a_type, b_type) in {
            ("work", "activity"),        # a match, of cricket
            ("part_of_work", "activity"),
            ("dish", "cuisine"),
            ("dish", "activity"),
            ("person", "activity"),      # a player, of cricket
            ("work", "work"),            # an episode named, of a serial
        }

    # A feeling is not part of anything. It should not have reached here —
    # the durable-fact gate drops them — but khushi joining Arjun would make
    # happiness a property of her son.
    if a_type == "feeling" or b_type == "feeling":
        return False

    # Siblings. Two conditions, two people, two films, two dishes: neither
    # contains the other, and the merge would keep the listed one.
    if a_form == "named" and b_form == "named" and a_type == b_type:
        return False

    # A work contains its parts. A song joins its film, an episode its serial.
    if a_type == "part_of_work" and b_type == "work":
        return True

    # A drug joins the condition it TREATS, and no other. Metformin reached
    # blood pressure because both are health and the vectors were close; the
    # code refuses it because metformin treats diabetes.
    if a_type == "medication" and b_type == "condition":
        treats = c.get("treats") or ""
        cand = candidate.lower()
        return bool(treats) and (treats in cand or cand in treats)

    # What surrounds a condition: the symptom, the treatment, the doctor.
    if a_type in ("symptom", "treatment", "occupation") and b_type == "condition":
        return True

    # What is known about a person: where they live, what they do. Three of
    # the six misses were this — Delhi, doctor and beta all failed to reach
    # Arjun, so facts about her son were not landing on her son.
    if b_type == "person" and a_type in ("place", "occupation", "activity"):
        return True

    # A dish joins its cuisine. Not the reverse, and not two dishes.
    if a_type == "dish" and b_type == "cuisine":
        return True

    return False


def _adjudicate_v2(label: str, candidates: List[dict]) -> Optional[dict]:
    """Same signature as _adjudicate. Classify, then decide.

    Candidates are tried in cosine order, so the closest plausible one wins
    and a merge is never chosen over a better-scoring alternative.
    """
    for cand in candidates:
        c = _classify_pair(label, cand.get("label", ""))
        if not c:
            continue
        if _should_merge(label, cand.get("label", ""), c):
            return cand
    return None

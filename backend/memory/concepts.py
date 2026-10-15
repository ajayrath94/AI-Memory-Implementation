"""
CONCEPTS — one thing, one row. The single answer to "is this the same thing?"

Twenty places decided it, eight ways: exact labels, case-insensitive labels,
substrings both ways, three cosine floors (0.84, 0.87, 0.62), and four model
prompts asking four different questions. The one most writers went through
asked whether a new name "BELONGS TO" an ongoing concern — so a medicine
merged into "blood pressure" and one cricket match into "cricket", and the
merge deleted the row. Belonging is a link. Sameness is identity. Only
identity merges.

THE QUESTION
Is this the same real-world thing said differently — another spelling, her
word and the English for it, a nickname, a translation? "ghutna" is "Knee
pain"; "bagwani" is "gardening"; "Kishore da" is "Kishore Kumar". Two things
of the same kind are two things: Lata is not Kishore, back pain is not knee
pain, and a bahu called Priya is not a padosan called Priya.

HOW
    1. the same label, ignoring case — one thing, no question asked
       (unless two people share it with different relations)
    2. otherwise the closest few by meaning, against each concept's own
       label, from a low floor (0.62): ghutna/knee pain sits at 0.695 and
       bagwani/gardening at 0.680, below the old 0.84-0.87 floors, which is
       why they were never even proposed
    3. the model picks the one it IS, or none

Every pillar at once. Filing by pillar was why the same thing under two
pillars was two things.

STATUS (decided 15 Oct)
    active    a live concept
    merged    the same as another; forwarded to it (attributes.merged_into)
    archived  known, not offered. It is still the thing: the next cold goes
              under the archived "Common cold" and stays archived. It is
              never shown as an interest and never brought back by a mention.
    dropped   as archived

MERGING
Soft, always. The absorbed row is marked merged with merged_into, and what
pointed at it is pointed at the survivor. Nothing is deleted, so a wrong
merge is undone by setting it back.

Never raises: a failure is "no match", and the caller makes a new concept.
A missed merge costs a duplicate; a wrong one puts one thing's life on
another.
"""
import json
import time
from typing import Dict, List, Optional

SAME_FLOOR = 0.62        # worth asking about, never enough on its own
MAX_CANDIDATES = 5
_POOL = 600

# label text -> its embedding. Labels repeat across every call; embedding
# each once per process is the difference between one call and two hundred.
_VEC: Dict[str, list] = {}
# (user, name, relation) -> (concept id or "", when)
_SEEN: Dict[tuple, tuple] = {}
_SEEN_TTL = 6 * 3600


def _db():
    from supabase_store import get_client
    return get_client()


def _attrs(r: dict) -> dict:
    a = (r or {}).get("attributes")
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except Exception:
            a = {}
    return a if isinstance(a, dict) else {}


def _status(r: dict) -> str:
    return (r or {}).get("status") or "active"


def known_not_offered(r: dict) -> bool:
    """Archived or dropped: recognised, holds history, never offered."""
    return _status(r) not in ("active", "merged")


def _embed(text: str) -> Optional[list]:
    t = (text or "").strip()
    if not t:
        return None
    if t in _VEC:
        return _VEC[t]
    try:
        from classifier.pillar_classifier import embed_text
        v = embed_text(t)
    except Exception as e:
        print(f"[Concepts] embed failed for {t!r}: {e}")
        v = None
    if v:
        if len(_VEC) > 5000:
            _VEC.clear()
        _VEC[t] = v
    return v


def _cos(a, b) -> float:
    try:
        from classifier.pillar_classifier import cosine_similarity
        return float(cosine_similarity(a, b))
    except Exception:
        return 0.0


_KIND_SENSE = {"concern": "about her own health",
               "person": "about a person in her life",
               "place": "about a place",
               "interest": "about something she likes or does"}
_EN: Dict[tuple, str] = {}


# Kinds and categories whose names are names — a person, a film, a song, a
# singer — are never translated. "Shubham" came back "Auspicious one",
# "Gadar" "Awesome" and "Hum Aapke Hain Koun" "You are my everything!".
_NAMES_KINDS = {"person"}
_NAMES_CATEGORIES = {"dekhna", "sangeet"}


def english(name: str, kind: str = "", category: str = "") -> str:
    """The plain English NAME of the same thing, for matching only — never
    shown to her. "sardi" about her health is "common cold"; "ghutna" is
    "knee pain"; "tinda" is "round gourd"; "bagwani" is "gardening".

    The language step: the embedding does not know "sardi" (it put it
    nearest "Arjun"), so her word alone could never find "Common cold".
    Searching by her word AND its English finds it in any of her languages,
    with no list of words anywhere. Names are not translated, and when the
    model is unsure it writes the word back — a missing translation costs a
    match; a wrong one ("Mediterranean food" -> "South Indian food") could
    make two things one.
    """
    n = (name or "").strip()
    if not n:
        return ""
    if (kind or "") in _NAMES_KINDS or (category or "") in _NAMES_CATEGORIES:
        return n
    key = (n.lower(), kind or "", category or "")
    if key in _EN:
        return _EN[key]
    what = {"concern": "something about her own health",
            "place": "a place",
            "interest": "something she likes or does"}.get(kind or "", "something in her life")
    cat = {"khana": " (a food or dish)", "bhakti": " (faith or worship)",
           "shauk": " (a hobby)"}.get(category or "", "")
    try:
        from llm import ask
        e = (ask(f"""Translate this NAME into English, for matching. It is the name of one
thing in an elderly Indian woman's memory: {what}{cat}.

Name: "{n}"

- Give the plain English name of the SAME thing, one to four words:
  sardi (health) -> common cold; ghutna (health) -> knee pain;
  tinda (food) -> round gourd; bagwani -> gardening; ककड़ी -> cucumber.
- A proper name stays exactly as written: a person, a film, a song, a show,
  a singer, a brand, a festival.
- Already English: write it back exactly.
- Never describe, interpret, praise or add feelings. Never swap it for a
  different thing of the same kind.
- If you are not sure, write the name back exactly.

Only the English name.""", max_tokens=16) or "").strip().strip('".')
    except Exception as ex:
        print(f"[Concepts] english failed for {n!r}: {ex}")
        e = ""
    e = e.splitlines()[0].strip() if e else ""
    if not e or len(e) > 40 or len(e.split()) > 5:
        e = n
    if len(_EN) > 5000:
        _EN.clear()
    _EN[key] = e
    return e


def _label_english(r: dict) -> str:
    """A concept's label in English, kept on the concept once worked out."""
    a = _attrs(r)
    if a.get("english"):
        return str(a["english"])
    e = english(str(r.get("label") or ""), r.get("kind") or "", a.get("category") or "")
    if e:
        a["english"] = e
        r["attributes"] = a
        try:
            _db().table("interest_clusters").update({"attributes": a}) \
                .eq("id", r["id"]).execute()
        except Exception:
            pass
    return e


def _vecs(*texts) -> list:
    out = []
    for t in texts:
        v = _embed(t) if t else None
        if v:
            out.append(v)
    return out


def _search(name: str, kind: str, pool: List[dict], embedding=None):
    """The closest few concepts by meaning: her word and its English, against
    each label and its English. Returns (candidates, closest label, score)."""
    gloss = english(name, kind)
    mine = _vecs(name, gloss if gloss and gloss.lower() != name.lower() else "")
    if embedding:
        mine = [embedding] + mine
    if not mine:
        return [], gloss, ("", 0.0)
    scored, best = [], ("", 0.0)
    for r in pool:
        lab = str(r.get("label") or "")
        le = _label_english(r)
        theirs = _vecs(lab, le if le and le.lower() != lab.lower() else "")
        if not theirs:
            continue
        sc = max(_cos(a, b) for a in mine for b in theirs)
        if sc > best[1]:
            best = (lab, sc)
        if sc >= SAME_FLOOR:
            scored.append((sc, r))
    scored.sort(key=lambda x: -x[0])
    cands, ids = [], set()
    for _s, r in scored:
        rr = r if _status(r) != "merged" else follow(r, pool)
        if not rr or rr["id"] in ids:
            continue
        ids.add(rr["id"])
        cands.append(rr)
        if len(cands) >= MAX_CANDIDATES:
            break
    return cands, gloss, best


def _pool(user_id: str, include_events: bool) -> List[dict]:
    try:
        rows = (_db().table("interest_clusters")
                .select("id,label,kind,pillar,status,attributes")
                .eq("user_id", user_id).limit(_POOL).execute()).data or []
    except Exception as e:
        print(f"[Concepts] pool read failed: {e}")
        return []
    if not include_events:
        rows = [r for r in rows if (r.get("kind") or "") != "event"]
    return rows


def follow(r: dict, pool: List[dict] = None) -> Optional[dict]:
    """Where a merged row went. A few hops at most."""
    by_id = {x["id"]: x for x in (pool or [])}
    seen = set()
    while r and _status(r) == "merged" and len(seen) < 5:
        seen.add(r["id"])
        to = _attrs(r).get("merged_into")
        if not to or to in seen:
            return None
        nxt = by_id.get(to)
        if nxt is None:
            try:
                got = (_db().table("interest_clusters")
                       .select("id,label,kind,pillar,status,attributes")
                       .eq("id", to).limit(1).execute()).data
                nxt = got[0] if got else None
            except Exception:
                nxt = None
        r = nxt
    return r if r and _status(r) != "merged" else None


def _out(r: dict) -> dict:
    return {"id": r["id"], "label": r.get("label"), "kind": r.get("kind"),
            "pillar": r.get("pillar"), "status": _status(r)}


def _relation(r: dict) -> str:
    return str(_attrs(r).get("relation") or "").strip().lower()


def _ask(name: str, relation: str, kind: str, cands: List[dict],
         gloss: str = "") -> Optional[int]:
    listing = "\n".join(
        f"{i + 1}. {c['label']}"
        + (f" ({c.get('kind')}" + (f', her "{_relation(c)}"' if _relation(c) else "") + ")"
           if c.get("kind") else "")
        for i, c in enumerate(cands))
    rel = f', whom she calls "{relation}"' if relation else ""
    # What she was talking about, in words: the bare kind ("concern") left
    # "ghutna" as a body part and "sardi" as the weather. Said about her own
    # health, ghutna is her knee trouble and sardi is a cold.
    kd = {"concern": " (she said it about her own health)",
          "person": " (a person in her life)",
          "place": " (a place)",
          "interest": " (something she likes or does)"}.get(kind or "", "")
    gl = (f' (probably "{gloss}" in English)' if gloss and gloss.lower() != name.lower() else "")
    prompt = f"""An elderly woman in India mentioned: "{name}"{gl}{kd}{rel}

Things already in her memory:
{listing}

Is "{name}" THE SAME real-world thing as one of these, said differently?

Same: another spelling, her word and the English for it, a translation, a
nickname or honorific, more or less wording for the identical thing.
"ghutne ka dard" is "Knee pain". "bagwani" is "Gardening". "Kishore da" is
"Kishore Kumar". "Priya ji" is "Priya".

Not the same:
- two things of the same kind: two singers, two films, two dishes, two
  illnesses. Lata is not Kishore Kumar; back pain is not knee pain.
- broader or narrower: "old songs" is not "Kishore Kumar"; arthritis is not
  knee pain; a knee is not knee pain.
- something that merely belongs with it: a medicine is not the illness it
  treats; one match is not "cricket"; a song is not its film.
- two different names are two people: Ramu is not Ramesh.
- the same name with a different relation is a different person: her bahu
  Priya is not her padosan Priya.

Read the word in the sense she used it. Said about her health, a body part
means the trouble with it ("ghutna" is her knee trouble, so "Knee pain"),
and a word with two meanings takes the one that fits ("sardi" about her
health is a cold, not the weather).

When unsure, it is not the same. A wrong match puts one thing's life on
another.

Answer with the number only, or NONE."""
    try:
        from llm import ask
        a = (ask(prompt, max_tokens=8) or "").strip().upper()
    except Exception as e:
        print(f"[Concepts] model failed: {e}")
        return None
    if not a or a.startswith("NONE"):
        return None
    digits = "".join(ch for ch in a.split()[0] if ch.isdigit())
    if not digits:
        return None
    n = int(digits)
    return n - 1 if 1 <= n <= len(cands) else None


def same_as(user_id: str, name: str, kind: str = "", relation: str = "",
            embedding: list = None, include_events: bool = False,
            exclude_ids=()) -> Optional[dict]:
    """The concept this name IS, or None.

    Returns {"id", "label", "kind", "pillar", "status"}. A merged match is
    followed to where it went; an archived one is returned as it is — known,
    and the caller decides (it is never revived by a mention).
    """
    name = (name or "").strip()
    if not name or not user_id:
        return None
    relation = (relation or "").strip().lower()
    key = (user_id, name.lower(), relation, bool(include_events))
    hit = _SEEN.get(key)
    if hit and time.time() - hit[1] < _SEEN_TTL:
        if not hit[0]:
            return None
        try:
            got = (_db().table("interest_clusters")
                   .select("id,label,kind,pillar,status,attributes")
                   .eq("id", hit[0]).limit(1).execute()).data
            if got:
                r = follow(got[0]) if _status(got[0]) == "merged" else got[0]
                if r:
                    return _out(r)
        except Exception:
            pass

    pool = [r for r in _pool(user_id, include_events) if r["id"] not in set(exclude_ids)]
    result = _decide(user_id, name, kind, relation, embedding, pool)
    _SEEN[key] = ((result or {}).get("id") or "", time.time())
    if len(_SEEN) > 5000:
        _SEEN.clear()
    return result


def _decide(user_id, name, kind, relation, embedding, pool) -> Optional[dict]:
    low = name.lower()

    # 1. The same label. One thing — unless two people share the name and
    #    are called different things, which only the model can settle.
    exact = [r for r in pool if str(r.get("label") or "").strip().lower() == low]
    for r in exact:
        rr = r if _status(r) != "merged" else follow(r, pool)
        if not rr:
            continue
        if relation and _relation(rr) and _relation(rr) != relation:
            continue
        return _out(rr)

    # 2. The closest few by meaning — her word and its English, against
    #    each label and its English.
    cands, gloss, best = _search(name, kind, pool, embedding)
    if not cands:
        print(f"[Concepts] {name!r} ({gloss or 'no English'}): nothing close enough "
              f"(closest {best[0]!r} at {round(best[1], 3)}, floor {SAME_FLOOR})")
        return None

    # 3. The model says which one it IS.
    i = _ask(name, relation, kind, cands, gloss)
    if i is None:
        print(f"[Concepts] {name!r} ({gloss}): none of {[c['label'] for c in cands]}")
        return None
    print(f"[Concepts] {name!r} is {cands[i]['label']!r}")
    return _out(cands[i])


def remember(user_id: str, name: str, concept_id: str, relation: str = "",
             include_events: bool = False):
    """A new concept was just made for this name: the next lookup finds it
    without asking again."""
    _SEEN[(user_id, (name or "").strip().lower(), (relation or "").strip().lower(),
           bool(include_events))] = (concept_id, time.time())


# ── about: for linking a mention or a day to a concept, never for merging ──

_ABOUT: Dict[tuple, tuple] = {}


def about(user_id: str, subject: str) -> Optional[dict]:
    """The concept this subject is ABOUT: the same thing, or a part, an
    instance or a piece of it. "Kishore Kumar ke gaane" is about Kishore
    Kumar; "sham ki walk" is about Evening walk.

    Looser than same_as on purpose, and only ever used to LINK a record
    (a day's mention, a day's tag) — never to merge two concepts. Archived
    concepts count: a day about her cold is about "Common cold".
    """
    subject = (subject or "").strip()
    if not subject or not user_id:
        return None
    same = same_as(user_id, subject)
    if same:
        return same
    key = (user_id, subject.lower())
    hit = _ABOUT.get(key)
    if hit and time.time() - hit[1] < _SEEN_TTL:
        return hit[0]

    pool = _pool(user_id, include_events=False)
    result = None
    cands, gloss, _best = _search(subject, "", pool) if pool else ([], "", ("", 0))
    if cands:
        listing = "\n".join(f"{i + 1}. {c['label']}" for i, c in enumerate(cands))
        _g = f' (probably "{gloss}" in English)' if gloss and gloss.lower() != subject.lower() else ""
        try:
            from llm import ask
            a = (ask(f"""An elderly woman talked about: "{subject}"{_g}

Things in her memory:
{listing}

Is what she talked about ABOUT one of these — the same thing, a part, an
instance or a piece of it, or something done for it? "Kishore Kumar ke
gaane" is about Kishore Kumar. "sham ki walk" is about Evening walk.
"ghutne ki maalish" is about Knee pain. A different thing of the same
kind is not: Lata is not about Kishore Kumar.

Answer with the number only, or NONE.""", max_tokens=8) or "").strip().upper()
            d = "".join(ch for ch in (a.split() or [""])[0] if ch.isdigit())
            if d and 1 <= int(d) <= len(cands):
                result = _out(cands[int(d) - 1])
        except Exception as e:
            print(f"[Concepts] about failed: {e}")
    _ABOUT[key] = (result, time.time())
    if len(_ABOUT) > 5000:
        _ABOUT.clear()
    return result


# ── merging: soft, and everything that pointed at it follows ────────────────

def merge(user_id: str, keep_id: str, absorb_id: str, why: str = "") -> bool:
    """absorb becomes a forwarding address to keep. Nothing is deleted."""
    if not keep_id or not absorb_id or keep_id == absorb_id:
        return False
    db = _db()
    try:
        rows = (db.table("interest_clusters")
                .select("id,label,status,attributes,strength,event_count")
                .in_("id", [keep_id, absorb_id]).execute()).data or []
        keep = next((r for r in rows if r["id"] == keep_id), None)
        absorb = next((r for r in rows if r["id"] == absorb_id), None)
        if not keep or not absorb:
            return False
        a = _attrs(absorb)
        a["merged_into"] = keep_id
        if why:
            a["merged_why"] = why[:200]
        db.table("interest_clusters").update(
            {"status": "merged", "attributes": a}).eq("id", absorb_id).execute()
        db.table("interest_clusters").update({
            "strength": round((keep.get("strength") or 0) + (absorb.get("strength") or 0), 4),
            "event_count": (keep.get("event_count") or 0) + (absorb.get("event_count") or 0),
        }).eq("id", keep_id).execute()
    except Exception as e:
        print(f"[Concepts] merge failed: {e}")
        return False

    # What pointed at it now points at the survivor. Each on its own: one
    # table missing must not stop the rest.
    for table, col in (("user_behavioral_events", "cluster_id"),
                       ("subject_mentions", "cluster_id"),
                       ("suggestions", "cluster_id"),
                       ("interest_clusters", "parent_id"),
                       ("health_episodes", "cluster_id")):
        try:
            db.table(table).update({col: keep_id}).eq(col, absorb_id).execute()
        except Exception:
            pass
    for col in ("from_id", "to_id"):
        try:
            db.table("entity_relations").update({col: keep_id}).eq(col, absorb_id).execute()
        except Exception:
            pass                         # an edge that already exists stays as it was
    for table in ("memory_stm", "memory_ltm"):
        try:
            rows = (db.table(table).select("*").eq("user_id", user_id)
                    .contains("tags", [absorb_id]).execute()).data or []
            for r in rows:
                tags = [keep_id if t == absorb_id else t for t in (r.get("tags") or [])]
                tags = list(dict.fromkeys(tags))
                key = "happened_on" if table == "memory_stm" else "period"
                db.table(table).update({"tags": tags}).eq("user_id", user_id) \
                    .eq(key, r[key]).execute()
        except Exception:
            pass
    for k in [k for k, v in _SEEN.items() if v[0] == absorb_id]:
        _SEEN[k] = (keep_id, time.time())
    print(f"[Concepts] {absorb.get('label')!r} merged into {keep.get('label')!r}")
    return True


def set_aside(cluster_id: str, why: str = "") -> bool:
    """Archive instead of deleting: known, not offered."""
    try:
        db = _db()
        got = (db.table("interest_clusters").select("attributes")
               .eq("id", cluster_id).limit(1).execute()).data
        a = _attrs(got[0]) if got else {}
        if why:
            a["archived_why"] = why[:200]
        db.table("interest_clusters").update(
            {"status": "archived", "attributes": a}).eq("id", cluster_id).execute()
        return True
    except Exception as e:
        print(f"[Concepts] set aside failed: {e}")
        return False

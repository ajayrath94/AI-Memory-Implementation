"""
Ambiguity — when a title could be two films, ask rather than guess.

"Gadar" is the 2001 film to anyone who has loved it for twenty years, and the
2023 sequel to OMDb, which ranks by relevance. Guessing wrong produced three
questions in a row about a film she has never seen — and the companion
discussing it confidently is worse than the companion not knowing.

Preferring the oldest match fixes this case and is a heuristic, not a rule: a
1962 film sharing the name would have won instead. The honest fix is the one
used everywhere else in this system — declared beats inferred. Ask her.

    "Gadar — Sunny Deol wali, ya nayi wali?"

Which is a natural question, doubles as conversation, and settles it for good.

HOW IT SITS IN THE FLOW
  enrich      finds two plausible matches -> stores candidates, enriches nothing
  probes      skip an unresolved cluster, since facts about the wrong film are
              worse than no facts
  curiosity   asks the disambiguation question in its own slot, because a
              question about which film she means IS curiosity with a purpose
  reply       her answer picks the candidate, enrichment proceeds

Until she answers, the cluster simply has no facts. That is the correct state:
we do not know which film she means, and pretending otherwise is the failure.
"""
import json
import os
import urllib.parse
import urllib.request
from typing import List, Optional, Dict

_OMDB = "https://www.omdbapi.com/"

# Two films of the same name a decade apart are a different film. Two a year
# apart are usually a re-release or bad data.
_YEAR_GAP = 10


def candidates(title: str, limit: int = 4) -> List[Dict]:
    """Plausible films for this title, oldest first.

    Only what a person might actually have meant: a sequel and its original
    qualify, twelve identically-named television episodes do not.
    """
    key = os.getenv("OMDB_API_KEY")
    if not key or not title:
        return []
    try:
        url = _OMDB + "?" + urllib.parse.urlencode(
            {"apikey": key, "s": title, "type": "movie"})
        with urllib.request.urlopen(url, timeout=10) as r:
            found = json.loads(r.read()).get("Search") or []
    except Exception as e:
        print(f"[Ambiguity] search failed for {title!r}: {e}")
        return []

    def norm(s):
        return "".join(ch for ch in (s or "").lower() if ch.isalnum())

    want = norm(title)

    seen, out = set(), []
    for m in found:
        yr = (m.get("Year") or "")[:4]
        imdb = m.get("imdbID")
        if not (yr.isdigit() and imdb) or imdb in seen:
            continue

        # OMDb matches any title CONTAINING the word, so searching "Sholay"
        # returned "Phool Aur Sholay" — a different film that happens to share
        # a word. What we want is a title that IS this thing, or this thing
        # with a subtitle or sequel number attached.
        got = norm(m.get("Title"))
        if not (got.startswith(want) or want.startswith(got)):
            continue

        seen.add(imdb)
        out.append({"title": m.get("Title"), "year": int(yr), "imdb": imdb})

    out.sort(key=lambda x: x["year"])
    out = out[:limit]

    # How many people have actually heard of each. Same title in different
    # decades finds real ambiguity — Gadar 2001 against Gadar 2 — and also
    # finds films nobody has heard of: searching "Sholay" returns a 1977 and a
    # 1984 film alongside the one everybody means. Asking whether she meant the
    # 1977 Sholay would make the companion seem obtuse.
    for cand in out:
        cand.update(_detail(cand["imdb"]))
    return out


def _detail(imdb_id: str) -> dict:
    """Votes and a lead actor. Votes decide whether a film is a real
    alternative; the actor is what makes the question answerable, since nobody
    remembers a release year and everybody remembers who was in it."""
    key = os.getenv("OMDB_API_KEY")
    if not (key and imdb_id):
        return {}
    try:
        url = _OMDB + "?" + urllib.parse.urlencode({"apikey": key, "i": imdb_id})
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.loads(r.read())
    except Exception:
        return {}

    votes = (d.get("imdbVotes") or "").replace(",", "")
    actors = [a.strip() for a in (d.get("Actors") or "").split(",") if a.strip()]
    return {
        "votes": int(votes) if votes.isdigit() else 0,
        "lead":  actors[0] if actors and actors[0] != "N/A" else "",
    }


# Below this nobody has heard of it, and it is not a film she might have meant.
_MIN_VOTES = 1000

# And a film with a hundredth of another's audience is not competing with it,
# whatever its raw count.
_RATIO = 0.05


def plausible(cands: List[Dict]) -> List[Dict]:
    """The ones someone might actually have meant."""
    known = [c for c in cands if c.get("votes", 0) >= _MIN_VOTES]
    if not known:
        return cands[:1]
    top = max(c["votes"] for c in known)
    return [c for c in known if c["votes"] >= top * _RATIO]


def is_ambiguous(cands: List[Dict]) -> bool:
    """Two films, both known, far enough apart in time to be different films.

    All three conditions matter. Same-decade matches are usually a re-release
    or bad data; obscure ones are not alternatives at all.
    """
    real = plausible(cands)
    if len(real) < 2:
        return False
    return (real[-1]["year"] - real[0]["year"]) >= _YEAR_GAP


def needs_asking(user_id: str) -> Optional[Dict]:
    """A cluster waiting on her to say which film she meant, or None."""
    try:
        from supabase_store import get_client
        rows = (get_client().table("interest_clusters")
                .select("id,label,attributes")
                .eq("user_id", user_id).eq("status", "active")
                .order("strength", desc=True).limit(30).execute()).data or []
    except Exception as e:
        print(f"[Ambiguity] read failed: {e}")
        return None

    for r in rows:
        attrs = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        amb = attrs.get("ambiguous")
        if amb and not attrs.get("resolved_imdb"):
            return {"cluster_id": r["id"], "label": r["label"],
                    "candidates": amb}
    return None


def ask_instruction(pending: Dict) -> str:
    """The question, phrased so she can answer it without knowing a year.

    Nobody remembers a release date. They remember who was in it, which is why
    the candidates carry a lead actor rather than only a year.
    """
    cands = pending["candidates"][:3]
    leads = {(c.get("lead") or "").strip() for c in cands}
    # Naming the actor only helps when the actors differ. Both Gadar films
    # star Sunny Deol, so "the one with Sunny Deol" distinguishes nothing —
    # and an instruction that cannot be followed is why the model reached for
    # something else entirely.
    distinct = len(leads - {""}) == len(cands)

    lines = []
    for c in cands:
        who = c.get("lead") or ""
        if distinct and who:
            lines.append(f"the one with {who} ({c['year']})")
        else:
            lines.append(f"the {c['year']} one")

    hint = ("Name the actors rather than the years: nobody remembers a release "
            "date, everyone remembers who was in it."
            if distinct else
            "They share a lead actor, so the year or old-versus-new is the only "
            "thing that separates them — ask it the way a person would: "
            "purani wali ya nayi wali.")

    return (
        "THIS OVERRIDES THE CONTEXT BELOW. Ask this one thing and nothing "
        "else.\n"
        f"They mentioned liking \"{pending['label']}\", and there is more than "
        f"one film by that name: " + ", or ".join(lines) + ".\n"
        "Ask which they mean — lightly, as if you had just realised, not as a "
        "form to fill in. " + hint
    )


def resolve(user_id: str, cluster_id: str, imdb_id: str) -> bool:
    """She said which one. Record it and let enrichment proceed."""
    try:
        from supabase_store import get_client
        db = get_client()
        rows = (db.table("interest_clusters").select("attributes")
                .eq("id", cluster_id).limit(1).execute()).data or []
        if not rows:
            return False
        attrs = rows[0].get("attributes")
        attrs = attrs if isinstance(attrs, dict) else {}
        attrs["resolved_imdb"] = imdb_id
        db.table("interest_clusters").update(
            {"attributes": attrs}).eq("id", cluster_id).execute()
        print(f"[Ambiguity] {cluster_id[:8]} resolved to {imdb_id}")
        return True
    except Exception as e:
        print(f"[Ambiguity] resolve failed: {e}")
        return False


def match_answer(pending: Dict, text: str) -> Optional[str]:
    """Read her reply against the candidates. Returns an imdbID or None.

    Deliberately forgiving: "Sunny Deol wali" and "purani" and "2001" should
    all work, because she is answering a question rather than filling a field.
    """
    t = (text or "").lower()
    if not t:
        return None

    cands = pending.get("candidates") or []
    for c in cands:
        if str(c.get("year")) in t:
            return c["imdb"]
        lead = (c.get("lead") or "").lower()
        if lead and any(part in t for part in lead.split() if len(part) > 3):
            return c["imdb"]

    # "purani", "old one", "the first one" — the oldest. "nayi", "new" — the
    # newest. These are how people actually answer.
    older = ("purani", "puran", "old", "pehli", "first", "original")
    newer = ("nayi", "naya", "new", "recent", "latest", "doosri", "second")
    if any(w in t for w in older):
        return cands[0]["imdb"] if cands else None
    if any(w in t for w in newer):
        return cands[-1]["imdb"] if cands else None
    return None

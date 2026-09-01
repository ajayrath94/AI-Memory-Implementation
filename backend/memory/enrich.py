"""
ENRICH — turning a name into something with parts.

"Sholay" is a label with a score. There is nowhere to go from it, so every offer
is either the same thing again or something unrelated, and a decline teaches
only that this one label is less wanted.

With parts there are directions:

    Sholay ──cast──→ Dharmendra ──→ his other films
           ──music──→ R.D. Burman ──→ his other songs
           ──era────→ 1975 ──→ that decade

A decline then says something about the DIRECTION rather than the thing. Someone
who turns down another Dharmendra film has not cooled on Sholay; they have said
cast is not their axis, and music might still be.

WHERE FACTS COME FROM, AND WHAT MAY BE SAID
  OMDb    films: cast, director, year, genre. Checked against three Bollywood
          titles and correct on all three. Verified — may be stated aloud.
  model   music and food. No API comes close on Indian material: it places
          undhiyu in Gujarat in winter and khichdi as recovery food, which
          Spoonacular and TheMealDB cannot (TheMealDB returns zero Indian
          dishes). Inferred — may CHOOSE an offer, must not be asserted.

That distinction is the whole safety story here. These are films and singers the
person knows intimately; a wrong composer stated as fact makes the companion
someone who talks nonsense about the thing they love. Using an uncertain fact to
pick a song costs nothing if it is wrong — the worst case is a song they do not
love.

NEVER ENRICHED
  bhakti  Inferring the particulars of someone's faith is the same overreach as
          reading Hinduism into "namaste", which the extractor did eight times.
  shauk   Gardening has no cast.
"""
import os
import json
import urllib.parse
import urllib.request
import re
from datetime import datetime, timezone
from typing import Optional, Dict, List

# Which classes have anything to decompose. From the design: the five
# user-facing categories collapse into a few classes that share machinery.
_ENRICHABLE = {"sangeet", "dekhna", "khana"}

_OMDB = "https://www.omdbapi.com/"


# ── verified: OMDb ────────────────────────────────────────────────────────────

def _omdb_fields(d: dict) -> Optional[dict]:
    """OMDb's response to our field names. Shared, because the same mapping is
    needed whether we looked the film up by title or by the id she chose."""
    # OMDb answers "False" as a string, and "N/A" for anything it lacks.
    if str(d.get("Response")) != "True":
        return None

    def clean(v):
        v = (v or "").strip()
        return "" if v in ("N/A", "") else v

    def split(v):
        return [x.strip() for x in clean(v).split(",") if x.strip()]

    facts = {}
    if clean(d.get("Actors")):   facts["cast"]     = split(d.get("Actors"))
    if clean(d.get("Director")): facts["director"] = clean(d.get("Director"))
    if clean(d.get("Genre")):    facts["genre"]    = split(d.get("Genre"))
    if clean(d.get("Year")):     facts["year"]     = clean(d.get("Year"))
    if clean(d.get("Language")): facts["language"] = split(d.get("Language"))
    # The canonical title, so Wikipedia is searched for the film she chose
    # rather than the ambiguous label she typed.
    if clean(d.get("Title")):    facts["omdb_title"] = clean(d.get("Title"))
    return facts or None


def _omdb_by_id(imdb_id: str) -> Optional[dict]:
    """The exact film, once she has said which one."""
    key = os.getenv("OMDB_API_KEY")
    if not (key and imdb_id):
        return None
    try:
        url = _OMDB + "?" + urllib.parse.urlencode({"apikey": key, "i": imdb_id})
        with urllib.request.urlopen(url, timeout=10) as r:
            return _omdb_fields(json.loads(r.read()))
    except Exception as e:
        print(f"[Enrich] omdb id lookup failed for {imdb_id}: {e}")
        return None


def _omdb(title: str) -> Optional[dict]:
    key = os.getenv("OMDB_API_KEY")
    if not key or not title:
        return None
    try:
        # Search first, then fetch. A direct lookup returns whatever OMDb ranks
        # highest, which for "Gadar" is the 2023 sequel — so someone who has
        # loved the 2001 film for twenty years would have been asked three
        # questions about a film she has never seen.
        #
        # The oldest plausible match wins. For people in their sixties and
        # seventies a bare title almost always means the film from their youth,
        # not last year's remake. That is a prior rather than a certainty, and
        # it is right far more often than "first result".
        s_url = _OMDB + "?" + urllib.parse.urlencode(
            {"apikey": key, "s": title, "type": "movie"})
        with urllib.request.urlopen(s_url, timeout=10) as r:
            found = json.loads(r.read()).get("Search") or []

        best = None
        for m in found:
            yr = (m.get("Year") or "")[:4]
            if not yr.isdigit():
                continue
            if best is None or int(yr) < int(best[0]):
                best = (yr, m.get("imdbID"))

        q = {"apikey": key}
        if best and best[1]:
            q["i"] = best[1]
        else:
            q["t"] = title

        url = _OMDB + "?" + urllib.parse.urlencode(q)
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(f"[Enrich] omdb failed for {title!r}: {e}")
        return None

    return _omdb_fields(d)


# ── inferred: the model ───────────────────────────────────────────────────────

_PROMPTS = {
    "sangeet": """This is a singer, composer or piece of music from India: "{name}"

Return JSON only, no prose, no markdown fence:
{{"kind": "artist|song|composer", "era": "", "language": "",
  "composers": [], "films": [], "similar": []}}

similar: up to three artists someone who likes this would plausibly also like.
films: up to three films this artist is strongly associated with.
Leave a field as an empty string or list if you are not confident.""",

    "khana": """This is an Indian dish or cuisine: "{name}"

Return JSON only, no prose, no markdown fence:
{{"is_cuisine": true|false, "region": "", "ingredients": [], "occasion": "",
  "season": "", "meal": "breakfast|lunch|dinner|snack|any", "dishes": []}}

If it is a CUISINE rather than a single dish, set is_cuisine true and name up
to three defining dishes in "dishes", leaving ingredients empty.
"meal" matters: it decides when this can sensibly be suggested.
Leave a field empty if you are not confident.""",

    "dekhna": """This is a film or show, probably Indian: "{name}"

Return JSON only, no prose, no markdown fence:
{{"music": "", "themes": [], "mood": ""}}

music: the music director, if you are confident. OMDb supplies cast and
director separately, so only add what it cannot.
Leave a field empty if you are not confident.""",
}


def _model(category: str, name: str) -> Optional[dict]:
    prompt = _PROMPTS.get(category)
    if not prompt:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=400,
            messages=[{"role": "user", "content": prompt.format(name=name)}])
        text = (resp.content[0].text or "").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        got = json.loads(text)
    except Exception as e:
        print(f"[Enrich] model failed for {name!r}: {e}")
        return None

    # Empty strings and lists are the model saying it does not know, which is
    # what the prompt asked for. Keeping them would make an unknown look like
    # a fact.
    return {k: v for k, v in got.items() if v not in ("", [], None)} or None


# ── the thing itself ──────────────────────────────────────────────────────────

def enrich_cluster(user_id: str, cluster_id: str, force: bool = False) -> Optional[dict]:
    """
    Fill in what a cluster is made of. Returns the facts written, or None.

    Runs once per cluster. Re-enriching costs a call and changes nothing, so
    an already-enriched cluster is skipped unless forced.
    """
    try:
        from supabase_store import get_client
        db = get_client()
        rows = (db.table("interest_clusters").select("id,label,attributes")
                .eq("id", cluster_id).limit(1).execute()).data or []
    except Exception as e:
        print(f"[Enrich] read failed: {e}")
        return None
    if not rows:
        return None

    row   = rows[0]
    attrs = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
    cat   = attrs.get("category") or ""
    name  = row.get("label") or ""

    if cat not in _ENRICHABLE or not name:
        return None
    if attrs.get("facts") and not force:
        return attrs["facts"]

    facts: Dict[str, dict] = {}

    # Verified first, so anything the model later claims about the same field
    # loses to a real source.
    if cat == "dekhna":
        # Which film does she mean? Preferring the oldest match fixed Gadar and
        # is a heuristic, not a rule. When two well-known films share a title,
        # facts about the wrong one are worse than no facts — so this stores
        # the choice and waits for her to make it.
        if not attrs.get("resolved_imdb"):
            try:
                from memory.ambiguity import candidates, is_ambiguous, plausible
                cands = candidates(name)
                if is_ambiguous(cands):
                    attrs["ambiguous"] = plausible(cands)
                    db.table("interest_clusters").update(
                        {"attributes": attrs}).eq("id", cluster_id).execute()
                    print(f"[Enrich] {name!r} is ambiguous — asking before enriching")
                    return None
            except Exception as e:
                print(f"[Enrich] ambiguity check failed: {e}")

        # By the film she named, if she has told us which one. Storing her
        # answer and then searching afresh gave 2001 from OMDb and the 2023
        # sequel's composer from Wikipedia — facts from two different films in
        # the same record.
        chosen = attrs.get("resolved_imdb")
        verified = (_omdb_by_id(chosen) if chosen else _omdb(name)) or {}
        year = str(verified.get("year") or "")[:4]
        # Wikipedia second, and it wins on any shared field: OMDb has no music
        # director at all, which is the field this was added for.
        try:
            wiki = infobox(verified.get("omdb_title") or name, year) or {}
        except Exception as e:
            print(f"[Enrich] wiki failed for {name!r}: {e}")
            wiki = {}
        verified.update(wiki)
        if verified:
            facts["verified"] = verified

    inferred = _model(cat, name)
    if inferred:
        facts["inferred"] = inferred

    if not facts:
        return None

    attrs["facts"] = facts
    attrs["enriched_at"] = datetime.now(timezone.utc).isoformat()

    try:
        db.table("interest_clusters").update(
            {"attributes": attrs}).eq("id", cluster_id).execute()
    except Exception as e:
        print(f"[Enrich] write failed: {e}")
        return None

    got = list((facts.get("verified") or {}).keys()) + \
          list((facts.get("inferred") or {}).keys())
    print(f"[Enrich] {name!r} ({cat}) -> {', '.join(got)}")
    return facts


def enrich_user(user_id: str, limit: int = 10) -> int:
    """Enrich everything of this person's that has parts and has not been done.

    Bounded because it is one API call each and a new user can declare a dozen
    interests in a minute.
    """
    try:
        from supabase_store import get_client
        rows = (get_client().table("interest_clusters")
                .select("id,label,attributes")
                .eq("user_id", user_id).eq("status", "active")
                .order("strength", desc=True).limit(60).execute()).data or []
    except Exception as e:
        print(f"[Enrich] user read failed: {e}")
        return 0

    done = 0
    for r in rows:
        if done >= limit:
            break
        a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        if (a.get("category") in _ENRICHABLE) and not a.get("facts"):
            if enrich_cluster(user_id, r["id"]):
                done += 1
    return done


def stateable(facts: Optional[dict]) -> dict:
    """Only what came from a real source, for anything that will be SAID.

    A composer may use inferred facts to choose what to offer and must not
    assert them. This is the seam that enforces it.
    """
    return (facts or {}).get("verified") or {}


def usable(facts: Optional[dict]) -> dict:
    """Everything, verified and inferred, for CHOOSING. Being wrong here costs
    a song they do not love, which is a different order of mistake."""
    f = facts or {}
    return {**(f.get("inferred") or {}), **(f.get("verified") or {})}


# ── verified: Wikipedia infobox ───────────────────────────────────────────────
# Added because the model got the music director wrong on all three films tried
# — S.D. for R.D. Burman, a singer named as a composer, and a composer who died
# before the film was made. The infobox has all three right, and music is the
# axis most likely to matter here.

_API = "https://en.wikipedia.org/w/api.php"
# Wikipedia asks for a real identifier rather than a library default.
_UA = "NancyAI/1.0 (eldercare companion; contact via app)"

# Only fields worth having. The infobox also carries budget, runtime,
# cinematography and a dozen others that no offer would ever use.
_WANTED = {
    "music":     "music",       # the reason this exists
    "director":  "director",
    "starring":  "cast",
    "producer":  "producer",
    "writer":    "writer",
    "language":  "language",
    "country":   "country",
    "gross":     "gross",       # "highest-grossing film of 1975" is the kind of
                                # surprising fact that makes an offer land
}


def _get(params: dict) -> dict:
    url = _API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


def _resolve_title(name: str, year: str = "") -> Optional[str]:
    """Find the real article title.

    "Gadar" is a disambiguation page and searching it returned "Gadar 2" — the
    2023 sequel, not the film she named. Silently returning facts about the
    wrong film is worse than returning none, so the year from OMDb is used to
    disambiguate when there is one.
    """
    try:
        query = f"{name} {year} film".strip() if year else f"{name} film"
        d = _get({"action": "query", "list": "search",
                  "srsearch": query, "srlimit": 3})
        hits = ((d.get("query") or {}).get("search") or [])
        return hits[0]["title"] if hits else None
    except Exception as e:
        print(f"[Wiki] search failed for {name!r}: {e}")
        return None


def _wikitext(title: str) -> str:
    try:
        d = _get({"action": "query", "prop": "revisions", "rvprop": "content",
                  "rvslots": "main", "titles": title})
        for p in ((d.get("query") or {}).get("pages") or {}).values():
            revs = p.get("revisions") or []
            if revs:
                return revs[0]["slots"]["main"]["*"]
    except Exception as e:
        print(f"[Wiki] fetch failed for {title!r}: {e}")
    return ""


_LINK   = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")   # [[R. D. Burman]]
_TMPL   = re.compile(r"\{\{[^{}]*\}\}")                    # {{Plainlist|...}}
_REF    = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.S)
_TAGS   = re.compile(r"<[^>]+>")
_FIELD  = re.compile(r"^\|\s*([a-z_ ]+?)\s*=\s*(.*)$", re.I)


def _clean(value: str) -> List[str]:
    """Wikitext to plain names.

    Infobox values are messy in a predictable way — wiki links, citation
    templates, HTML line breaks, footnotes — so this strips rather than parses.
    """
    v = _REF.sub("", value)
    # Strip template braces without removing what is inside them. Sholay's cast
    # is a {{Plainlist|...}} wrapping the names, and a regex that removes whole
    # templates took the names with it — leaving "{{Plainlist" as the value.
    v = v.replace("{{Plainlist", "").replace("{{plainlist", "")
    v = v.replace("{{ubl", "").replace("{{unbulleted list", "")
    v = _TMPL.sub(" ", v)          # anything still nested and unwanted
    v = v.replace("{{", " ").replace("}}", " ").replace("|", ",")
    v = v.replace("<br />", ",").replace("<br/>", ",").replace("<br>", ",")
    v = _LINK.sub(r"\1", v)
    v = _TAGS.sub(" ", v)
    v = v.replace("'''", "").replace("''", "").replace("*", ",")
    parts = [p.strip(" ,.|") for p in v.split(",")]
    # Some infoboxes label their sub-parts — "Score: Uttam Singh, Songs: Uttam
    # Singh" — and taking the first fragment gave music="Score:". Drop anything
    # that is a label rather than a name.
    out = []
    for p in parts:
        if not p or len(p) >= 60:
            continue
        if p.endswith(":"):
            continue
        if ":" in p:
            p = p.split(":", 1)[1].strip()
        # Wikipedia disambiguates in the title — "Amjad Khan (actor)", "Anil
        # Sharma (director)" — and that suffix has no business in a sentence
        # spoken to someone.
        p = re.sub(r"\s*\([^)]*\)$", "", p).strip()
        if p:
            out.append(p)
    return out[:6]


def infobox(name: str, year: str = "") -> Optional[Dict]:
    """Verified facts from the infobox, or None.

    Everything here may be STATED in a message — unlike model output, which may
    only choose what to offer.
    """
    title = _resolve_title(name, year)
    if not title:
        return None

    text = _wikitext(title)
    if not text:
        return None

    facts: Dict[str, object] = {}
    # The infobox sits at the top. Reading the first 150 lines avoids parsing
    # 120KB of prose for four fields.
    # Infobox values run over several lines. Sholay's cast is
    # "| starring = {{Plainlist|" followed by one name per line, so reading
    # line by line saw the opening brace and none of the names — which is why
    # the cast came from OMDb's top three instead, and Hema Malini went
    # missing from a film she is rather central to.
    fields, key, buf = [], None, []
    for line in text.split("\n")[:200]:
        s = line.strip()
        m = _FIELD.match(s)
        if m:
            if key:
                fields.append((key, " ".join(buf)))
            key = m.group(1).strip().lower().replace(" ", "_")
            buf = [m.group(2)]
        elif key and not s.startswith("}}") and s not in ("", "|"):
            buf.append(s)
        elif s.startswith("}}") and key:
            fields.append((key, " ".join(buf)))
            key, buf = None, []
    if key:
        fields.append((key, " ".join(buf)))

    for key, raw in fields:
        if key not in _WANTED:
            continue
        vals = _clean(raw)
        if not vals:
            continue
        out_key = _WANTED[key]
        facts[out_key] = vals[0] if out_key in ("music", "director", "gross") else vals

    if facts:
        facts["wikipedia_title"] = title
        print(f"[Wiki] {name!r} -> {title!r}: {', '.join(k for k in facts if k != 'wikipedia_title')}")
    return facts or None

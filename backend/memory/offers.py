"""
THE OFFER PATH — only ever something she does not already have.

Two paths, and keeping them apart is the whole design.

    the cluster path   offers what is hers. Kishore Kumar, South Indian
                       food, Sholay — raised again when it has been a
                       while. suggestions.py does this.

    the offer path     shows her the next thing. And anything it manages to
                       introduce STOPS being its business: once Lata is a
                       cluster, the cluster path will raise her naturally
                       with "bahut din se Lata nahi suni".

So this has a receding frontier. It can never repeat itself, because its
own successes leave its territory — which is what makes it read as curious
rather than as a catalogue.

WHY IT MATTERS THAT IT IS SEPARATE
Three of five messages one day mentioned Kishore Kumar, and none of them
came through an offer path at all. He is her strongest cluster, so he is in
the memory block and the interests block and the summary, and a composer
told it may mention something she likes reaches for him every time.

A thing she already loves is not an offer. It is a reminder, and the
cluster path is where reminders belong.

HOW IT CHOOSES
Six steps, and five of them are subtraction:

    what is hers           her clusters
    expand                 one step out, from adjacent()
    drop what is hers      the frontier
    drop what she refused  a clear no is permanent; silence is not a no
    drop what does not fit the window — a recipe after lunch is no use
    and what is left, nearest to something she loves

WHAT IS RECORDED
Not offered-and-clicked. The circumstances: which window, what hour, what
kind of day it had been, what it was expanded from. In a month that says
whether new things land in the afternoon and not at breakfast, or whether
she takes up music and never films.
"""
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

# A clear no is permanent. Silence is not a no — she answers two messages a
# day, and treating that as rejection would empty the world.
REFUSED = ("declined",)

# How far out to look before the connection is too thin to say "because of".
RINGS = 2


@dataclass
class Offer:
    what: str                    # "Lag Ja Gale by Lata Mangeshkar"
    because: str = ""            # "Kishore Kumar"
    when: str = "anytime"
    category: str = ""
    cluster_id: Optional[str] = None
    artefact: Optional[Dict] = None
    why_now: str = ""            # why this one suits this moment

    def __str__(self) -> str:
        s = self.what
        if self.because:
            s += f" (because of {self.because})"
        return s + f" [{self.when}]"


def _db():
    from supabase_store import get_client
    return get_client()


def hers(user_id: str) -> Dict[str, Dict]:
    """Everything she already has, by lowercase label.

    The frontier. The offer path may not cross back over it.
    """
    out = {}
    try:
        rows = (_db().table("interest_clusters")
                .select("id,label,attributes,strength")
                .eq("user_id", user_id).eq("status", "active")
                .eq("kind", "interest").limit(100).execute()).data or []
        for r in rows:
            a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
            out[str(r["label"]).strip().lower()] = {
                "id": r.get("id"), "label": r["label"],
                "category": a.get("category") or "",
                "strength": float(r.get("strength") or 0),
            }
    except Exception as e:
        print(f"[Offers] clusters read failed: {e}")
    return out


def _refused(user_id: str) -> set:
    """What she has said no to. Permanent.

    Not what she ignored — she replies to two messages a day, and reading
    silence as rejection would empty the world in a fortnight.
    """
    try:
        rows = (_db().table("suggestions").select("label,reaction")
                .eq("user_id", user_id).limit(200).execute()).data or []
        return {str(r.get("label") or "").strip().lower()
                for r in rows if r.get("reaction") in REFUSED}
    except Exception as e:
        print(f"[Offers] refusals read failed: {e}")
        return set()


def _recently_offered(user_id: str, days: int = 21) -> set:
    """Shown to her lately. Not refused — just not again yet."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        rows = (_db().table("suggestions").select("label")
                .eq("user_id", user_id).gte("created_at", since)
                .limit(100).execute()).data or []
        return {str(r.get("label") or "").strip().lower() for r in rows}
    except Exception:
        return set()


def _on_her_schedule(user_id: str) -> set:
    """Her routine and her observances, which are not interests.

    "walk" and "Navratri" are both clusters and both are things she DOES.
    Expanding them produces a shopping list or a liturgy.
    """
    out = set()
    try:
        from memory.day import events
        for e in events(user_id) or []:
            lab = str(e.get("label") or "").strip().lower()
            if lab:
                out.add(lab)
    except Exception:
        pass
    try:
        from memory.observances import all_for
        for r in all_for(user_id):
            v = str(r.get("value") or "").strip().lower()
            if v:
                out.add(v)
    except Exception:
        pass
    return out


def _artist(what: str) -> str:
    """Whoever comes after "by". "" when there is no by.

    An expansion is "<song> by <artist>", so the artist is a clean split
    rather than a substring search — which is what made "chicken" match
    "padosan" when this was tried the other way.
    """
    low = (what or "").lower()
    if " by " not in low:
        return ""
    return low.rsplit(" by ", 1)[1].strip().strip('"').strip()


def _artists(what: str) -> list:
    """Everyone after "by". A duet names two.

    "Sholay Ke Geet by Kishore Kumar and Lata Mangeshkar" went out to a
    woman whose strongest interest is Kishore Kumar, because the whole
    string after "by" was taken as one name.
    """
    a = _artist(what)
    if not a:
        return []
    parts = a.replace(" & ", " and ").replace(",", " and ").split(" and ")
    return [p.strip() for p in parts if p.strip()]


def _title(what: str) -> str:
    """The song itself, without the artist and without the quotes.

    "Abhi Na Jao Chhod Kar" came back three times in a fortnight — by
    Mohammad Rafi, by Mohammad Rafi and Asha Bhosle, and spelt Jaao. Three
    strings, one song, and an exact-match dedup lets all three through.
    """
    low = (what or "").lower()
    if " by " in low:
        low = low.rsplit(" by ", 1)[0]
    return low.strip().strip('"').strip("'").strip()


def _fits(when: str, window, now_min: Optional[int]) -> bool:
    """Does this belong in the stretch she is in?

    A recipe an hour after lunch is no use; a film needs an evening and two
    hours; gardening is a morning thing.
    """
    if when == "anytime":
        return True
    if now_min is None:
        return True

    hour = now_min // 60
    if when == "morning":
        return 5 <= hour < 11
    if when == "evening":
        # and long enough to actually watch something
        return hour >= 16 and (window is None or window.minutes >= 90)
    if when == "before_meal":
        # Useful in the run-up to a meal, useless after it. The window's
        # own end is the meal, which is what makes this answerable.
        if window is None:
            return True
        # And the window must actually end at a meal. The last stretch of
        # her day ends at bedtime, so idli sambar was offered at nine at
        # night, an hour after dinner.
        # By the kind of what ends the window, not by its name: "dopahar ka
        # khana" contains neither "lunch" nor "meal", so for anyone whose
        # meals are not named in English no food offer ever fitted.
        if getattr(window, "before_kind", "") != "meal" and \
                "meal" not in (window.before or "").lower() and \
                (window.before or "").lower() not in ("breakfast", "lunch", "dinner"):
            return False
        return (window.ends - now_min) <= 90
    return True


# Categories whose interests are served as named and never expanded.
_FULFIL_ONLY = {"bhakti"}


_LANGS: Dict[str, set] = {}


def _their_languages(user_id: str, mine: Dict[str, Dict]) -> set:
    """The languages their songs, films and prayers are in. Worked out once
    per process from what they already love and where they live, so a
    Carnatic listener keeps Sanskrit and Telugu kritis and loses Hindi
    bhajans, and a Bengali reader in English keeps Bengali.

    Empty when it cannot be worked out, which turns the filter off rather
    than filtering everything."""
    if user_id in _LANGS:
        return _LANGS[user_id]
    out: set = set()
    try:
        from memory.declared import get_declared
        from llm import ask
        import json as _j
        d = get_declared(user_id)
        loves = ", ".join(v["label"] for v in sorted(
            mine.values(), key=lambda v: -v["strength"])[:8])
        raw = (ask(f"""Someone lives in {d.place.home or 'India'}, speaks {d.language.pref},
and loves: {loves}.

Which languages are the songs, films and prayers they love in? Include the
languages of the things above, and the language of where they live. Not
languages they would not understand or would not choose.

JSON only: {{"langs": ["tamil", "sanskrit"]}}  (lowercase, one word each)""",
                   max_tokens=60) or "")
        raw = raw.replace("```json", "").replace("```", "")
        got = _j.loads(raw[raw.find("{"):raw.rfind("}") + 1]).get("langs") or []
        out = {str(x).strip().lower() for x in got if str(x).strip()}
        if out and (d.language.pref or "").lower() == "english":
            out.add("english")
    except Exception as e:
        print(f"[Offers] languages read failed, not filtering: {e}")
        out = set()
    print(f"[Offers] {user_id}: their languages: {sorted(out) or '(unknown)'}")
    _LANGS[user_id] = out
    return out


def candidates(user_id: str, window=None, now_min: Optional[int] = None,
               rings: int = RINGS) -> List[Offer]:
    """Everything she could be shown, nearest first.

    Usually a handful. Empty when she has no interests yet, or when
    everything within reach is already hers — which is a good problem.
    """
    mine = hers(user_id)
    skip = set(mine.keys()) | _refused(user_id) | _recently_offered(user_id)
    routine = _on_her_schedule(user_id)
    # The same song reaches her under three spellings otherwise.
    skip_titles = {_title(s) for s in skip if _title(s)}

    # Strongest first: an expansion from something she loves is a better
    # offer than one from something she mentioned once.
    # Strongest first, and a thing she adopted this week is a poor reason:
    # "because of Kishore Kumar" is a connection she would recognise, and
    # "because of a song you heard on Tuesday" is not.
    # Faith is fulfil-only: serve what she named, never expand around it.
    # artefacts.py says so and has no fetcher for it on purpose, but this
    # path expanded it anyway, and a Tamil woman whose devotion is the
    # Suprabhatam was offered a Hindustani thumri "because of Suprabhatam".
    seeds = sorted(
        [v for k, v in mine.items()
         if k not in routine and v["strength"] >= 0.5
         and (v.get("category") or "") not in _FULFIL_ONLY],
        key=lambda v: -v["strength"])[:8]

    from memory.artefacts import adjacent

    out: List[Offer] = []
    seen = set()

    # Ring by ring. Five interests expanding three or four each is about
    # twenty things, and a fortnight of offers exhausts them — six of
    # fourteen days came back with nothing to say.
    #
    # So when the first ring runs out, expand from the expansions: Lata's
    # songs lead to Madan Mohan, and outward. The "because" stays the
    # original interest, because "because of Kishore Kumar" is a reason she
    # would recognise and "because of a song you were offered last week" is
    # not.
    frontier = [(s["label"], s) for s in seeds]
    langs = _their_languages(user_id, mine)

    for ring_no in range(max(1, rings)):
        next_frontier = []
        for label, seed in frontier:
            try:
                ring = adjacent(user_id, label, seed["category"]) or []
            except Exception as e:
                print(f"[Offers] expand failed for {label}: {e}")
                continue

            for item in ring:
                what = str(item.get("what") or "").strip()
                low = what.lower()
                if not what or low in seen:
                    continue
                seen.add(low)
                next_frontier.append((what, seed))

                # Already hers, already refused, already offered — by
                # the song or by the singer.
                #
                # Two rings out, the expansion came back to where it
                # started: "Pyar Diwana Hota Hai by Kishore Kumar" offered
                # to a woman whose strongest interest is Kishore Kumar.
                if low in skip:
                    continue
                if _title(what) in skip_titles:
                    continue
                if any(a in skip for a in _artists(what)):
                    continue
                if not _fits(item.get("when") or "anytime", window, now_min):
                    continue

                # Its own kind where the generator gave one, the interest's
                # where it did not (older cached rings).
                kind = item.get("kind") or seed["category"]

                # In a language they live in. The generator is asked for
                # this and twice in one day returned a Hindi Hanuman Chalisa
                # for a Tamil Carnatic listener, so it is checked here too.
                lang = str(item.get("lang") or "").lower()
                if lang and lang != "none" and langs and lang not in langs:
                    print(f"[Offers] {user_id}: not offering {what!r} "
                          f"({lang}; theirs: {', '.join(sorted(langs))})")
                    continue

                # A song names the song. "Jagjit Singh" and "Farida Khanum"
                # came through alone, the search found an hour-long "Best
                # Of" compilation, and that is not an offer to someone of
                # seventy. The generator is told this; this makes sure.
                if kind == "sangeet" and " by " not in low:
                    continue

                out.append(Offer(
                    what=what,
                    because=seed["label"],
                    when=item.get("when") or "anytime",
                    category=kind,
                    cluster_id=seed.get("id"),
                ))

        # Only go further out when the near ring has little left — the
        # second ring is a thinner connection and should not crowd out the
        # first.
        if len(out) >= 6:
            break
        frontier = next_frontier[:6]

    return out


def _offered_kinds_today(user_id: str) -> Dict[str, int]:
    """How many offers of each category have reached her today.

    Read from suggestions by cluster, then mapped to the cluster's category,
    since the category is not stored on the suggestion itself.
    """
    out: Dict[str, int] = {}
    try:
        rows = (_db().table("suggestions").select("cluster_id")
                .eq("user_id", user_id).eq("intent", "recommendation")
                .gte("created_at", date.today().isoformat())
                .limit(50).execute()).data or []
        if not rows:
            return out
        by_id = {v.get("id"): v.get("category") or ""
                 for v in hers(user_id).values()}
        for r in rows:
            cat = by_id.get(r.get("cluster_id"), "")
            if cat:
                out[cat] = out.get(cat, 0) + 1
    except Exception as e:
        print(f"[Offers] today's kinds read failed: {e}")
    return out


# Each offer of a kind already made today multiplies its weight by this.
_REPEAT_PENALTY = 0.3

# How many kinds to try before deciding nothing suits. Each try is one
# model call, and only inside an open window.
_KINDS_TO_TRY = 3


def _kinds_in_order(user_id: str, pool: List[Offer],
                    now_min: Optional[int]) -> List[List[Offer]]:
    """The pool split by category, best-suited to this hour first."""
    by_kind: Dict[str, List[Offer]] = {}
    for o in pool:                        # strength order kept inside a kind
        by_kind.setdefault(o.category or "", []).append(o)
    if len(by_kind) == 1 or now_min is None:
        return list(by_kind.values())[:_KINDS_TO_TRY]

    try:
        from memory.affinity import weights, describe
        w = weights(user_id, now_min)
        print(f"[Affinity] {user_id}: {describe(user_id, now_min)}")
    except Exception as e:
        print(f"[Affinity] read failed, strength order only: {e}")
        w = {}
    done = _offered_kinds_today(user_id)

    def score(kind):
        return w.get(kind, 0.3) * (_REPEAT_PENALTY ** done.get(kind, 0))

    order = sorted(by_kind, key=lambda k: -score(k))
    print(f"[Offers] {user_id}: kinds for this hour: "
          + ", ".join(f"{k or '?'} {score(k):.2f}" for k in order))
    return [by_kind[k] for k in order[:_KINDS_TO_TRY]]


def _title_matches(what: str, found: str) -> bool:
    """Does the found title contain the thing offered?

    By the song's own words, allowing for spelling: Nadaan and Nadan,
    Chalo and Cholo, Aankhen and Ankhen are all the same word written by
    different people.
    """
    import difflib
    import re as _re

    def words(t):
        return [w for w in _re.findall(r"[a-z]+", (t or "").lower()) if len(w) >= 3]

    want = words(_title(what))
    have = words(found)
    if not want:
        return True
    if not have:
        return False
    def found_(w):
        return any(difflib.SequenceMatcher(None, w, h).ratio() >= 0.75
                   for h in have)

    hits = [found_(w) for w in want]
    # Most of the title, or its opening words: video titles are often cut
    # short, and "Dil-E-Nadan Tujhe" is that song even without the rest.
    return (sum(hits) / len(want) >= 0.6
            or (len(want) >= 3 and all(hits[:3])))


def _pick_for_moment(user_id: str, pool: List[Offer], window,
                     now_min: Optional[int]) -> Optional[Offer]:
    """One of these that suits this moment, with why. Or None."""
    if not pool:
        return None
    if window is None or now_min is None:
        return pool[0]

    said = []
    try:
        from memory.windows import _said_today
        said = [x for x in (_said_today(user_id) or []) if x][-3:]
    except Exception:
        pass

    def hm(m):
        return f"{m // 60:02d}:{m % 60:02d}"

    # Who they are, so "the same tradition" means theirs. Without it a Tamil
    # Carnatic listener was given a Hindi Hanuman Chalisa, and the reason
    # offered was that she had said "Saaptachu", in Tamil.
    who = ""
    try:
        from memory.declared import get_declared
        d = get_declared(user_id)
        loves = ", ".join(v["label"] for v in sorted(
            hers(user_id).values(), key=lambda v: -v["strength"])[:5])
        who = (f"\nThey live in {d.place.home or 'India'} and speak "
               f"{d.language.pref}. What they love: {loves}.")
    except Exception as e:
        print(f"[Offers] who-they-are read failed: {e}")

    # And what today is. Navratri morning, pooja being prepared, and a
    # romantic film duet went out.
    day = ""
    try:
        from memory.festivals import today as _festival_today
        f = _festival_today()
        if f and f.get("name"):
            day = (f"\nToday is {f['name']}"
                   + (", a fasting day" if f.get("fasting") else "") + ".")
    except Exception:
        pass

    left = max(0, window.ends - now_min)
    listing = "\n".join(
        f"{i}. {o.what}  (they love {o.because}; suggested as {o.when})"
        for i, o in enumerate(pool, 1))
    heard = ("\nWhat they have said today:\n" +
             "\n".join(f"  - {x[:120]}" for x in said)) if said else ""

    prompt = f"""It is {hm(now_min)}. An older person is free now for about {left} minutes.{who}{day}
They have just finished: {window.after or 'nothing in particular'}.
Next in their day: {window.before or 'bed'}.{heard}

Things they might enjoy, each connected to something they love:
{listing}

Which ONE suits this exact moment best? Think about the hour, how long they
have, what they have just finished and what comes next. A romantic or
late-night song belongs to the evening; something that needs other people
needs company they have; a full film needs two free hours; a dish belongs
before a meal, not after; after a rest, something gentle. If something they
said today points to one, that one.

Their own tradition: a song, dish or film from a different region, language
or style of music than the ones they love does not fit, however famous.
On a festival or fasting day, respect it.
Only something they can actually listen to, watch, cook or do. A past
event, a famous innings or a memory is not something to offer.

If none of them truly suits this moment, answer 0. An offer that does not
fit is worse than none.

JSON only: {{"pick": <number or 0>, "why": "<one short reason, in English>"}}"""

    try:
        from llm import ask
        import json as _j
        raw = (ask(prompt, max_tokens=120) or "").replace("```json", "").replace("```", "")
        got = _j.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        n = int(got.get("pick") or 0)
        if 1 <= n <= len(pool):
            o = pool[n - 1]
            o.why_now = str(got.get("why") or "").strip()[:200]
            print(f"[Offers] {user_id}: for {window.clock()} at {hm(now_min)} "
                  f"-> {o.what} ({o.why_now})")
            return o
        print(f"[Offers] {user_id}: nothing of {len(pool)} suits "
              f"{window.clock()} at {hm(now_min)}")
        return None
    except Exception as e:
        # The model is down: fall back to the strongest, as before.
        print(f"[Offers] moment pick failed, taking the strongest: {e}")
        return pool[0]


def choose(user_id: str, window=None, now_min: Optional[int] = None) -> Optional[Offer]:
    """One thing to show her, with something she can act on. Or None.

    None is a perfectly good answer: nothing fits this stretch, or
    everything near her is already hers.
    """
    pool = candidates(user_id, window, now_min)
    if not pool:
        return None

    # Which KIND of thing first: what suits this hour for this person, and
    # less of what she has already been offered today.
    #
    # The hour comes from affinity.py: a default map (films and ghazals in
    # the evening, a dish before a meal, gardening in the morning) that her
    # own "not now"s and yeses reshape over the weeks. Already-offered
    # kinds are pushed down hard, so a second offer is a different kind
    # unless nothing else suits the hour at all — the top six used to be
    # one category every time, because the pool is ordered by the strength
    # of the interest it came from.
    offer = None
    for kind_pool in _kinds_in_order(user_id, pool, now_min):
        offer = _pick_for_moment(user_id, kind_pool[:10], window, now_min)
        if offer is not None:
            break
    if offer is None:
        # Nothing suits this stretch. Silence is the right answer; the
        # next window may suit something.
        return None

    try:
        from memory.artefacts import fetch_artefact
        # A devotional piece offered is still a recording to play. bhakti has
        # no fetcher on purpose, so that faith is never searched AROUND; a
        # named stotram being offered is searched for as the music it is.
        kind = "sangeet" if offer.category == "bhakti" else offer.category
        art = fetch_artefact(user_id, kind, offer.what)
        # The link is added to the message whatever it is, so it has to be
        # the thing offered. Search returns its nearest guess either way:
        # "Shauq Ka Awaara by Begum Akhtar" came back as Hariharan singing
        # something else, "Aji Bijane Ase Keu" as "Shunya Haate Phiri".
        # No link is better than the wrong song.
        if art and art.get("kind") != "tip" and not _title_matches(
                offer.what, str(art.get("title") or "")):
            print(f"[Offers] dropped link for {offer.what!r}: found "
                  f"{str(art.get('title'))[:60]!r}")
            art = None
        offer.artefact = art
    except Exception as e:
        print(f"[Offers] artefact failed: {e}")

    return offer


def record(user_id: str, offer: Offer, window=None,
           now_min: Optional[int] = None) -> bool:
    """Written when it REACHES her, never when it is composed.

    Recording at compose time made every held offer and every probe a
    suggestion she had ignored — twenty-nine over a month, one of which was
    ever delivered.

    And the circumstances, not just the label: in a month this says whether
    new things land in the afternoon and not at breakfast.
    """
    shape = ""
    try:
        from memory.carry import yesterdays
        y = yesterdays(user_id)
        shape = (y or {}).get("shape") or ""
    except Exception:
        pass

    try:
        _db().table("suggestions").insert({
            "user_id": user_id,
            "cluster_id": offer.cluster_id,
            "label": offer.what,
            "intent": "recommendation",
            "source": "offer",
            "because": offer.because,
            "window_label": (window.clock() if window else None),
            "offered_hour": (now_min // 60) if now_min is not None else None,
            "day_shape": shape[:200],
        }).execute()
        print(f"[Offers] {user_id}: offered {offer}")
        return True
    except Exception as e:
        print(f"[Offers] record failed: {e}")
        return False


def hint(offer: Offer) -> str:
    """What the composer is told. One thing, and why."""
    if not offer:
        return ""

    # The one thing, plus the one interest it comes from and nothing else.
    # This used to forbid naming "any other artist" and then ask for the
    # reason, which IS another artist: told both, the composer said neither
    # and wrote "Ismail, Ranjish Hi Sahi suniye." and nothing more.
    allowed = f" apart from {offer.because}, which is the reason" if offer.because else ""
    line = (f"\n\nOffer {offer.what}. That one thing only: name no other "
            f"artist, film or dish{allowed}, whatever else you know they "
            f"like, and do not credit it to anyone else."
            f"\nTwo or three sentences, warm, like a friend who thought of "
            f"them: what it is, and why now. A bare title is not an offer."
            f"\nNever claim it is on, playing or happening right now; you "
            f"cannot know that.")

    if offer.because:
        # Describe the RELATION, not the geometry. "Sits next to it" is how
        # this is drawn on a whiteboard and it does not survive translation.
        line += (f"\nThey already love {offer.because}, and this is the same "
                 f"kind of thing — someone who loves one usually knows the "
                 f"other. Say why it reminded you of them, in their own "
                 f"language and in your own words. Do not use the words "
                 f"'similar', 'related' or 'you might also like', and do not "
                 f"describe one as being near or next to the other.")

    if getattr(offer, "why_now", ""):
        # Why now, from whoever chose it. Context for the composer, in
        # English, never a sentence to reuse.
        line += (f"\nWhy it suits this moment: {offer.why_now}. Let that "
                 f"shape what you say, in your own words.")

    if offer.artefact and offer.artefact.get("kind") == "tip":
        # A tip is a paragraph of search-answer text with no link, and it
        # was presented as "something she can tap", so the composer pasted
        # it whole: "Arre suno na! Ludo mein jeetne ke liye...".
        tip = str(offer.artefact.get("title") or "")[:200]
        if tip:
            line += (f"\nBackground you may draw on, never quote: {tip}")
    elif offer.artefact:
        title = str(offer.artefact.get("title") or "")[:120]
        url = offer.artefact.get("url") or ""
        if title:
            # The app shows the link with its own title. The composer gets
            # only the fact that there is one: given the title, it copied
            # it, and a YouTube title is whatever the uploader wrote —
            # "পুরানো সেই দিনের/Purano Sei..." landed in Bengali script
            # inside an English message to someone who reads English.
            line += (f"\nA link to play it is added under your message "
                     f"automatically. Call it {offer.what} as written here, "
                     f"and do not write any link or the video's title "
                     f"yourself.")

    return line


def offered_in_window(user_id: str, window) -> bool:
    """Has something already gone out in this stretch?

    The window is the unit. There is no spacing rule any more — the window
    IS the spacing — so without this every tick inside an open stretch
    could send, and two offers went out an hour apart on the first day it
    worked.
    """
    if window is None:
        return False
    try:
        from datetime import date
        rows = (_db().table("suggestions").select("window_label")
                .eq("user_id", user_id)
                .gte("created_at", date.today().isoformat())
                .limit(20).execute()).data or []
        return any(str(r.get("window_label") or "") == window.clock()
                   for r in rows)
    except Exception as e:
        print(f"[Offers] window check failed: {e}")
        return False

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
import os
import random
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

# A clear no is permanent. Silence is not a no — she answers two messages a
# day, and treating that as rejection would empty the world.
#
# suggestions.py writes "declined_preference" for "not this" and
# "declined_timing" for "not now". Only "declined" was listed here, a value
# nothing writes any more, so a "pasand nahi" was never remembered and the
# same thing could be offered again. "Not now" is not a refusal: the hour
# was wrong, not the thing, and affinity.py learns from that instead.
REFUSED = ("declined", "declined_preference")

# How far out to look before the connection is too thin to say "because of".
RINGS = 2


@dataclass
class Offer:
    what: str                    # "Lag Ja Gale by Lata Mangeshkar"
    because: str = ""            # "Kishore Kumar"
    because_kind: str = ""       # the category of that interest: "sangeet"
    when: str = "anytime"
    category: str = ""
    cluster_id: Optional[str] = None
    artefact: Optional[Dict] = None
    why_now: str = ""            # why this one suits this moment
    way: str = ""                # khana: "outside" (a place) or "home"

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
                .select("id,label,attributes,strength,current_state")
                .eq("user_id", user_id).eq("status", "active")
                .eq("kind", "interest").limit(100).execute()).data or []
        for r in rows:
            a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
            out[str(r["label"]).strip().lower()] = {
                "id": r.get("id"), "label": r["label"],
                "category": a.get("category") or "",
                "strength": float(r.get("strength") or 0),
                # How she feels about it lately: her replies to offers move
                # this (suggestions.apply_reaction), not the strength.
                "state": (float(r["current_state"])
                          if r.get("current_state") is not None else None),
                # When she does it, as she has said: {"night": 3, "weekend": 1}.
                "usually": a.get("usually") or {},
            }
    except Exception as e:
        print(f"[Offers] clusters read failed: {e}")
    return out


# Songs struck today because no recording of them was found. Only inside one
# choose() call before, so the next hourly pass picked the same one again:
# "Khaike Paan Banaras Wala by Mohammad Rafi" six times on 16 Oct, each a
# model call, and nothing offered all afternoon.
_STRUCK: Dict[tuple, set] = {}


def _struck_today(user_id: str) -> set:
    key = (user_id, date.today().isoformat())
    if len(_STRUCK) > 500:
        _STRUCK.clear()
    return _STRUCK.setdefault(key, set())


def _rules_now(user_id: str):
    try:
        from memory import offer_rules as R
        return R.rules(user_id), R.moment_now(user_id)
    except Exception as e:
        print(f"[Offers] rules read failed: {e}")
        return [], {}


def way_lean(user_id: str, kind: str = "khana") -> Optional[str]:
    """Which way she takes this kind, from her answers: "home" when she has
    said she would make it herself more than she has taken it from outside.
    "Ghar pe hi bana lenge" (15 Oct) to fruit chaat from a place was a yes to
    the dish and a no to the place."""
    try:
        rows = (_db().table("suggestions").select("way,way_she_wants,reaction")
                .eq("user_id", user_id).eq("kind", kind)
                .not_.is_("reaction", "null").limit(100).execute()).data or []
    except Exception:
        return None
    home = sum(1 for r in rows if r.get("way_she_wants") == "home"
               or (r.get("reaction") == "accepted" and r.get("way") == "home"))
    out = sum(1 for r in rows if r.get("way_she_wants") == "outside"
              or (r.get("reaction") == "accepted" and r.get("way") == "outside"))
    if home > out:
        return "home"
    if out > home:
        return "outside"
    return None


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


def _is_routine(label: str, routine: set) -> bool:
    """Is this interest one of her routines under another name?

    Matched by exact label it missed: the interest is "Walk", the routine is
    "Evening walk", and at 10am she was offered pranayam "because of Walk",
    with a remark about her walk five hours before it. Then it was matched by
    shared words with a filler list ("morning", "subah", "ki"), which knew
    two languages. Now the model is asked, once per pair, in any language.
    """
    low = str(label or "").strip().lower()
    if not low or not routine:
        return False
    if low in routine:
        return True
    rs = sorted(str(r) for r in routine)[:20]
    try:
        from memory.judge import yes_no
        return yes_no(f'Her daily routines are: {rs}. Is "{label}" the same '
                      f'activity as one of them, under another name (e.g. '
                      f'"Walk" and "Evening walk")?',
                      key="routine:" + low + "|" + "|".join(rs))
    except Exception as e:
        print(f"[Offers] routine check failed for {label!r}: {e}")
        return False


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


_FAST_TODAY: Dict[tuple, bool] = {}


def _keeping_fast(user_id: str) -> bool:
    """A fasting festival she keeps is running today. Cached for the day."""
    key = (user_id, date.today().isoformat())
    if key not in _FAST_TODAY:
        try:
            from memory.festival_brief import for_user
            f = for_user(user_id)
            _FAST_TODAY[key] = bool(f and f.get("fasting") and f.get("she_keeps_it"))
        except Exception:
            _FAST_TODAY[key] = False
    return _FAST_TODAY[key]


def candidates(user_id: str, window=None, now_min: Optional[int] = None,
               rings: int = RINGS) -> List[Offer]:
    """Everything she could be shown, nearest first.

    Usually a handful. Empty when she has no interests yet, or when
    everything within reach is already hers — which is a good problem.
    """
    mine = hers(user_id)
    skip = (set(mine.keys()) | _refused(user_id) | _recently_offered(user_id)
            | {s.lower() for s in _struck_today(user_id)})
    from memory import offer_rules as _R
    _rules, _moment = _rules_now(user_id)
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
         if v["strength"] >= 0.5
         and (v.get("category") or "") not in _FULFIL_ONLY
         # Soured on. A "pasand nahi" to an offer moves the interest it came
         # from down by 0.4; once the average turns negative, it stops being
         # a reason to offer anything. The older picker in suggestions.py
         # already skipped these; this path did not read it at all.
         and not (v.get("state") is not None and v["state"] < 0)
         # Last, because it asks the model: only for what is still in.
         and not _is_routine(k, routine)],
        key=lambda v: -v["strength"])[:8]

    from memory.artefacts import adjacent

    out: List[Offer] = []
    seen = set()
    seen_dish = set()

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
                # By an artist she already loves: skipped for songs, so a
                # Kishore Kumar fan is not offered Kishore again. Not for
                # devotional pieces, where the voice IS the devotion: every
                # stotram Kamala could be offered was by M.S. Subbulakshmi,
                # all were skipped, and she was offered nothing all day.
                # The piece itself still has to be new to her.
                if (item.get("kind") or "") != "bhakti" and \
                        any(a in skip for a in _artists(what)):
                    continue
                if not _fits(item.get("when") or "anytime", window, now_min):
                    continue

                # Its own kind where the generator gave one, the interest's
                # where it did not (older cached rings).
                kind = item.get("kind") or seed["category"]

                # Her own standing rules: "Mangalvar ko nahi", "vrat ke din
                # nahi". A rule about a WAY ("not from outside") is applied
                # when the offer is made, so the dish can still come as
                # something to cook.
                if _R.blocked([r for r in _rules if not r.get("way")], kind,
                              None, _moment):
                    continue

                # During a fast she keeps, food comes only from the fasting
                # question, which is asked of her food interests. Two rings
                # out from Kishore Kumar the generator offered Rava Idli and
                # Masala Dosa, reached through a film, and they never passed
                # the fast.
                if kind == "khana" and _keeping_fast(user_id) and \
                        (seed.get("category") or "") != "khana":
                    continue

                # A dish, not a shop. "Idli Sambar by Murugan Idli Shop" went
                # out with a shop the generator had borrowed from the song
                # format: nobody had checked it existed near her, and when
                # she asked "kitna door hai" there was no answer to give.
                # The dish is the offer; where to eat it is for the chat to
                # look up, with a real place search, if she asks.
                if kind == "khana" and " by " in low:
                    what = what.split(" by ")[0].split(" By ")[0].strip()
                    low = what.lower()
                    if not what or low in skip or low in seen_dish:
                        continue
                    seen_dish.add(low)

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
                    because_kind=str(seed.get("category") or ""),
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
    """Is the video found the thing offered — the same song, and the singer
    named when one is named?

    This compared letters a-z with fuzzy matching, which allowed Nadaan for
    Nadan but turned "Canción" into "canci" and "Für" into "f". The model
    reads both titles in any script and language. Raises when it cannot
    answer, so the caller offers without a link rather than striking the
    offer for a check that never happened.
    """
    from memory.judge import yes_no
    return yes_no(f'We offered: "{what}". The video found is titled: '
                  f'"{found}". Is this video that same song or piece '
                  f'(allowing for spelling and transliteration)? If a singer '
                  f'is named in what we offered and the video names a '
                  f'different singer, answer NO.',
                  key="title:" + what.lower() + "|" + found.lower())


_MATCH_CACHE: Dict[str, tuple] = {}


def _match_recording(what: str, found: str):
    """Is the video found the song offered? -> (ok, corrected_what or None)

    The yes/no check was too strict and too loose at once on 16 Oct. It
    turned down "Mehbooba Oh Mehbooba - Lyrical" for Mehbooba Mehbooba and
    "Tujhe Dekha Toh" for Tujhe Dekha To, which are the same songs, and
    rightly turned down "Khaike Paan Banaras Wala" by Kishore Kumar when the
    model had called it Mohammad Rafi's, and then offered nothing all
    afternoon. Now: the same song in any spelling or version (lyrical, video,
    audio) is a match; when the video names a different singer, the offer
    is corrected to that singer rather than thrown away. Raises when the
    model cannot answer.
    """
    import json as _j
    k = what.lower() + "|" + found.lower()
    if k in _MATCH_CACHE:
        return _MATCH_CACHE[k]
    from llm import ask
    raw = ask(f'We want to offer the song: "{what}".\n'
              f'A video was found titled: "{found}".\n\n'
              'JSON only: {"same_song": true/false, "singer_in_title": "<the '
              'main singer the video title names, or null>", '
              '"same_singer": true/false/null}\n'
              '- same_song: the same song, allowing any spelling, '
              'transliteration, "Oh"/"To"/"Toh" and versions like Lyrical, '
              'Video Song, Audio, Full Song. A different song with similar '
              'words is false. A compilation or jukebox is false.\n'
              '- same_singer: does the singer we named match the video\'s '
              'singer (null if either names no singer).', max_tokens=80) or ""
    raw = raw.replace("```json", "").replace("```", "")
    got = _j.loads(raw[raw.find("{"):raw.rfind("}") + 1])
    if not got.get("same_song"):
        out = (False, None)
    elif got.get("same_singer") is False and got.get("singer_in_title"):
        title = what.split(" by ")[0].split(" By ")[0].strip()
        out = (True, f"{title} by {str(got['singer_in_title']).strip()}")
    else:
        out = (True, None)
    if len(_MATCH_CACHE) > 2000:
        _MATCH_CACHE.clear()
    _MATCH_CACHE[k] = out
    return out


def _hm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def user_context(user_id: str, window=None, now_min: Optional[int] = None) -> Dict:
    """Everything the choice should know, in one structure.

    Who they are, what they love, and where they are in their day. Built
    in one place so the picker sees all of it every time, and so it can be
    printed and read: the sentences this replaced had grown one fact at a
    time and left out the ones that mattered most for food, her conditions
    and her diet, so a fried sweet went to a woman on BP tablets.

    Every part is best effort. A part that cannot be read is left out, not
    guessed.
    """
    ctx: Dict = {"person": {}, "loves": [], "today": {}}

    # ── who ──
    try:
        from memory.declared import get_declared
        d = get_declared(user_id)
        ctx["person"].update({
            "name": d.name,
            "lives_in": d.place.home,
            "currently_in": d.place.current if d.place.away else None,
            "speaks": d.language.pref,
        })
        meals = getattr(d.rhythm, "meals", None) or {}
        if meals:
            ctx["person"]["meals"] = meals
    except Exception as e:
        print(f"[Offers] declared read failed: {e}")
    try:
        from memory.profile_store import get_user_profile
        p = get_user_profile(user_id) or {}
        demo = p.get("demographics") or {}
        health = p.get("health") or {}
        culture = p.get("cultural_context") or {}
        for k, v in (("age", demo.get("age")), ("gender", demo.get("gender")),
                     ("diet", demo.get("diet")),
                     ("religion", culture.get("religion")),
                     ("region", culture.get("region")),
                     ("health_conditions", health.get("conditions")),
                     ("medications", health.get("medications"))):
            if v:
                ctx["person"][k] = v
    except Exception as e:
        print(f"[Offers] profile read failed: {e}")
    # What she has said she can and cannot do, and her own standing rules
    # about offers, in plain words. Only what she or her caregiver said.
    try:
        from memory import offer_rules as _R
        can = {k: v.get("value") for k, v in (_R.abilities(user_id) or {}).items()
               if isinstance(v, dict) and v.get("source") in ("she_said", "caregiver")}
        if can:
            ctx["person"]["can_do"] = can
        said = [_R.describe(r) for r in _R.rules(user_id)]
        if said:
            ctx["her_rules"] = said
    except Exception as e:
        print(f"[Offers] rules for context failed: {e}")
    ctx["person"] = {k: v for k, v in ctx["person"].items() if v not in (None, "", [], {})}

    # ── what they love ──
    try:
        ctx["loves"] = []
        for v in sorted(hers(user_id).values(),
                        key=lambda v: -float(v.get("strength") or 0))[:10]:
            item = {"what": v["label"], "kind": v.get("category") or "",
                    "strength": round(float(v.get("strength") or 0), 2)}
            # How her replies to offers have moved it, when they have.
            us = v.get("usually") or {}
            if us:
                # Most-said first, and only what she has said more than once
                # once there is more than one thing said.
                top = sorted(us.items(), key=lambda x: -int(x[1]))
                keep = [k for k, n in top if n >= 2] or [top[0][0]]
                item["usually"] = keep[:3]
            st = v.get("state")
            if st is not None and st < 0.1:
                item["lately"] = "less keen" if st >= 0 else "turned against it"
            ctx["loves"].append(item)
    except Exception as e:
        print(f"[Offers] interests read failed: {e}")

    # ── where they are in their day ──
    t = ctx["today"]
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from memory.declared import get_declared
        tz = ZoneInfo(get_declared(user_id).place.timezone or "Asia/Kolkata")
        t["day"] = datetime.now(tz).strftime("%A")
    except Exception:
        pass
    if now_min is not None:
        t["time"] = _hm(now_min)
        try:
            from memory.affinity import slot_of
            t["part_of_day"] = slot_of(now_min)
        except Exception:
            pass
    if window is not None:
        t["free_for_minutes"] = max(0, window.ends - (now_min or window.starts))
        t["just_finished"] = window.after or None
        t["next"] = window.before or "bed"
        # Which end of the gap this moment is nearer. Ten minutes before
        # the walk is a moment for music to walk with; ten minutes after
        # the puja is a moment for something devotional; the middle of a
        # long empty afternoon is a moment for a film. The gap alone said
        # only how long, not where in it they are.
        if now_min is not None:
            ago = max(0, now_min - window.starts)
            ahead = max(0, window.ends - now_min)
            t["finished_minutes_ago"] = ago if window.after else None
            t["next_in_minutes"] = ahead
            if window.after and ago <= 45 and ago <= ahead:
                t["nearest"] = f"just after {window.after}"
            elif ahead <= 60 and ahead < ago:
                t["nearest"] = f"shortly before {window.before or 'bed'}"
            else:
                t["nearest"] = "the middle of a free stretch"

    # The whole day, so the choice can see what comes after "next" too: a
    # dish offered at 11 is for lunch at 1, and a film at 4 runs into the
    # walk at 5:30.
    try:
        from memory.day import events as _day_events
        sched = []
        for e in _day_events(user_id) or []:
            at = str(e.get("due_at") or "")[:5]
            what = e.get("label") or e.get("kind") or ""
            if not (at and what):
                continue
            row = {"at": at, "what": what, "kind": e.get("kind") or ""}
            if e.get("status") in ("confirmed", "denied"):
                row["status"] = "done" if e["status"] == "confirmed" else "skipped"
            sched.append(row)
        if sched:
            t["schedule"] = sched
    except Exception as e:
        print(f"[Offers] schedule read failed: {e}")
    # The festival as SHE keeps it, on every day it runs. festivals.today()
    # matched only the first day and anyone's festival, so on day two of
    # Navratri this said nothing, and a woman who does puja every morning
    # was offered idli at a restaurant.
    try:
        from memory.festival_brief import for_user as _festival_for
        f = _festival_for(user_id)
        if f:
            t["festival"] = f
    except Exception as e:
        print(f"[Offers] festival read failed: {e}")
    # Meat today, which is a date, not a flag: Tuesdays, Shravan, her own
    # days. memory.diet already knows; this path never asked.
    try:
        from memory.diet import can_eat_meat_today
        v = can_eat_meat_today(user_id)
        if v and not v.get("ok"):
            t["no_meat_today"] = True
    except Exception:
        pass
    try:
        from memory.windows import _said_today
        said = [x[:120] for x in (_said_today(user_id) or []) if x][-3:]
        if said:
            t["they_said_today"] = said
    except Exception:
        pass
    # What she said in the last hour, with how long ago. "Match dekh rahi
    # hoon" twenty minutes ago means she is in the middle of something, and
    # the right offer is none; the same words five hours ago mean nothing now.
    try:
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        from memory.day import _conversation
        now_utc = _dt.now(_tz.utc)
        recent = []
        for m in _conversation(user_id, (now_utc - _td(minutes=60)).isoformat()):
            if m["who"] != "them":
                continue
            try:
                at = _dt.fromisoformat(str(m["at"]).replace("Z", "+00:00"))
                at = at if at.tzinfo else at.replace(tzinfo=_tz.utc)
                ago = int((now_utc - at).total_seconds() // 60)
            except Exception:
                ago = None
            recent.append({"minutes_ago": ago, "said": m["text"][:160]})
        if recent:
            t["said_in_last_hour"] = recent[-4:]
    except Exception as e:
        print(f"[Offers] recent words read failed: {e}")
    try:
        done = _offered_kinds_today(user_id)
        if done:
            t["already_offered_today"] = done
    except Exception:
        pass
    ctx["today"] = {k: v for k, v in t.items() if v not in (None, "", [], {})}

    # ── how they answered before ──
    # From the offer log: her last answers, in her words where she gave
    # them, and what has worked at this part of the day and on this weekday,
    # by the kind of thing offered. "Weekday mei kaha, weekend pe" about
    # carrom on a Monday afternoon is seen the next Monday afternoon.
    try:
        from memory.offer_log import history, patterns, slot_of_hour
        hist = history(user_id)
        if hist:
            ctx["past_offers"] = hist
        pat = patterns(user_id,
                       now_slot=slot_of_hour((now_min // 60) if now_min is not None else None),
                       weekday=ctx.get("today", {}).get("day", ""))
        if pat:
            ctx["what_has_worked"] = pat
    except Exception as e:
        print(f"[Offers] history read failed: {e}")

    # ── trends ──
    # What this weekday leans towards, from what they actually do and say
    # (chicken on Sundays), and what they are enjoying less each time.
    trends = {}
    try:
        from memory.leanings import leanings as _leanings
        lean = {k: round(float(v), 2) for k, v in (_leanings(user_id) or {}).items() if v}
        if lean:
            trends["today_leans_to"] = dict(sorted(lean.items(), key=lambda x: -x[1])[:5])
    except Exception as e:
        print(f"[Offers] leanings read failed: {e}")
    try:
        from memory.topics import declining as _declining
        down = [str(d.get("subject")) for d in (_declining(user_id) or []) if d.get("subject")]
        if down:
            trends["enjoying_less"] = down[:5]
    except Exception as e:
        print(f"[Offers] declining read failed: {e}")
    # Her weekly habits that fall on today: "chicken on Sundays", found by
    # rhythms.py from the days she mentions things. It already added a line
    # to the message on the day; the choice itself never saw it.
    try:
        from memory.rhythms import due_today
        due = [f"{r['subject']} (on {r['on_that_day']} of her last {r['of']} "
               f"{r['weekday']}s)" for r in (due_today(user_id) or [])]
        if due:
            trends["today_is_usually"] = due
    except Exception as e:
        print(f"[Offers] rhythms read failed: {e}")
    if trends:
        ctx["trends"] = trends
    return ctx


def _pick_for_moment(user_id: str, pool: List[Offer], window,
                     now_min: Optional[int]) -> Optional[Offer]:
    """One of these that suits this moment, with why. Or None."""
    if not pool:
        return None
    if window is None or now_min is None:
        return pool[0]

    import json as _j
    ctx = user_context(user_id, window, now_min)
    ctx["options"] = [
        {"n": i, "what": o.what, "kind": o.category or "",
         "connected_to": o.because or "", "suits": o.when}
        for i, o in enumerate(pool, 1)]
    if os.getenv("OFFERS_DEBUG"):
        print("[Offers] context:\n" + _j.dumps(ctx, ensure_ascii=False, indent=2))

    prompt = f"""You choose ONE thing to suggest to an older person right now, or nothing.
Everything known about them and their day, as JSON:

{_j.dumps(ctx, ensure_ascii=False)}

Choose the option that best suits THIS person at THIS moment:

- The moment: the time and part of day, how long they are free, and which
  part of their schedule it is nearest ("nearest"). Shortly before
  something, choose what leads into it: a dish before a meal, music to walk
  with before the walk. Just after something, what follows from it:
  something devotional after prayer, something gentle after a rest or a
  walk. In the middle of a long free stretch, something that fills it: a
  film needs two free hours. A romantic or late-night song belongs to the
  evening. If something they said today points to one, that one.
- Their habits: a love with "usually" is done at that time ("night",
  "weekend"); offer it, or something like it, then, not at other times.
  "today_is_usually" is a weekly habit that falls today: a meal suggestion
  should fit with it, not compete with it.
- Their pattern: what this weekday leans towards ("trends"), how they
  answered past offers ("past_offers", with their own words), and what has
  worked by kind at this time of day and on this weekday ("what_has_worked").
  A kind answered "not now" at this time should wait; a kind accepted at
  this time is a good sign. Skip anything they are enjoying less.
- Their health: a dish must suit their conditions, medicines and diet. With
  blood pressure, diabetes or heart trouble, nothing fried, very sweet, very
  salty or rich. Vegetarian means vegetarian. When unsure, the lighter one.
  An exercise, yoga or breathing practice must be gentle and safe for their
  age and conditions: with blood pressure or heart trouble nothing forceful
  (no kapalbhati or bhastrika), no breath-holding, no inversions, no
  strain; with knee or back pain nothing on the floor or weight-bearing.
  When unsure, choose something that is not exercise.
- Their world: songs, films, prayers and dishes from their own region,
  language and tradition, whatever else is famous.
- The day: during a festival ("festival"), food follows it. If it fasts and
  they keep it, only what the fast allows ("eaten_instead"); food among what
  they talked about during it, this time or last time, is the best guide. If it
  fasts and you do not know whether they keep it, suggest no dish at all.
  "no_meat_today" means nothing with meat.
- Variety: prefer a kind not already offered today.
- Real: only something they can actually listen to, watch, cook or do now.
  A past event, a famous innings or a memory is not something to offer.

- Busy: if what they said in the last hour ("said_in_last_hour") shows they
  are in the middle of something now — watching, cooking, eating, out, at
  the temple, with family or guests, resting — answer 0. Someone already
  absorbed in something does not want to be offered something else.

- Her rules ("her_rules") are her own words and always hold. What she
  cannot do ("can_do" false) rules out anything that needs it.

If none truly suits, answer 0. An offer that does not fit is worse than none.

JSON only: {{"pick": <n or 0>, "why": "<one short reason, in English>"}}"""

    try:
        from llm import ask
        raw = (ask(prompt, max_tokens=120) or "").replace("```json", "").replace("```", "")
        got = _j.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        n = int(got.get("pick") or 0)
        if 1 <= n <= len(pool):
            o = pool[n - 1]
            o.why_now = str(got.get("why") or "").strip()[:200]
            print(f"[Offers] {user_id}: for {window.clock()} at {_hm(now_min)} "
                  f"-> {o.what} ({o.why_now})")
            return o
        print(f"[Offers] {user_id}: nothing of {len(pool)} suits "
              f"{window.clock()} at {_hm(now_min)}")
        return None
    except Exception as e:
        # The model is down: fall back to the strongest, as before.
        print(f"[Offers] moment pick failed, taking the strongest: {e}")
        return pool[0]


# How far a dish is worth going for, and what is not a place to eat.
PLACE_MAX_KM = 3.0
PLACE_MIN_RATING = 3.8
# Not a place to eat: by Google's own place types, not by words in the name —
# "Kneipe", "taberna" and "cervecería" were never on a list of English names.
_NOT_FOR_HER = {"night_club", "liquor_store", "casino"}


def _place_for(user_id: str, dish: str) -> Optional[Dict]:
    """A real place near her that serves this dish, or None.

    "Idli Sambar by Murugan Idli Shop" named a shop nobody had looked for:
    there is none within 10 km of Vyalikaval. So the place is found, not
    imagined: a Google Places search for the dish around where she is now
    (home, or wherever she is travelling), nearest first, and only one
    she could actually go to — close, open, decently rated, not a bar.

    None is common and fine: the dish is still offered, without a place.
    """
    try:
        from routes.integrations import get_nearby_places
        r = get_nearby_places(user_id, dish, radius=int(PLACE_MAX_KM * 1000))
    except Exception as e:
        print(f"[Offers] place search failed for {dish!r}: {e}")
        return None
    if not isinstance(r, dict) or r.get("error"):
        print(f"[Offers] place search for {dish!r}: {(r or {}).get('error')}")
        return None

    for p in r.get("places") or []:          # nearest first
        name = str(p.get("name") or "").strip()
        d = p.get("distance_km")
        if not name or d is None or d > PLACE_MAX_KM:
            continue
        if p.get("open") is False:
            continue
        if p.get("rating") is not None and float(p["rating"]) < PLACE_MIN_RATING:
            continue
        types = set(p.get("types") or [])
        if types & _NOT_FOR_HER:
            continue
        # A bar that is not also a restaurant or cafe is a bar.
        if "bar" in types and not types & {"restaurant", "cafe", "meal_takeaway",
                                           "bakery", "food"}:
            continue
        url = ("https://www.google.com/maps/search/?api=1&query="
               + urllib.parse.quote(name)
               + (f"&query_place_id={p['place_id']}" if p.get("place_id") else ""))
        area = str(p.get("address") or "").split(",")
        # The name as it would be said. Google listings carry their own
        # advertising: "Paakashala @ Nagavara | Restaurants Near Manyata Tech
        # Park" is Paakashala. The map link keeps the full listing.
        said = name
        for cut in (" | ", " @ ", " - "):
            said = said.split(cut)[0]
        said = said.strip() or name
        return {
            "kind":        "place",
            "title":       said,
            "url":         url,
            "area":        ", ".join(x.strip() for x in area[-3:-1]) if len(area) > 2 else (p.get("address") or ""),
            "distance_km": d,
            "walk_min":    p.get("walk_min"),
            "rating":      p.get("rating"),
            "open":        p.get("open"),
        }
    print(f"[Offers] {user_id}: no place within {PLACE_MAX_KM:g} km for {dish!r}")
    return None


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
    # A song is offered only if a real recording of it was found. The
    # generator sometimes invents one: "Manjal Kaapaarikkum by M.S.
    # Subbulakshmi", reached from curd rice, does not exist, and no search
    # found it. That absence is the signal. An invented song offered to
    # someone who has known this music for sixty years costs more trust
    # than any number of silences, so an unverified song is struck from the
    # pool and the choice is made again, up to twice.
    struck: set = set()
    for _attempt in range(3):
        offer = None
        for kind_pool in _kinds_in_order(
                user_id, [o for o in pool if o.what not in struck], now_min):
            offer = _pick_for_moment(user_id, kind_pool[:10], window, now_min)
            if offer is not None:
                break
        if offer is None:
            # Nothing suits this stretch. Silence is the right answer; the
            # next window may suit something.
            return None

        art = None
        try:
            from memory.artefacts import fetch_artefact
            # A devotional piece offered is still a recording to play. bhakti
            # has no fetcher on purpose, so that faith is never searched
            # AROUND; a named stotram being offered is searched for as the
            # music it is.
            kind = "sangeet" if offer.category == "bhakti" else offer.category
            art = fetch_artefact(user_id, kind, offer.what)
            # The link is added to the message whatever it is, so it has to
            # be the thing offered, by the singer named. No link is better
            # than the wrong song.
            if art and art.get("kind") != "tip":
                ok, fixed = _match_recording(offer.what, str(art.get("title") or ""))
                if not ok:
                    print(f"[Offers] dropped link for {offer.what!r}: found "
                          f"{str(art.get('title'))[:60]!r}")
                    art = None
                elif fixed and fixed != offer.what:
                    mine_now = set(hers(user_id).keys())
                    if any(a in mine_now for a in _artists(fixed)):
                        # Corrected to a singer she already loves: that is a
                        # reminder, not an offer, and belongs to the cluster path.
                        print(f"[Offers] {offer.what!r} is really {fixed!r}, "
                              f"already hers: not offering it")
                        art = None
                    else:
                        print(f"[Offers] singer corrected: {offer.what!r} -> {fixed!r}")
                        offer.what = fixed
        except Exception as e:
            print(f"[Offers] artefact failed: {e}")
            # A search that failed says nothing about whether the song
            # exists. Offer it without a link rather than strike it.
            offer.artefact = None
            return offer

        if art is None and offer.category in ("sangeet", "bhakti"):
            print(f"[Offers] {user_id}: no recording found for "
                  f"{offer.what!r}, not offering it")
            struck.add(offer.what)
            _struck_today(user_id).add(offer.what)
            continue

        # A dish: where she can actually get it, near where she is. The map
        # link goes under the message in place of a recipe, which is what
        # someone who loves eating out would act on. No place nearby, and
        # the recipe (or nothing) stays.
        # Not from outside when she has a rule against it, or has shown she
        # makes things herself: then it is offered as a dish to cook.
        if offer.category == "khana":
            rules_, moment_ = _rules_now(user_id)
            try:
                from memory import offer_rules as _R
                no_outside = _R.blocked(rules_, "khana", "outside", moment_)
            except Exception:
                no_outside = None
            lean = way_lean(user_id, "khana")
            place = None
            if not no_outside and lean != "home":
                place = _place_for(user_id, offer.what)
            elif no_outside:
                print(f"[Offers] {user_id}: not from outside ({_R.describe(no_outside)})")
            if place:
                art = place
                offer.way = "outside"
            else:
                offer.way = "home"

        offer.artefact = art
        return offer
    return None


def record(user_id: str, offer: Offer, window=None,
           now_min: Optional[int] = None) -> bool:
    """Written when it REACHES her, never when it is composed.

    Recording at compose time made every held offer and every probe a
    suggestion she had ignored — twenty-nine over a month, one of which was
    ever delivered.

    And the circumstances, not just the label: in a month this says whether
    new things land in the afternoon and not at breakfast.
    """
    # Her hour, worked out here when the caller did not pass it. The
    # scheduler calls record(uid, offer, window) without a time, so every
    # offer was stored with offered_hour empty, and affinity.py, which
    # learns which kinds suit which hour from exactly this column, has had
    # nothing to learn from: every slot still reads "(default)".
    if now_min is None:
        try:
            from zoneinfo import ZoneInfo
            from memory.declared import get_declared
            _now = datetime.now(ZoneInfo(get_declared(user_id).place.timezone
                                         or "Asia/Kolkata"))
            now_min = _now.hour * 60 + _now.minute
        except Exception as e:
            print(f"[Offers] hour for record failed: {e}")

    shape = ""
    try:
        from memory.carry import yesterdays
        y = yesterdays(user_id)
        shape = (y or {}).get("shape") or ""
    except Exception:
        pass

    row = {
        "user_id": user_id,
        "cluster_id": offer.cluster_id,
        "label": offer.what,
        "intent": "recommendation",
        "source": "offer",
        "because": offer.because,
        "window_label": (window.clock() if window else None),
        "offered_hour": (now_min // 60) if now_min is not None else None,
        "day_shape": shape[:200],
    }
    # The log's own columns: what kind of thing it was, her date and weekday,
    # the link, the festival, and why it was chosen. See offer_log.py.
    try:
        from memory.offer_log import stamp
        extra = stamp(user_id, offer, window, now_min)
    except Exception as e:
        print(f"[Offers] log stamp failed: {e}")
        extra = {}
    if getattr(offer, "way", ""):
        extra["way"] = offer.way
    try:
        _db().table("suggestions").insert({**row, **extra}).execute()
        print(f"[Offers] {user_id}: offered {offer}")
        return True
    except Exception as e:
        if extra:
            # The columns may not exist yet: record the offer without them
            # rather than lose it.
            try:
                _db().table("suggestions").insert(row).execute()
                print(f"[Offers] {user_id}: offered {offer} (log columns missing: {str(e)[:60]})")
                return True
            except Exception as e2:
                e = e2
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
    allowed = (f" apart from {offer.because}, which is the reason"
               if offer.because and not (offer.because_kind and offer.category
                                         and offer.because_kind != offer.category) else "")
    line = (f"\n\nOffer {offer.what}. That one thing only: name no other "
            f"artist, film or dish{allowed}, whatever else you know they "
            f"like, and do not credit it to anyone else."
            f"\nTwo or three sentences, warm, like a friend who thought of "
            f"them: what it is, and why now. A bare title is not an offer."
            f"\nNever claim it is on, playing or happening right now; you "
            f"cannot know that."
            f"\nDo not tie it to something else in their day that is not "
            f"happening now: no 'your walk' in the morning when the walk is in "
            f"the evening."
            f"\nSpeak about them, never about a kind of person: no 'people "
            f"who like X enjoy Y'.")

    cross = bool(offer.because and offer.because_kind and offer.category
                 and offer.because_kind != offer.category)
    if cross:
        # Reached from a different kind of thing: masala chai from Carrom.
        # Told "this is the same kind of thing, say why it reminded you", the
        # writer invented a reason — "Carrom ke shaukeen logon ko aise waqt
        # mein chai ka maza lena khoob aata hai, isliye mujhe aapka khayal
        # aaya" (17 Oct). There is no such link to explain.
        line += (f"\nOffer it on its own, for this moment. Do not mention "
                 f"{offer.because}, and do not explain why you thought of it.")
    elif offer.because:
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

    # A dish she would make herself, or not have from outside: say so.
    if offer.category == "khana" and getattr(offer, "way", "") == "home":
        line += ("\nOffer it as something to make at home. Do not suggest "
                 "ordering it or going out for it, and do not name a shop "
                 "or restaurant.")

    if offer.artefact and offer.artefact.get("kind") == "tip":
        # A tip is a paragraph of search-answer text with no link, and it
        # was presented as "something she can tap", so the composer pasted
        # it whole: "Arre suno na! Ludo mein jeetne ke liye...".
        tip = str(offer.artefact.get("title") or "")[:200]
        if tip:
            line += (f"\nBackground you may draw on, never quote: {tip}")
    elif offer.artefact and offer.artefact.get("kind") == "place":
        a = offer.artefact
        far = a.get("distance_km")
        walk = a.get("walk_min")
        line += (f"\nThere is a real place near them that serves it: "
                 f"{a.get('title')}"
                 + (f", {a.get('area')}" if a.get("area") else "")
                 + (f", about {far} km away" if far is not None else "")
                 + (f" (about {walk} minutes on foot)" if walk else "")
                 + ". Name the place and say roughly how far it is, in their "
                 "own language. It is straight-line distance: say 'about', "
                 "never an exact figure. Say they can get it there, not that "
                 "it is the best. Do not say it is open now unless told so"
                 + (" — it is open now." if a.get("open") is True else ".")
                 + " A map link is added under your message automatically; "
                 "do not write a link or an address yourself.")
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

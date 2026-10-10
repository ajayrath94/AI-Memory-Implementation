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
        if "meal" not in (window.before or "").lower() and (window.before or "").lower() not in ("breakfast", "lunch", "dinner"):
            return False
        return (window.ends - now_min) <= 90
    return True


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
    seeds = sorted(
        [v for k, v in mine.items()
         if k not in routine and v["strength"] >= 0.5],
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

                out.append(Offer(
                    what=what,
                    because=seed["label"],
                    when=item.get("when") or "anytime",
                    category=seed["category"],
                    cluster_id=seed.get("id"),
                ))

        # Only go further out when the near ring has little left — the
        # second ring is a thinner connection and should not crowd out the
        # first.
        if len(out) >= 6:
            break
        frontier = next_frontier[:6]

    return out


def choose(user_id: str, window=None, now_min: Optional[int] = None) -> Optional[Offer]:
    """One thing to show her, with something she can act on. Or None.

    None is a perfectly good answer: nothing fits this stretch, or
    everything near her is already hers.
    """
    pool = candidates(user_id, window, now_min)
    if not pool:
        return None

    # Weighted towards the first few — they come from her strongest
    # interests — without always being the same one.
    top = pool[:6]
    weights = [max(1, len(top) - i) for i in range(len(top))]
    offer = random.choices(top, weights=weights, k=1)[0]

    try:
        from memory.artefacts import fetch_artefact
        offer.artefact = fetch_artefact(user_id, offer.category, offer.what)
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

    line = (f"\n\nOffer {offer.what}. That one and nothing else — do not "
            f"name any other artist, film or dish, whatever else you know "
            f"they like, and do not credit it to anyone else.")

    if offer.because:
        # Describe the RELATION, not the geometry. "Sits next to it" is how
        # this is drawn on a whiteboard and it does not survive translation.
        line += (f"\nThey already love {offer.because}, and this is the same "
                 f"kind of thing — someone who loves one usually knows the "
                 f"other. Say why it reminded you of them, in their own "
                 f"language and in your own words. Do not use the words "
                 f"'similar', 'related' or 'you might also like', and do not "
                 f"describe one as being near or next to the other.")

    if offer.artefact:
        title = str(offer.artefact.get("title") or "")[:120]
        url = offer.artefact.get("url") or ""
        if title:
            line += (f"\nThere is something they can tap: \"{title}\""
                     + (f" — {url}" if url else "")
                     + ". Offer that, in one line.")

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

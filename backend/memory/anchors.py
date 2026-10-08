"""
ANCHORS — the few things about her that are worth being sure of.

Her profile holds twenty-eight fields and no record of how any of them came to
be. "chicken" sits in food.likes and could be a form she filled in months ago,
one meal the extractor caught, or her saying "Sunday ko chicken banati hoon"
four Sundays running. Those are different facts, and the adjacency work
suggested Chilli Chicken on the strength of the weakest reading.

So each anchor carries where it came from and when, and anything acting on one
states the strength it needs.

HOW STRONG A BELIEF IS

    declared    typed into a form. A claim, not evidence — the setup form was
                saved seven times in testing and put Shakira at 7.0.
    said        she said it once.
    repeated    on two or more separate days. The strongest ordinary signal.
    observed    the system watched it happen.
    inferred    deduced. Her religion from mentions of puja. The weakest.

WHY NOT PATTERNS OR SIMILARITY
"shudh shakahari", "veg hi khati hoon", "main non-veg nahi khati", "சைவம்" —
a phrase list misses the fifth one, as it did with kinship and with labels.
And embeddings cannot help: we measured "ghutna" against "knee pain" at 0.695
while two different singers scored 0.704. Similarity cannot tell the same fact
from the same topic.

One question instead, asked of what she said.

WHAT GETS CONFIRMED
Things that change how she is treated — where home is, her diet, who she lives
with — are asked about before they are believed. They persist and are costly
to be wrong about. A birthday or a food she likes is cheap to correct, so it
is simply recorded; if it is wrong she will say so.
"""
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

# What a change costs to get wrong, which is what decides whether to ask.
#
#   ask    changes how she is treated, and persists
#   keep   cheap to correct — she will say if it is wrong
ANCHORS = {
    "home_location":  {"confirm": True,  "what": "where she lives"},
    "lives_with":     {"confirm": True,  "what": "who she lives with"},
    # Not "vegetarian", which is a boolean and cannot hold Shravan, or
    # Tuesdays, or a woman who eats chicken on Sundays and nothing else.
    "eats_meat":      {"confirm": True,  "what": "whether she eats meat"},
    "avoids_meat_on": {"confirm": True,  "what": "days she keeps without meat"},
    "keeps_fasts":    {"confirm": False, "what": "whether she keeps fasts"},
    "birthday":       {"confirm": False, "what": "her birthday"},
    "from_location":  {"confirm": False, "what": "where she is from"},
    "doctor":         {"confirm": False, "what": "her doctor"},
    "occupation":     {"confirm": False, "what": "what she did"},
}


def _db():
    from supabase_store import get_client
    return get_client()


def read(user_id: str, text: str, propositions: List[Dict] = None) -> List[Dict]:
    """Does what she just said settle anything about her? Usually not.

    Returns [{field, value, confidence, quote}] — empty most of the time,
    because most sentences are about her day rather than about her.
    """
    said = (text or "").strip()
    if len(said) < 8:
        return []

    prompt = f"""Someone elderly in India said this to their companion:

"{said[:500]}"

Does it settle any of these about HER? Most messages settle nothing.

  home_location   where she LIVES — not where she is staying, not a trip
  from_location   where she is originally from, which is a different thing
  lives_with      who is in the house with her
  eats_meat       "yes" if she eats meat, "no" if she does not
  avoids_meat_on  days or months she keeps without it — tuesday, shravan
  birthday        her own, as a date
  doctor          a doctor she sees by name
  occupation      what she did for a living

JSON only:
{{"found": [{{"field": "...", "value": ..., "confidence": 0.0-1.0,
              "quote": "her words"}}]}}

Only when SHE is the subject. "Mera beta Bangalore mein rehta hai" says where
her son lives, not where she does. "Padosan shakahari hai" is the neighbour.

Only when she states it, not when she is asked. A question settles nothing.

AND READ THE NEGATION. "Is saal Navratri ka vrat nahi rakhungi" means she is
NOT keeping it — that sentence came back as avoids_meat_on: ["Navratri"],
which is the opposite of what she said. A denial is a value too: return the
field with "none" when she says she does not do the thing.

  "Navratri mein vrat rakhti hoon"       -> avoids_meat_on: ["Navratri"]
  "Is saal vrat nahi rakhungi"           -> avoids_meat_on: "none"
  "Main shakahari nahi hoon"             -> eats_meat: "yes"
  "Ab mandir nahi jaati"                 -> keeps_fasts: "none"

eats_meat is "no" only when she says she does NOT eat meat — a statement
about what she avoids, not a meal. "Shudh shakahari hoon" is true; "roz dal
chawal khati hoon" is not, because eating dal daily says nothing about
Sundays, and "aaj khichdi banayi" says nothing at all.

eats_meat is "yes" whenever she mentions eating or cooking meat for herself.
"Sunday ko chicken banati hoon" is false — one such mention settles it,
because nobody cooks chicken for themselves by accident.

The two directions are deliberately not symmetrical. Being wrong that she is
vegetarian means she is offered dal; being wrong the other way means meat
offered to someone who does not eat it.

An empty list is the usual answer. No prose."""

    try:
        from llm import ask
        import json as _j
        raw = ask(prompt, max_tokens=220).replace("```json", "").replace("```", "")
        found = _j.loads(raw.strip()).get("found") or []
    except Exception as e:
        print(f"[Anchor] read failed: {e}")
        return []

    out = []
    for f in found:
        field = str(f.get("field") or "").strip()
        if field not in ANCHORS or f.get("value") in (None, ""):
            continue
        # "none" is a real answer — she has stopped doing the thing. Without
        # this, "is saal vrat nahi rakhungi" was stored as though she keeps
        # it, because the subject survived and the negation did not.
        if str(f.get("value")).strip().lower() in ("none", "nothing", "[]"):
            try:
                _db().table("profile_anchors").delete() \
                    .eq("user_id", user_id).eq("field", field).execute()
                print(f"[Anchor] {field} cleared — she says she does not")
            except Exception as _de:
                print(f"[Anchor] clear failed: {_de}")
            continue
        out.append({
            "field": field,
            "value": f.get("value"),
            "confidence": float(f.get("confidence") or 0.5),
            "quote": str(f.get("quote") or said)[:200],
        })
    return out


def current(user_id: str, field: str) -> Optional[Dict]:
    """What is believed now, and how it came to be believed."""
    try:
        rows = (_db().table("profile_anchors").select("*")
                .eq("user_id", user_id).eq("field", field)
                .limit(1).execute()).data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[Anchor] current read failed: {e}")
        return None


def record(user_id: str, field: str, value, source: str = "said",
           quote: str = "") -> bool:
    """Write it down, with where it came from.

    A second mention on a different day lifts `said` to `repeated`, which is
    the strength the costly decisions require — suggesting meat, telling a
    caregiver where she is.
    """
    if field not in ANCHORS:
        return False
    was = current(user_id, field)
    today = date.today().isoformat()

    days = list((was or {}).get("seen_on") or [])
    if today not in days:
        days.append(today)
    # Said on two separate days is no longer a passing remark.
    if source == "said" and len(days) >= 2:
        source = "repeated"

    try:
        _db().table("profile_anchors").upsert({
            "user_id": user_id,
            "field": field,
            # Always text — the column is text, and passing a Python bool
            # made every write fail silently behind the except below.
            "value": ("yes" if value is True else "no" if value is False
                      else str(value)[:200]),
            "source": source,
            "quote": quote[:200],
            "seen_on": days[-10:],
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="user_id,field").execute()
        print(f"[Anchor] {field} = {value} ({source}, {len(days)} day(s))")
        return True
    except Exception as e:
        print(f"[Anchor] write failed: {e}")
        return False


def pending(user_id: str) -> Optional[Dict]:
    """Something heard but not yet believed, waiting on her answer."""
    try:
        rows = (_db().table("profile_anchors").select("*")
                .eq("user_id", user_id).eq("source", "unconfirmed")
                .order("confirmed_at", desc=True).limit(1).execute()).data or []
        return rows[0] if rows else None
    except Exception:
        return None


def hear(user_id: str, text: str) -> str:
    """Read what she said; record or ask. Returns a line for the composer.

    Called on the message, beside the other per-message work. Returns "" for
    almost everything, which is correct — most of what she says is about her
    day, not about her.
    """
    hints = []
    for a in read(user_id, text):
        field, value = a["field"], a["value"]
        spec = ANCHORS[field]
        was = current(user_id, field)

        # Does this contradict something else she has told us? "Navratri
        # mein bhi chicken khaya" sets eats_meat to yes, which it already
        # was — so nothing changed and nothing was asked, while
        # avoids_meat_on still said she keeps Navratri without meat.
        #
        # A contradiction is a change. Ask, the same as any other.
        if field == "eats_meat" and str(value).lower() in ("yes", "true"):
            avoid = current(user_id, "avoids_meat_on")
            said = (a.get("quote") or "").lower()
            if avoid:
                for d in str(avoid.get("value") or "").lower().replace(
                        "[", " ").replace("]", " ").replace("'", " ").split(","):
                    d = d.strip()
                    if d and d in said:
                        hints.append(
                            f"\n\nShe has eaten meat during {d}, and it is "
                            f"on record that she keeps {d} without it. Ask "
                            f"— lightly, once — whether she still keeps it, "
                            f"or whether that has changed.")
                        break

        # Nothing to do if it is already what she just said.
        if was and str(was.get("value")) == str(value):
            record(user_id, field, value, "said", a["quote"])
            continue

        if not spec["confirm"]:
            record(user_id, field, value, "said", a["quote"])
            continue

        # Costly to be wrong about, so ask rather than assume. Recorded as
        # unconfirmed so her next message can settle it.
        record(user_id, field, value, "unconfirmed", a["quote"])
        hints.append(
            f"\n\nShe may have just said something about {spec['what']}: "
            f"{value}. It was previously {(was or {}).get('value') or 'not known'}. "
            f"Ask her, once, lightly, in passing — not as a form. Something "
            f"like a person checking they heard right."
        )

    return "".join(hints)


def settle(user_id: str, text: str) -> bool:
    """Her answer to the question. Yes makes it true; no drops it."""
    p = pending(user_id)
    if not p:
        return False

    prompt = f"""Someone was asked to confirm this about themselves:

  {ANCHORS.get(p['field'], {}).get('what', p['field'])}: {p['value']}

They replied: "{(text or '')[:200]}"

Did they agree? One word: yes, no, or unclear."""
    try:
        from llm import ask
        a = ask(prompt, max_tokens=10).strip().lower().strip(".")
    except Exception:
        return False

    if a.startswith("y"):
        return record(user_id, p["field"], p["value"], "said", p.get("quote") or "")
    if a.startswith("n"):
        try:
            _db().table("profile_anchors").delete() \
                .eq("user_id", user_id).eq("field", p["field"]) \
                .eq("source", "unconfirmed").execute()
            print(f"[Anchor] {p['field']} — she said no")
        except Exception:
            pass
    return False


def strength(user_id: str, field: str) -> str:
    """How firmly this is believed. '' when it is not believed at all.

    Anything acting on an anchor asks for this first: suggesting meat needs
    'repeated', using her name needs 'declared'.
    """
    was = current(user_id, field)
    return (was or {}).get("source") or ""

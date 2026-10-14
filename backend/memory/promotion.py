"""
PROMOTION — what earns a cluster, and what does not.

She said she ate lemon rice at lunch and it became an interest with the same
weight as a favourite typed into the setup form. The cause was not weighting:
a confirmed meal was written through record_declared_interest, the path for
things she states, so eating something once was recorded as declaring a
preference.

Three different things arrive, they need different evidence, and treating them
as one mechanism is what produced that.

    a stated preference    "Kishore Kumar acche lagte hain"
                           one mention, straight through. Already built —
                           record_propositions handles it and is unchanged.

    a weighty event        "Doctor ne kaha operation karana padega"
                           one mention, promoted at once. Waiting for her to
                           say it twice would be a failure.

    a habit                khichdi on Tuesday, Sunday and Wednesday
                           no single mention says this. Only the count across
                           DISTINCT DAYS does.

DISTINCT DAYS, NOT MENTIONS
Saying "khichdi" four times in one conversation is one day of evidence. The
count is over days because that is what separates a habit from an afternoon.

REPORT MODE FIRST
This runs and prints what it WOULD promote, writing nothing, until the
threshold has been watched for a week. Three days in fourteen is a guess; a
week of seeing what it catches turns it into a measurement.
"""
import json
from datetime import datetime, date, timezone, timedelta
from typing import List, Dict

# A habit, in distinct days out of the last fortnight. Three feels right for
# someone who talks most days; someone who opens the app twice a week would
# need longer, which is the case for making this per-user later.
HABIT_DAYS = 3
HABIT_WINDOW = 14

# A single mention worth a cluster on its own. Below this it still gets a
# second chance through repetition, so the bar can afford to be high.
WEIGHT_BAR = 0.7


def _db():
    from supabase_store import get_client
    return get_client()


# ── a habit: counted across days ──────────────────────────────────────────────

# Two windows, because they say different things. Three times in a fortnight
# is something she is doing NOW and worth offering back today. Three times in
# a month is a slower rhythm — khichdi every ten days is a habit the short
# window cannot see, and six weeks of it were invisible.
#
# A subject can clear both, or only the wider one, and which it is changes how
# it would be offered.
WINDOWS = (14, 30)


def habits(user_id: str, window: int = HABIT_WINDOW) -> List[Dict]:
    """Subjects with no cluster that keep coming back.

    Read from subject_mentions, not from memory_stm.untagged. The stm version
    worked for a fortnight and then quietly stopped: when a day folds into its
    month its untagged array goes with it, so a subject mentioned on the 1st,
    the 10th and the 20th lost the 1st the moment September folded — and the
    count that would have earned it a cluster silently reset.
    """
    from memory.mentions import recurring

    seen, out = set(), []
    for w in (window,) if window != HABIT_WINDOW else WINDOWS:
        for h in recurring(user_id, min_days=HABIT_DAYS, window=w,
                           unresolved_only=True):
            key = h["subject"].lower()
            if key in seen:
                continue
            seen.add(key)
            # Which window caught it. "Recent" is worth offering today;
            # "regular" is worth knowing about her.
            # Three mentions in one week and nothing since is a spell — she
            # was doing it and stopped. It promoted as a habit, which is the
            # opposite of what it is.
            from memory.rhythms import is_spell
            if is_spell(h.get("dates") or []):
                continue
            h["rhythm"] = "recent" if w <= 14 else "regular"
            h["window"] = w
            out.append(h)

    out.sort(key=lambda x: (-x["days"], x["window"]))
    return out


# ── a weighty event: judged once ──────────────────────────────────────────────

def weigh(subject: str, pillar: str = "", sentiment: float = 0.0,
          flags: List[str] = None, dated: str = "") -> float:
    """Would this still matter in a month? 0 to 1.

    The model judges with the signals already computed rather than re-reading
    the conversation — it is scoring a summary, not parsing text, and the
    signals do most of the work. The dal arrives as GENERAL, +0.3, no flags,
    no date and scores low without anything having to reason about cooking.
    """
    flags = flags or []
    prompt = f"""Something came up in conversation with an elderly person.

  subject:   {subject}
  pillar:    {pillar or 'unknown'}
  sentiment: {sentiment:+.1f}
  flags:     {', '.join(flags) if flags else 'none'}
  dated:     {dated or 'no'}

Would a daughter ring her brother to tell him about this?

That is a concrete test, where "would this still matter in a month" was an
abstract one — and under it a plate of chole scored 1.00, the same as a knee
operation, while poha scored 0.00. The model was guessing at a life.

1.0   she would ring him about it — a diagnosis, an operation, a fall, a
      death, a wedding, someone moving away
0.7   she would mention it if he rang — a new medicine, a trip being
      planned, news about a grandchild
0.3   only if the conversation reached it — a film watched, a visitor
0.0   she would not think to say it — what she ate, the weather, a mood

If the subject is a FOOD or a DISH, the answer is 0.0, whatever the dish and
however it is written. A meal she liked is not news. If she eats it every
Sunday, repetition will find it without this.

Only the number."""

    try:
        from llm import ask
        raw = (ask(prompt, max_tokens=10) or "").strip()
        return max(0.0, min(1.0, float(raw.split()[0])))
    except Exception as e:
        print(f"[Promote] weigh failed for {subject!r}: {e}")
        return 0.0


def weighty(user_id: str, topics: List[Dict], flags: List[str] = None,
            dated: List[str] = None) -> List[Dict]:
    """Which of this session's subjects are worth a cluster on their own.

    Only asked about subjects that have no cluster already — an existing one
    needs no promoting, and a known subject coming up again is what
    reactivation handles.
    """
    if not topics:
        return []

    try:
        known = {str(r["label"]).lower() for r in
                 (_db().table("interest_clusters").select("label")
                  .eq("user_id", user_id).limit(200).execute()).data or []}
    except Exception:
        known = set()

    out = []
    for t in topics:
        subject = str(t.get("subject") or "").strip()
        low = subject.lower()
        if not subject or low in known:
            continue
        # A weak sentiment on a light pillar is not worth a model call.
        s = float(t.get("sentiment") or 0)
        pillar = t.get("pillar") or ""
        if abs(s) < 0.4 and pillar not in ("HEALTH_WELLNESS", "FAMILY"):
            continue

        score = weigh(subject, pillar, s, flags or [],
                      ", ".join(dated or []))
        if score >= WEIGHT_BAR:
            out.append({"subject": subject, "pillar": pillar,
                        "sentiment": s, "score": score})
    return out


# ── the pass ──────────────────────────────────────────────────────────────────

def review(user_id: str, dry_run: bool = True) -> Dict:
    """What would be promoted, and why. Writes nothing while dry_run.

    Report mode is not caution for its own sake: three days in fourteen is a
    guess, and a week of watching what it catches turns it into a measurement.
    """
    found = habits(user_id)

    print(f"\n[Promote] {user_id}: {len(found)} subject(s) at "
          f"{HABIT_DAYS}+ days in {HABIT_WINDOW}")
    for h in found:
        rhythm = ("spread out" if h["spread"] >= 7
                  else "clustered together")
        print(f"   {h['subject'][:26]:28} {h['days']} days, {rhythm}"
              f"  ({', '.join(d[5:] for d in h['dates'])})")

    if dry_run:
        if found:
            print("   (dry run — nothing written)")
        return {"habits": found, "promoted": 0}

    n = 0
    for h in found:
        # A cold said on three days is three days of a cold, not a liking.
        # "Sardi" became an interest with dishes attached this way.
        if _is_health(user_id, h["subject"]):
            print(f"[Promote] {h['subject']!r} skipped — a health matter, not a habit")
            continue
        if _promote(user_id, h["subject"], h):
            n += 1
    return {"habits": found, "promoted": n}


def _is_health(user_id: str, subject: str) -> bool:
    """Filed under health when she said it — the classifier already decided."""
    try:
        rows = (_db().table("subject_mentions").select("pillar")
                .eq("user_id", user_id).eq("subject", subject)
                .limit(20).execute()).data or []
        return any((r.get("pillar") or "") == "HEALTH_WELLNESS" for r in rows)
    except Exception as e:
        print(f"[Promote] health check failed for {subject!r}: {e}")
        return False


def _promote(user_id: str, subject: str, evidence: Dict) -> bool:
    """Make it a cluster, carrying the dates that earned it.

    The dates are the point. A cluster that knows it was mentioned on the
    4th, 9th and 14th can be offered back with a reason — "teen baar bana
    chuki hain is mahine" — where one that only knows a strength cannot.
    """
    try:
        from memory.profile_enricher import _upsert_cluster
        from classifier.pillar_classifier import embed_text
        cid = _upsert_cluster(
            user_id, subject, "GENERAL",
            # Earned over days rather than declared, so it starts modest and
            # grows the normal way from here.
            0.8,
            embed_text(subject),
            {"source": "habit", "kind": "interest",
             "promoted_on": date.today().isoformat(),
             "seen_on": evidence.get("dates", [])},
        )
        if cid:
            # Point the mentions at it, so the count stops being counted.
            # Without this a promoted subject stays unresolved and is offered
            # for promotion again every day — Rajesh had a cluster and was
            # still a candidate, because nothing ever filled cluster_id in.
            from memory.mentions import attach
            n = attach(user_id, subject, cid)
            print(f"[Promote] {subject!r} -> cluster "
                  f"({evidence['days']} days, {n} mentions attached)")
        return bool(cid)
    except Exception as e:
        print(f"[Promote] failed for {subject!r}: {e}")
        return False

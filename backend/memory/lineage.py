"""
LINEAGE — a concept and everything dated that hangs under it.

    Common cold   (archived — known, never offered)
     ├─ episode   5–14 Oct, mild, resolved
     └─ episode   3 Dec –   , mild, active
    Zoo
     ├─ visit     2 Oct
     └─ visit     20 Nov
    Knee pain     (lasting)
     └─ flare-up  10–15 Nov, moderate, resolved

Three kinds of dated record, each pointing at its concept:
    episodes     health_episodes.cluster_id     a span with a status
    occurrences  interest_clusters.parent_id    one dated moment (kind=event)
    day notes    memory_stm.tags                what was said that day

Nothing here decides what something is (concepts.py does) or when it
happened (events, episodes). This reads them back as one timeline, so
"kab", "pichli baar", "kitni baar" and "abhi bhi hai?" have one answer.
"""
from datetime import date, datetime, timezone
from typing import Dict, List, Optional


def _db():
    from supabase_store import get_client
    return get_client()


def _her_date(user_id: str, ts) -> Optional[date]:
    """A stored instant as her calendar day (India, not the server's UTC)."""
    if not ts:
        return None
    try:
        s = str(ts)
        if len(s) == 10:
            return date.fromisoformat(s)
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if not d.tzinfo:
            d = d.replace(tzinfo=timezone.utc)
        from memory.events import _their_time
        return _their_time(user_id, d).date()
    except Exception:
        return None


def _today(user_id: str) -> date:
    try:
        from memory.thread import _today as t
        return t(user_id)
    except Exception:
        return date.today()


def _d(x: Optional[date]) -> str:
    return x.strftime("%-d %b %Y") if x else "?"


def timeline(user_id: str, concept_id: str) -> Dict:
    """Everything dated under one concept, oldest first."""
    db = _db()
    out = {"concept": None, "episodes": [], "occurrences": [], "days": []}
    try:
        c = (db.table("interest_clusters").select("id,label,kind,status,attributes")
             .eq("id", concept_id).limit(1).execute()).data
        out["concept"] = c[0] if c else None
    except Exception:
        pass
    try:
        eps = (db.table("health_episodes").select("*").eq("user_id", user_id)
               .eq("cluster_id", concept_id).execute()).data or []
        for e in eps:
            e["_start"] = _her_date(user_id, e.get("first_reported"))
            e["_end"] = _her_date(user_id, e.get("resolved_at"))
        out["episodes"] = sorted(eps, key=lambda e: e["_start"] or date.min)
    except Exception as e:
        print(f"[Lineage] episodes read failed: {e}")
    try:
        occ = (db.table("interest_clusters")
               .select("id,label,happened_on,event_count,status,attributes")
               .eq("user_id", user_id).eq("parent_id", concept_id)
               .eq("kind", "event").execute()).data or []
        occ = [o for o in occ if (o.get("status") or "active") not in ("merged", "archived", "dropped")]
        for o in occ:
            o["_on"] = _her_date(user_id, o.get("happened_on"))
        out["occurrences"] = sorted(occ, key=lambda o: o["_on"] or date.min)
    except Exception as e:
        print(f"[Lineage] occurrences read failed: {e}")
    try:
        days = (db.table("memory_stm").select("happened_on,text")
                .eq("user_id", user_id).contains("tags", [concept_id])
                .execute()).data or []
        out["days"] = sorted(days, key=lambda r: str(r.get("happened_on")))
    except Exception:
        pass
    return out


def render(user_id: str, concept_id: str) -> str:
    """One block for the prompt: when, last time, how many, still going."""
    t = timeline(user_id, concept_id)
    c = t["concept"]
    if not c:
        return ""
    today = _today(user_id)
    eps, occ, days = t["episodes"], t["occurrences"], t["days"]
    if not eps and not occ and not days:
        return ""
    lines = [f"{c['label']}:"]

    if eps:
        flare = any((e.get("kind") or "") == "flare" for e in eps)
        noun = "flare-up" if flare else "time"
        lines.append(f"  {len(eps)} {noun}{'s' if len(eps) != 1 else ''} on record:")
        for e in eps[-6:]:
            s, en = e["_start"], e["_end"]
            # How it LAST closed: reopened and later "theek hai" is over.
            _h = [h for h in (e.get("history") or []) if isinstance(h, dict)]
            quiet = bool(_h) and "nothing said for a week" in str(_h[-1].get("what") or "")
            if e.get("status") == "resolved" and s and quiet:
                span = (f"{_d(s)}, last mentioned {_d(en)}, not mentioned since"
                        if en and en != s else f"{_d(s)}, not mentioned since")
            elif e.get("status") == "resolved" and s and en:
                span = f"{_d(s)} to {_d(en)} ({max(1, (en - s).days)} days), over"
            elif s:
                span = (f"since {_d(s)} (day {(today - s).days + 1}), "
                        f"{'getting better' if e.get('status') == 'improving' else 'still going'}")
            else:
                span = e.get("status") or ""
            lines.append(f"   - {span}, {e.get('level') or 'mild'}")
    if occ:
        last = occ[-1]["_on"]
        ago = (today - last).days if last else None
        when = ("today" if ago == 0 else "yesterday" if ago == 1
                else f"{ago} days ago" if ago is not None else "")
        lines.append(f"  {len(occ)} time{'s' if len(occ) != 1 else ''}: "
                     + ", ".join(_d(o["_on"]) for o in occ[-8:])
                     + (f". Last: {_d(last)} ({when})." if last else ""))
    if days and not eps and not occ:
        lines.append(f"  talked about on {len(days)} day{'s' if len(days) != 1 else ''}, "
                     f"last {days[-1].get('happened_on')}")
    return "\n".join(lines)


def with_history(user_id: str, limit: int = 30) -> List[Dict]:
    """Concepts that have a timeline (episodes or occurrences under them)."""
    db = _db()
    ids = set()
    try:
        for r in (db.table("health_episodes").select("cluster_id")
                  .eq("user_id", user_id).execute()).data or []:
            if r.get("cluster_id"):
                ids.add(r["cluster_id"])
    except Exception:
        pass
    try:
        for r in (db.table("interest_clusters").select("parent_id")
                  .eq("user_id", user_id).eq("kind", "event").execute()).data or []:
            if r.get("parent_id"):
                ids.add(r["parent_id"])
    except Exception:
        pass
    if not ids:
        return []
    try:
        rows = (db.table("interest_clusters").select("id,label,kind,status,attributes,last_event")
                .in_("id", list(ids)).execute()).data or []
    except Exception:
        return []
    rows.sort(key=lambda r: str(r.get("last_event") or ""), reverse=True)
    return rows[:limit]


_PICK: Dict[tuple, tuple] = {}


def concepts_in(user_id: str, text: str) -> List[str]:
    """Which concepts with a timeline her message is about. One model call,
    only when she has any, and kept for the same words."""
    import time
    text = (text or "").strip()
    if not text:
        return []
    key = (user_id, text.lower()[:300])
    hit = _PICK.get(key)
    if hit and time.time() - hit[1] < 3600:
        return hit[0]
    cands = with_history(user_id)
    if not cands:
        return []
    from memory.concepts import _attrs
    listing = "\n".join(
        f"{i + 1}. {c['label']}"
        + (f" ({_attrs(c).get('english')})" if _attrs(c).get("english")
           and str(_attrs(c).get("english")).lower() != c["label"].lower() else "")
        for i, c in enumerate(cands))
    picked = []
    try:
        from llm import ask
        a = (ask(f"""An elderly woman said to her companion: "{text[:400]}"

Things in her life that have a history (visits, illnesses, flare-ups):
{listing}

Is she talking about, or asking about, one of these — when it happened, how
often, the last time, whether it is still going? In any language: "sardi"
is the common cold, "chidiyaghar" is the zoo.

Usually it is one, or none. Name a second only if she plainly asks about
two things.

Answer with the number(s), comma-separated, or NONE.""", max_tokens=20) or "").upper()
        for tok in a.replace(",", " ").split():
            dgt = "".join(ch for ch in tok if ch.isdigit())
            if dgt and 1 <= int(dgt) <= len(cands):
                cid = cands[int(dgt) - 1]["id"]
                if cid not in picked:
                    picked.append(cid)
    except Exception as e:
        print(f"[Lineage] pick failed: {e}")
    _PICK[key] = (picked[:2], time.time())
    if len(_PICK) > 2000:
        _PICK.clear()
    return picked[:2]

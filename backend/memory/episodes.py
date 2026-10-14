"""
EPISODES — things that start, change and end.

Her memory had two shapes: facts that stay true (knee pain, BP, Kishore
Kumar) and events that happened once (aloo paratha on the 8th). A cold is
neither. It starts on a day, it is mild or not, it gets better or worse, and
then it is over.

Forced into the first shape it never ended: "sardi" sat in health.concerns
beside her knee from 5 October, and on the 14th — six days after "aaj theek
hai sardi" — she was asked "Sardi kaisi hai?" twice. Forced into the second
it was forgotten at once: an archived "Cold" event nobody read. And the habit
detector, seeing it mentioned on three days, made "Sardi" an interest with
dishes attached.

An episode is the third shape:

    started → (checked on, at a pace set by how serious it is)
            → improving / worse → resolved

HOW IT HEARS
One model call reads her message against what is open: is this a new
problem, and does it say anything about one already open — better, same,
worse, gone? In any language; nothing here matches words. It runs only when
the classifier put the message in health, or something is already open.

HOW OFTEN IT ASKS (by concern level)
    mild       a cold, a slight cough   next day, then every two days;
                                        closes itself after 7 quiet days
    moderate   fever, stomach upset,    within hours, then daily; worse, or
               pain that stops her day  still going after 3 days, and her
                                        caregiver is told
    serious    a fall, chest pain       alert_engine.alert_now already tells
                                        her caregiver at once; the episode
                                        keeps the record and checks later

At most one health question a day per problem. Long-term conditions are not
episodes — they are never "checked on".

WHAT IT CHANGES
Her profile shows what is open; history keeps what ended. A resolved
episode is removed from health.concerns, and the prompts are told plainly:
over — do not ask.

TABLE (run once in Supabase):

    create table if not exists health_episodes (
      id uuid primary key default gen_random_uuid(),
      user_id text not null,
      what text not null,            -- her words: "sardi"
      english text,                  -- "common cold"
      level text default 'mild',     -- mild | moderate | serious
      status text default 'active',  -- active | improving | resolved
      first_reported timestamptz default now(),
      last_mentioned timestamptz default now(),
      last_asked timestamptz,
      next_check timestamptz,
      resolved_at timestamptz,
      caregiver_told_at timestamptz,
      history jsonb default '[]'::jsonb,
      created_at timestamptz default now()
    );
    create index if not exists health_episodes_user on health_episodes(user_id, status);
"""
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

# When a moderate problem has gone on this long, or got worse, her caregiver
# hears about it. "auto" tells them; "off" does not. (Asking her first is a
# later step: it needs the answer to her question tracked.)
CAREGIVER_MODE = "auto"
MODERATE_DAYS = 3
QUIET_DAYS_TO_CLOSE = 7

_NEXT = {                      # hours until the next check
    ("mild", "new"): 20, ("mild", "same"): 48, ("mild", "better"): 48,
    ("mild", "worse"): 20, ("mild", "asked"): 48,
    ("moderate", "new"): 6, ("moderate", "same"): 20, ("moderate", "better"): 36,
    ("moderate", "worse"): 10, ("moderate", "asked"): 20,
    ("serious", "new"): 4, ("serious", "same"): 12, ("serious", "better"): 24,
    ("serious", "worse"): 4, ("serious", "asked"): 12,
}


def _db():
    from supabase_store import get_client
    return get_client()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _later(level: str, why: str) -> str:
    return (_now() + timedelta(hours=_NEXT.get((level, why), 24))).isoformat()


def open_episodes(user_id: str) -> List[Dict]:
    try:
        return (_db().table("health_episodes").select("*")
                .eq("user_id", user_id).neq("status", "resolved")
                .order("first_reported").execute()).data or []
    except Exception as e:
        print(f"[Episodes] read failed: {e}")
        return []


def recently_resolved(user_id: str, days: int = 14) -> List[Dict]:
    try:
        since = (_now() - timedelta(days=days)).isoformat()
        return (_db().table("health_episodes").select("*")
                .eq("user_id", user_id).eq("status", "resolved")
                .gte("resolved_at", since).execute()).data or []
    except Exception:
        return []


def _note(ep: Dict, what: str) -> List:
    h = ep.get("history") if isinstance(ep.get("history"), list) else []
    return (h + [{"at": _now().isoformat(), "what": what}])[-30:]


# ── hearing her ───────────────────────────────────────────────────────────────

def hear(user_id: str, text: str, said: str = "", pillar: str = "") -> Dict:
    """Read one message against what is open. Returns what changed.

    Runs when the classifier says health, or when something is open — a
    "theek hai" about a cold is not a health-sounding message on its own.
    """
    opened = open_episodes(user_id)
    if pillar != "HEALTH_WELLNESS" and not opened:
        return {}
    listed = "\n".join(f"{i + 1}. {e['what']} ({e.get('english') or ''}), "
                       f"{e.get('level')}, {e.get('status')}"
                       for i, e in enumerate(opened)) or "(none)"
    try:
        from llm import ask
        raw = ask(f"""An elderly person is talking to their companion, in any language.

The companion had just said: "{said or '(nothing)'}"
They said: "{text}"

Health problems of theirs that are currently open:
{listed}

1. Does the message say anything about an open problem? For each, one of:
   better (improving), same, worse, gone (they are fine now / it is over).
2. Does it report a NEW short-term health problem of THEIR OWN (a cold,
   cough, fever, upset stomach, a fall, sudden pain, an injury)? Not a
   long-term condition (knee pain, BP, diabetes), not someone else's, not a
   medicine they take, not tiredness or wanting rest.
   For each new one: what (their words), english (plain name), and level:
   mild (cold, slight cough), moderate (fever, vomiting, pain that stops
   their routine), serious (a fall, chest pain, breathlessness, confusion).

Return JSON only:
{{"updates": [{{"n": 1, "status": "better|same|worse|gone"}}],
  "new": [{{"what": "...", "english": "...", "level": "mild|moderate|serious"}}]}}
Empty lists when nothing applies.""", max_tokens=250) or ""
        i, j = raw.find("{"), raw.rfind("}")
        d = json.loads(raw[i:j + 1]) if i >= 0 else {}
    except Exception as e:
        print(f"[Episodes] hear failed: {e}")
        return {}

    changed = {"updated": [], "opened": []}
    for u in d.get("updates") or []:
        try:
            ep = opened[int(u.get("n")) - 1]
        except Exception:
            continue
        st = str(u.get("status") or "").lower()
        if st in ("better", "same", "worse", "gone"):
            _update(user_id, ep, st, text)
            changed["updated"].append((ep["what"], st))

    for n in d.get("new") or []:
        what = str(n.get("what") or "").strip()[:80]
        if not what:
            continue
        # Said again in other words is the same problem, not a second one.
        if any(_same_problem(what, n.get("english", ""), e) for e in opened):
            continue
        ep = _open(user_id, what, str(n.get("english") or "")[:80],
                   str(n.get("level") or "mild").lower(), text)
        if ep:
            changed["opened"].append((what, ep.get("level")))
    if changed["updated"] or changed["opened"]:
        print(f"[Episodes] {user_id}: {changed}")
    return changed


def _same_problem(what: str, english: str, ep: Dict) -> bool:
    try:
        from memory.judge import yes_no
        a = f"{what} ({english})" if english else what
        b = f"{ep['what']} ({ep.get('english') or ''})"
        return yes_no(f'Are "{a}" and "{b}" the same health problem, as an '
                      f'elderly person would describe it in any language?',
                      key=f"ep_same:{a.lower()}|{b.lower()}")
    except Exception:
        return False


def _open(user_id: str, what: str, english: str, level: str,
          text: str) -> Optional[Dict]:
    level = level if level in ("mild", "moderate", "serious") else "mild"
    row = {"user_id": user_id, "what": what, "english": english,
           "level": level, "status": "active",
           "first_reported": _now().isoformat(),
           "last_mentioned": _now().isoformat(),
           "next_check": _later(level, "new"),
           "history": [{"at": _now().isoformat(), "what": f"started: {text[:120]}"}]}
    try:
        ep = _db().table("health_episodes").insert(row).execute().data[0]
        print(f"[Episodes] {user_id}: opened {what!r} ({level})")
        return ep
    except Exception as e:
        print(f"[Episodes] open failed: {e}")
        return None


def _update(user_id: str, ep: Dict, status: str, text: str) -> None:
    level = ep.get("level") or "mild"
    upd = {"last_mentioned": _now().isoformat(),
           "history": _note(ep, f"{status}: {text[:120]}")}
    if status == "gone":
        upd.update({"status": "resolved", "resolved_at": _now().isoformat(),
                    "next_check": None})
    else:
        upd["status"] = "improving" if status == "better" else "active"
        upd["next_check"] = _later(level, status)
        if status == "worse" and level == "mild":
            upd["level"] = "moderate"
    try:
        _db().table("health_episodes").update(upd).eq("id", ep["id"]).execute()
    except Exception as e:
        print(f"[Episodes] update failed: {e}")
        return
    ep = {**ep, **upd}
    if status == "gone":
        _drop_from_profile(user_id, ep)
    elif status == "worse":
        _maybe_tell_caregiver(user_id, ep, reason="worse")


# ── keeping the profile current ───────────────────────────────────────────────

def _drop_from_profile(user_id: str, ep: Dict) -> None:
    """Over, so no longer a current concern. The episode keeps the history."""
    try:
        from memory.profile_store import get_user_profile
        from memory.judge import yes_no
        p = get_user_profile(user_id) or {}
        h = dict(p.get("health") or {})
        concerns = list(h.get("concerns") or [])
        keep = []
        for c in concerns:
            try:
                same = yes_no(f'Is the health note "{c}" about the same problem '
                              f'as "{ep["what"]}" ({ep.get("english") or ""})?',
                              key=f"ep_drop:{str(c).lower()}|{ep['what'].lower()}")
            except Exception:
                same = False
            if not same:
                keep.append(c)
        if len(keep) != len(concerns):
            h["concerns"] = keep
            _db().table("user_profile").update({"health": h}) \
                .eq("user_id", user_id).execute()
            print(f"[Episodes] {user_id}: {ep['what']!r} removed from concerns")
    except Exception as e:
        print(f"[Episodes] profile update failed: {e}")


def sweep(user_id: str) -> None:
    """Close what has gone quiet; tell her caregiver what has gone on too long."""
    for ep in open_episodes(user_id):
        last = _ts(ep.get("last_mentioned")) or _now()
        first = _ts(ep.get("first_reported")) or _now()
        level = ep.get("level") or "mild"
        if level == "mild" and (_now() - last).days >= QUIET_DAYS_TO_CLOSE:
            try:
                _db().table("health_episodes").update({
                    "status": "resolved", "resolved_at": _now().isoformat(),
                    "next_check": None,
                    "history": _note(ep, "closed: nothing said for a week")}) \
                    .eq("id", ep["id"]).execute()
                _drop_from_profile(user_id, ep)
                print(f"[Episodes] {user_id}: {ep['what']!r} closed after a quiet week")
            except Exception as e:
                print(f"[Episodes] sweep failed: {e}")
        elif level in ("moderate", "serious") and ep.get("status") == "active" \
                and (_now() - first).days >= MODERATE_DAYS:
            _maybe_tell_caregiver(user_id, ep, reason="still going")


def _maybe_tell_caregiver(user_id: str, ep: Dict, reason: str) -> None:
    if CAREGIVER_MODE != "auto" or ep.get("caregiver_told_at"):
        return
    if (ep.get("level") or "mild") == "mild":
        return
    try:
        from memory.alert_engine import get_caregivers_for_user, send_email_alert, log_alert
        from memory.profile_store import get_user_profile
        prof = get_user_profile(user_id) or {}
        first = _ts(ep.get("first_reported"))
        since = first.strftime("%-d %b") if first else ""
        summary = (f"{ep['what']} ({ep.get('english') or ''}) since {since} — "
                   f"{'getting worse' if reason == 'worse' else 'not better after ' + str(MODERATE_DAYS) + ' days'}")
        last_words = ""
        hist = ep.get("history") if isinstance(ep.get("history"), list) else []
        if hist:
            last_words = str(hist[-1].get("what") or "").split(": ", 1)[-1]
        sent = False
        for link in get_caregivers_for_user(user_id):
            cg = link.get("caregivers") or {}
            if not cg.get("email"):
                continue
            ok = send_email_alert(
                to_email=cg["email"], caregiver_name=cg.get("name") or "",
                user_name=prof.get("name") or user_id,
                alerts=[{"type": "health_episode", "severity": "high",
                         "summary": summary, "quote": last_words}],
                user_id=user_id)
            log_alert(user_id, cg.get("id") or link.get("caregiver_id") or "",
                      {"alert_type": "health_episode", "severity": "high",
                       "message": summary, "pillar": "HEALTH_WELLNESS"}, ok)
            sent = ok or sent
        _db().table("health_episodes").update({
            "caregiver_told_at": _now().isoformat(),
            "history": _note(ep, f"caregiver told ({reason})")}) \
            .eq("id", ep["id"]).execute()
        print(f"[Episodes] {user_id}: caregiver told about {ep['what']!r} ({reason}, sent={sent})")
    except Exception as e:
        print(f"[Episodes] caregiver notice failed: {e}")


# ── what the companion is told ────────────────────────────────────────────────

def due(user_id: str) -> Optional[Dict]:
    """The one open problem it is time to ask about, if any. Never twice in a day."""
    best = None
    rank = {"serious": 0, "moderate": 1, "mild": 2}
    for ep in open_episodes(user_id):
        nc = _ts(ep.get("next_check"))
        la = _ts(ep.get("last_asked"))
        if not nc or nc > _now():
            continue
        if la and (_now() - la) < timedelta(hours=18):
            continue
        if best is None or rank.get(ep.get("level"), 3) < rank.get(best.get("level"), 3):
            best = ep
    return best


def prompt_note(user_id: str) -> str:
    """Plain lines for any prompt that might mention her health."""
    try:
        sweep(user_id)
    except Exception:
        pass
    opened = open_episodes(user_id)
    done = recently_resolved(user_id)
    if not opened and not done:
        return ""
    d = due(user_id)
    lines = []
    for ep in opened:
        first = _ts(ep.get("first_reported"))
        since = first.strftime("%-d %b") if first else "recently"
        st = {"active": "ongoing", "improving": "getting better"}.get(ep.get("status"), "ongoing")
        if d and d["id"] == ep["id"]:
            how = ("CHECK-IN DUE: you may ask once, gently and in passing, how it "
                   "is now — one question, nothing else about health.")
        else:
            how = "Not due — do not ask about it; respond warmly if they raise it."
        lines.append(f"- {ep['what']} ({ep.get('english') or ''}): {ep.get('level')}, "
                     f"since {since}, {st}. {how}")
    for ep in done:
        r = _ts(ep.get("resolved_at"))
        lines.append(f"- {ep['what']} ({ep.get('english') or ''}): OVER since "
                     f"{r.strftime('%-d %b') if r else 'recently'}. Do not ask about it. "
                     f"Only talk about it if they bring it up.")
    return ("\nHEALTH RIGHT NOW — short-term problems they told you about. This "
            "overrides anything else in these notes about them:\n" + "\n".join(lines) +
            "\nLong-term conditions (knee, BP, thyroid) are never checked on.\n")


def mark_asked_if(user_id: str, message: str) -> None:
    """After a message goes out: if it asked about the problem that was due,
    remember that it was asked, so it is not asked again today."""
    d = due(user_id)
    if not d or not (message or "").strip():
        return
    try:
        from memory.judge import yes_no
        asked = yes_no(f'Message: "{message[:400]}"\n\nDoes this message ask the '
                       f'person how their {d["what"]} ({d.get("english") or ""}) is?',
                       key=f"ep_asked:{d['id']}:{hash(message)}")
    except Exception:
        return
    if asked:
        try:
            _db().table("health_episodes").update({
                "last_asked": _now().isoformat(),
                "next_check": _later(d.get("level") or "mild", "asked")}) \
                .eq("id", d["id"]).execute()
            print(f"[Episodes] {user_id}: asked about {d['what']!r}")
        except Exception as e:
            print(f"[Episodes] mark asked failed: {e}")

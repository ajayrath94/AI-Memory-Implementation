"""
LISTS — what she is keeping track of.

She said she was going to the market for Navratri, and the companion
offered: "kuch cheezein aap mere saath share kar sakti hain." There was
nowhere for them to go. It offered something it could not do.

And a list is a good fit for her. She is going out, she is writing one on
paper, and what she would actually want is to say "sabudana bhi likh lena"
over the course of a morning and have it there when she leaves.

NOT A REMINDER
A reminder is a time. A list is a set of things with no time, added to
through a day and crossed off. The reminder engine already exists and this
is not it.

THE SHAPE GROWS AS SHE TALKS
An item starts as a word — "sabudana". Then "do kilo sabudana" gives it a
quantity, "yeh Big Bazaar se" gives it a place. Nothing is defined up
front: the fields are whatever she happened to say, in her own words, and
the UI shows whatever keys turned up.

Which is why fields is JSON and not columns. A shopping list and a list of
questions for her doctor have nothing in common except that both are lists.

ONE LIST AT A TIME, MOSTLY
Several named lists is an app feature. One running list is how people work.
So a new list does not close the old one — she may well have a market list
and a doctor list — but reading without naming one gives her the most
recent, which is almost always what she means.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional


def _db():
    from supabase_store import get_client
    return get_client()


def _active(user_id: str) -> List[Dict]:
    try:
        return (_db().table("lists").select("*")
                .eq("user_id", user_id).is_("closed_at", "null")
                .order("created_at", desc=True).limit(10).execute()).data or []
    except Exception as e:
        print(f"[Lists] read failed: {e}")
        return []


def _find(user_id: str, name: str = "") -> Optional[Dict]:
    """The list she means. The named one, or the most recent."""
    rows = _active(user_id)
    if not rows:
        return None
    if not name:
        return rows[0]
    want = name.strip().lower()
    for r in rows:
        if str(r.get("name") or "").strip().lower() == want:
            return r
    # A loose match, because she will not use the same word twice —
    # "bazar ki list" and "market list" are the same list.
    for r in rows:
        nm = str(r.get("name") or "").strip().lower()
        if want in nm or nm in want:
            return r
    return None


def create(user_id: str, name: str, purpose: str = "",
           expires_on: str = "") -> Optional[Dict]:
    """Start one. Usually because she named something to go on it."""
    nm = (name or "").strip()[:80]
    if not nm:
        return None
    try:
        row = _db().table("lists").insert({
            "user_id": user_id,
            "name": nm,
            "purpose": (purpose or "")[:200],
            "expires_on": expires_on or None,
        }).execute().data[0]
        print(f"[Lists] {user_id}: started {nm!r}")
        return row
    except Exception as e:
        print(f"[Lists] create failed: {e}")
        return None


def add(user_id: str, what: str, fields: Dict = None,
        list_name: str = "") -> Dict:
    """Put something on a list, starting one if there is none.

    fields is whatever else she said about it — a quantity, a shop, a
    note — in her own words as keys.
    """
    what = (what or "").strip()
    if not what:
        return {"ok": False, "why": "nothing to add"}

    lst = _find(user_id, list_name)
    if not lst:
        lst = create(user_id, list_name or "list")
        if not lst:
            return {"ok": False, "why": "could not start a list"}

    body = {"what": what[:120]}
    for k, v in (fields or {}).items():
        k = str(k).strip()[:40]
        if k and k != "what" and str(v).strip():
            body[k] = str(v).strip()[:120]

    try:
        _db().table("list_items").insert({
            "list_id": lst["id"], "fields": body,
        }).execute()
        print(f"[Lists] {user_id}: + {body} -> {lst['name']!r}")
        return {"ok": True, "list": lst["name"], "added": body}
    except Exception as e:
        print(f"[Lists] add failed: {e}")
        return {"ok": False, "why": str(e)[:80]}


def items(user_id: str, list_name: str = "",
          include_done: bool = False) -> List[Dict]:
    lst = _find(user_id, list_name)
    if not lst:
        return []
    try:
        q = (_db().table("list_items").select("*")
             .eq("list_id", lst["id"]).order("created_at"))
        rows = q.execute().data or []
    except Exception as e:
        print(f"[Lists] items failed: {e}")
        return []
    if not include_done:
        rows = [r for r in rows if not r.get("done")]
    return rows


def read(user_id: str, list_name: str = "") -> Dict:
    """A list, ready to be read back to her."""
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    rows = items(user_id, list_name, include_done=True)
    left = [r for r in rows if not r.get("done")]
    return {
        "ok": True,
        "name": lst.get("name"),
        "purpose": lst.get("purpose"),
        "items": [r.get("fields") or {} for r in left],
        "done": [(r.get("fields") or {}).get("what") for r in rows
                 if r.get("done")],
        "total": len(rows),
    }


def tick(user_id: str, what: str, list_name: str = "") -> Dict:
    """She has got it. Not deleted — crossed off, which is different."""
    want = (what or "").strip().lower()
    if not want:
        return {"ok": False, "why": "nothing named"}
    for r in items(user_id, list_name):
        f = r.get("fields") or {}
        if want in str(f.get("what") or "").lower():
            try:
                _db().table("list_items").update({"done": True}) \
                    .eq("id", r["id"]).execute()
                print(f"[Lists] {user_id}: ticked {f.get('what')!r}")
                return {"ok": True, "ticked": f.get("what")}
            except Exception as e:
                return {"ok": False, "why": str(e)[:80]}
    return {"ok": False, "why": f"{what} is not on it"}


def close(user_id: str, list_name: str = "") -> Dict:
    """Done with. The items stay — a market list is worth seeing again
    next month, and she will want the same things."""
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    try:
        _db().table("lists").update(
            {"closed_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", lst["id"]).execute()
        print(f"[Lists] {user_id}: closed {lst['name']!r}")
        return {"ok": True, "closed": lst["name"]}
    except Exception as e:
        return {"ok": False, "why": str(e)[:80]}


def sweep(user_id: str) -> int:
    """Close what has expired. On the heartbeat.

    A market list dies when she gets back; a list of questions for her
    doctor lives until the appointment. Both are better closed than left to
    accumulate until the companion is reading out a fortnight of sabudana.
    """
    n = 0
    today = date.today()
    for lst in _active(user_id):
        exp = lst.get("expires_on")
        if not exp:
            # Nothing said. A list nobody has touched in a fortnight is
            # finished whether she said so or not.
            try:
                made = datetime.fromisoformat(
                    str(lst["created_at"]).replace("Z", "+00:00")).date()
                if (today - made).days < 14:
                    continue
            except Exception:
                continue
        else:
            try:
                if date.fromisoformat(str(exp)[:10]) >= today:
                    continue
            except Exception:
                continue
        close(user_id, lst.get("name") or "")
        n += 1
    return n


def hint(user_id: str) -> str:
    """One line for the composer, when she has something open.

    Not read out unprompted — a companion that recites a shopping list
    every morning is a nuisance. This is so it KNOWS, and can say "sabudana
    bhi list mein hai" when the market comes up.
    """
    rows = _active(user_id)
    if not rows:
        return ""
    lst = rows[0]
    left = items(user_id, lst.get("name") or "")
    if not left:
        return ""
    what = [str((r.get("fields") or {}).get("what") or "") for r in left]
    return (f"\n\nShe has a list open — {lst.get('name')}: "
            f"{', '.join(w for w in what if w)[:200]}. "
            f"Do not read it back to her unless she asks or it is plainly "
            f"relevant. Knowing it is there is the point.")

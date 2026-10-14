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
the screen shows whatever keys turned up (Field 1, Field 2, ... on the
whiteboard — `columns()` below works them out).

SEVERAL LISTS, ONE AT A TIME
She may well have a market list and a packing list open together. Naming
one gets that one; not naming one gets the most recent, which is almost
always what she means.

THE KEY
Every list is known by the day it was started and what it is for —
"13-Oct-26 · bazar". Two market lists a week apart are different lists,
and that is how she would tell them apart on paper too.

STORE OR DROP
Finishing a list asks her: rakh lein agli baar ke liye, ya hata dein?
Kept lists are closed but stay, and can be started again next time —
next Navratri's list begins as this one. Dropped lists are gone.

READING IT OUT IN A SHOP
read() gives the whole list, which is right at home and useless in an
aisle. There she wants one thing, then "mil gaya" and the next. "Mil gaya"
names nothing, so the list remembers what it last read out
(last_read_item_id) and when (last_read_at). After 90 minutes without a
word the walk is over on its own — otherwise a "ho gaya" tomorrow about
something else entirely would tick off whatever she heard last.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

WALK_MINUTES = 90          # a walk nobody has touched for this long is over
STALE_DAYS = 14            # an untouched list with no expiry closes itself


def _db():
    from supabase_store import get_client
    return get_client()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _clean_date(s) -> Optional[str]:
    """A YYYY-MM-DD the database will take, or nothing."""
    if not s:
        return None
    try:
        return date.fromisoformat(str(s).strip()[:10]).isoformat()
    except Exception:
        return None


def key(lst: Dict) -> str:
    """The readable key: '13-Oct-26 · bazar'."""
    d = _parse_ts(lst.get("created_at"))
    day = d.strftime("%d-%b-%y") if d else "?"
    return f"{day} · {lst.get('name') or 'list'}"


def _what(row: Dict) -> str:
    return str((row.get("fields") or {}).get("what") or "")


# ── finding lists ────────────────────────────────────────────────────────────

def _active(user_id: str) -> List[Dict]:
    try:
        return (_db().table("lists").select("*")
                .eq("user_id", user_id).is_("closed_at", "null")
                .order("created_at", desc=True).limit(10).execute()).data or []
    except Exception as e:
        print(f"[Lists] read failed: {e}")
        return []


def _kept_rows(user_id: str, limit: int = 20) -> List[Dict]:
    try:
        return (_db().table("lists").select("*")
                .eq("user_id", user_id).not_.is_("closed_at", "null")
                .order("closed_at", desc=True).limit(limit).execute()).data or []
    except Exception as e:
        print(f"[Lists] kept read failed: {e}")
        return []


def _match(rows: List[Dict], name: str) -> Optional[Dict]:
    want = (name or "").strip().lower()
    if not want:
        return rows[0] if rows else None
    for r in rows:
        if str(r.get("name") or "").strip().lower() == want:
            return r
    for r in rows:
        if key(r).lower() == want:
            return r
    # A loose match, because she will not use the same word twice —
    # "bazar ki list" and "bazar" are the same list.
    for r in rows:
        nm = str(r.get("name") or "").strip().lower()
        if nm and (want in nm or nm in want):
            return r
    return None


def _find(user_id: str, name: str = "") -> Optional[Dict]:
    """The open list she means. The named one, or the most recent."""
    return _match(_active(user_id), name)


def get(user_id: str, list_id: str) -> Optional[Dict]:
    """A list by id, only if it is hers. Open or kept."""
    try:
        rows = (_db().table("lists").select("*")
                .eq("id", list_id).eq("user_id", user_id)
                .limit(1).execute()).data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[Lists] get failed: {e}")
        return None


def _items_of(list_id: str, include_done: bool = True) -> List[Dict]:
    try:
        rows = (_db().table("list_items").select("*")
                .eq("list_id", list_id).order("created_at")
                .execute()).data or []
    except Exception as e:
        print(f"[Lists] items failed: {e}")
        return []
    return rows if include_done else [r for r in rows if not r.get("done")]


def _counts(list_ids: List[str]) -> Dict[str, Dict[str, int]]:
    if not list_ids:
        return {}
    try:
        rows = (_db().table("list_items").select("list_id,done")
                .in_("list_id", list_ids).execute()).data or []
    except Exception:
        rows = []
    out: Dict[str, Dict[str, int]] = {}
    for r in rows:
        c = out.setdefault(r["list_id"], {"total": 0, "left": 0})
        c["total"] += 1
        if not r.get("done"):
            c["left"] += 1
    return out


def columns(rows: List[Dict]) -> List[str]:
    """The columns this list turns out to have: `what` first, then the
    keys she used, commonest first so a key on one item does not push
    `kitna` across the row."""
    counts: Dict[str, int] = {}
    for it in rows:
        for k in (it.get("fields") or {}):
            if k != "what":
                counts[k] = counts.get(k, 0) + 1
    return ["what"] + sorted(counts, key=lambda k: (-counts[k], k))


def _card(lst: Dict, c: Dict[str, int]) -> Dict:
    return {
        "id": lst["id"],
        "key": key(lst),
        "name": lst.get("name"),
        "purpose": lst.get("purpose") or "",
        "created_at": lst.get("created_at"),
        "expires_on": lst.get("expires_on"),
        "closed_at": lst.get("closed_at"),
        "total": c.get("total", 0),
        "left": c.get("left", 0),
    }


def overview(user_id: str, with_kept: bool = True) -> Dict:
    """Every list she has: open ones first, then the kept ones."""
    open_ = _active(user_id)
    kept = _kept_rows(user_id) if with_kept else []
    c = _counts([l["id"] for l in open_ + kept])
    return {
        "open": [_card(l, c.get(l["id"], {})) for l in open_],
        "kept": [_card(l, c.get(l["id"], {})) for l in kept],
    }


def detail(user_id: str, list_id: str) -> Optional[Dict]:
    lst = get(user_id, list_id)
    if not lst:
        return None
    rows = _items_of(lst["id"])
    c = {"total": len(rows), "left": sum(1 for r in rows if not r.get("done"))}
    out = _card(lst, c)
    out["columns"] = columns(rows)
    out["items"] = [{
        "id": r["id"],
        "fields": r.get("fields") or {},
        "done": bool(r.get("done")),
        "created_at": r.get("created_at"),
    } for r in rows]
    return out


# ── making and adding ────────────────────────────────────────────────────────

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
            "expires_on": _clean_date(expires_on),
        }).execute().data[0]
        print(f"[Lists] {user_id}: started {key(row)!r}")
        return row
    except Exception as e:
        print(f"[Lists] create failed: {e}")
        return None


def _clean_fields(what: str, fields: Dict = None) -> Dict:
    body = {"what": what.strip()[:120]}
    for k, v in (fields or {}).items():
        k = str(k).strip()[:40]
        if k and k != "what" and v is not None and str(v).strip():
            body[k] = str(v).strip()[:120]
    return body


def add_item(list_id: str, what: str, fields: Dict = None) -> Optional[Dict]:
    """Straight onto a known list. The screen uses this — it knows exactly
    which list is open, and name matching is for conversation."""
    what = (what or "").strip()
    if not what:
        return None
    body = _clean_fields(what, fields)
    try:
        row = _db().table("list_items").insert({
            "list_id": list_id, "fields": body}).execute().data[0]
        return row
    except Exception as e:
        print(f"[Lists] add failed: {e}")
        return None


def set_expiry(user_id: str, expires_on: str, list_name: str = "") -> Dict:
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    d = _clean_date(expires_on)
    try:
        _db().table("lists").update({"expires_on": d}).eq("id", lst["id"]).execute()
    except Exception as e:
        return {"ok": False, "why": str(e)[:80]}
    return {"ok": True, "list": key(lst), "expires_on": d}


def add(user_id: str, what: str, fields: Dict = None,
        list_name: str = "", expires_on: str = "",
        purpose: str = "") -> Dict:
    """Put something on a list, starting one if there is none.

    fields is whatever else she said about it — a quantity, a shop, a
    note — in her own words as keys.
    """
    what = (what or "").strip()
    if not what:
        return {"ok": False, "why": "nothing to add"}

    started = False
    lst = _find(user_id, list_name)
    if not lst:
        lst = create(user_id, list_name or "list", purpose, expires_on)
        if not lst:
            return {"ok": False, "why": "could not start a list"}
        started = True
    elif expires_on and _clean_date(expires_on) != lst.get("expires_on"):
        set_expiry(user_id, expires_on, lst.get("name") or "")

    # Said twice is not wanted twice. If it is already on and not crossed
    # off, the new words become more about the same thing.
    for r in _items_of(lst["id"], include_done=False):
        if _what(r).strip().lower() == what.lower():
            merged = dict(r.get("fields") or {})
            merged.update({k: v for k, v in _clean_fields(what, fields).items()
                           if k != "what"})
            try:
                _db().table("list_items").update({"fields": merged}) \
                    .eq("id", r["id"]).execute()
            except Exception as e:
                return {"ok": False, "why": str(e)[:80]}
            return {"ok": True, "list": lst["name"], "key": key(lst),
                    "already_there": True, "item": merged}

    row = add_item(lst["id"], what, fields)
    if not row:
        return {"ok": False, "why": "could not add"}
    print(f"[Lists] {user_id}: + {row.get('fields')} -> {key(lst)!r}")
    out = {"ok": True, "list": lst["name"], "key": key(lst),
           "added": row.get("fields")}
    if started:
        out["started_new_list"] = True
    return out


# ── reading ──────────────────────────────────────────────────────────────────

def items(user_id: str, list_name: str = "",
          include_done: bool = False) -> List[Dict]:
    lst = _find(user_id, list_name)
    return _items_of(lst["id"], include_done) if lst else []


def read(user_id: str, list_name: str = "") -> Dict:
    """A list, ready to be read back to her. Reading the whole thing ends
    any one-at-a-time walk."""
    lst = _find(user_id, list_name)
    if not lst:
        others = _kept_rows(user_id, 3)
        return {"ok": False, "why": "no open list",
                "kept_lists": [key(l) for l in others]}
    _set_cursor(lst["id"], None)
    rows = _items_of(lst["id"])
    left = [r for r in rows if not r.get("done")]
    out = {
        "ok": True,
        "name": lst.get("name"),
        "key": key(lst),
        "purpose": lst.get("purpose"),
        "expires_on": lst.get("expires_on"),
        "items": [r.get("fields") or {} for r in left],
        "done": [_what(r) for r in rows if r.get("done")],
        "total": len(rows),
    }
    others = [key(l) for l in _active(user_id) if l["id"] != lst["id"]]
    if others:
        out["other_open_lists"] = others
    return out


def read_all(user_id: str) -> Dict:
    """'Meri saari lists' — the names and how much is left, not the items."""
    ov = overview(user_id, with_kept=False)
    if not ov["open"]:
        return {"ok": False, "why": "no open lists",
                "kept_lists": [key(l) for l in _kept_rows(user_id, 3)]}
    return {"ok": True, "lists": [
        {"key": c["key"], "left": c["left"], "total": c["total"]}
        for c in ov["open"]]}


def kept(user_id: str) -> Dict:
    ov = overview(user_id)
    return {"ok": True, "kept": [
        {"key": c["key"], "items": c["total"]} for c in ov["kept"]]}


# ── crossing off and putting back ────────────────────────────────────────────

def _set_done(item_id: str, done: bool) -> bool:
    try:
        _db().table("list_items").update({"done": done}) \
            .eq("id", item_id).execute()
        return True
    except Exception as e:
        print(f"[Lists] tick write failed: {e}")
        return False


def _pick(rows: List[Dict], what: str) -> Optional[Dict]:
    want = (what or "").strip().lower()
    if not want:
        return None
    for r in rows:
        if _what(r).strip().lower() == want:
            return r
    for r in rows:
        w = _what(r).lower()
        if want in w or (w and w in want):
            return r
    # Not the same letters — ask which one she means. "ककड़ी" said aloud is
    # the "kakdi" she typed; "kheera" may be it too. Spelling matched none of
    # them, so "do kilo kakdi le aayi" ticked nothing.
    return _pick_by_meaning(rows, what)


def _pick_by_meaning(rows: List[Dict], what: str) -> Optional[Dict]:
    if not rows:
        return None
    listed = "\n".join(f"{i + 1}. {_what(r)}" for i, r in enumerate(rows))
    try:
        from llm import ask
        got = (ask(f"""Items on someone's list:
{listed}

They said: "{what}"

Which ONE item do they mean? The same thing in another script, spelling or
language counts (ककड़ी is kakdi; tarbuz is tarbooz). Reply with its number
only, or NONE if it is not on the list.""", max_tokens=5) or "").strip().upper()
    except Exception as e:
        print(f"[Lists] meaning match failed: {e}")
        return None
    num = "".join(ch for ch in got.split()[0] if ch.isdigit()) if got else ""
    if num and 1 <= int(num) <= len(rows):
        r = rows[int(num) - 1]
        print(f"[Lists] {what!r} -> {_what(r)!r} (by meaning)")
        return r
    return None


def tick(user_id: str, what: str, list_name: str = "") -> Dict:
    """She has got it. Not deleted — crossed off, which is different."""
    if not (what or "").strip():
        return {"ok": False, "why": "nothing named"}
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    r = _pick(_items_of(lst["id"], include_done=False), what)
    if not r:
        return {"ok": False, "not_found": what,
                "why": f"{what} is not on it (or already crossed off)"}
    if not _set_done(r["id"], True):
        return {"ok": False, "why": "could not save"}
    print(f"[Lists] {user_id}: ticked {_what(r)!r}")
    out = {"ok": True, "ticked": _what(r), "list": key(lst)}
    # Named the very thing she was just read — carry the walk on.
    if _cursor_live(lst) and str(lst.get("last_read_item_id")) == str(r["id"]):
        nxt = next_item(user_id, lst.get("name") or "")
        out.update({"next": nxt.get("item"), "done": nxt.get("done", False),
                    "left": nxt.get("left", 0)})
    return out


def untick(user_id: str, what: str = "", list_name: str = "") -> Dict:
    """Put it back. A finger on a phone lands on the wrong row, and "nahi,
    woh abhi nahi liya" has to have somewhere to go."""
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    done = [r for r in _items_of(lst["id"]) if r.get("done")]
    if not done:
        return {"ok": False, "why": "nothing is crossed off"}
    if (what or "").strip():
        r = _pick(done, what)
    else:
        # No name: only safe when there is exactly one crossed off.
        if len(done) > 1:
            return {"ok": False, "why": "which one? several are crossed off",
                    "crossed_off": [_what(d) for d in done]}
        r = done[0]
    if not r:
        return {"ok": False, "not_found": what, "why": f"{what} is not crossed off"}
    if not _set_done(r["id"], False):
        return {"ok": False, "why": "could not save"}
    print(f"[Lists] {user_id}: unticked {_what(r)!r}")
    return {"ok": True, "put_back": _what(r), "list": key(lst)}


def tick_all(user_id: str, list_name: str = "") -> Dict:
    """Everything at once. "Sab le liya" is how someone talks after a shop,
    not four separate confirmations."""
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    left = _items_of(lst["id"], include_done=False)
    if not left:
        return {"ok": False, "why": "nothing left on it"}
    done = [_what(r) for r in left if _set_done(r["id"], True)]
    _set_cursor(lst["id"], None)
    print(f"[Lists] {user_id}: ticked {len(done)} item(s)")
    return {"ok": True, "ticked": done, "list": key(lst)}


def set_item_done(user_id: str, list_id: str, item_id: str, done: bool) -> bool:
    """For the screen: by id, only within her own list."""
    if not get(user_id, list_id):
        return False
    try:
        rows = (_db().table("list_items").update({"done": bool(done)})
                .eq("id", item_id).eq("list_id", list_id).execute()).data
        return bool(rows)
    except Exception as e:
        print(f"[Lists] set_item_done failed: {e}")
        return False


# ── changing and removing ────────────────────────────────────────────────────

def change(user_id: str, what: str, new_what: str = "",
           fields: Dict = None, list_name: str = "") -> Dict:
    """'Do kilo nahi, ek kilo' — the item stays, what she said about it
    changes. A field given as empty is dropped."""
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    r = _pick(_items_of(lst["id"]), what)
    if not r:
        return {"ok": False, "not_found": what, "why": f"{what} is not on it"}
    f = dict(r.get("fields") or {})
    if (new_what or "").strip():
        f["what"] = new_what.strip()[:120]
    for k, v in (fields or {}).items():
        k = str(k).strip()[:40]
        if not k or k == "what":
            continue
        if v is None or not str(v).strip():
            f.pop(k, None)
        else:
            f[k] = str(v).strip()[:120]
    try:
        _db().table("list_items").update({"fields": f}).eq("id", r["id"]).execute()
    except Exception as e:
        return {"ok": False, "why": str(e)[:80]}
    return {"ok": True, "now": f, "list": key(lst)}


def edit_item(user_id: str, list_id: str, item_id: str, fields: Dict) -> Optional[Dict]:
    """For the screen: replace an item's fields wholesale."""
    if not get(user_id, list_id):
        return None
    what = str((fields or {}).get("what") or "").strip()
    if not what:
        return None
    body = _clean_fields(what, {k: v for k, v in fields.items() if k != "what"})
    try:
        rows = (_db().table("list_items").update({"fields": body})
                .eq("id", item_id).eq("list_id", list_id).execute()).data
        return body if rows else None
    except Exception as e:
        print(f"[Lists] edit failed: {e}")
        return None


def remove(user_id: str, what: str, list_name: str = "") -> Dict:
    """Actually gone — for "woh hata do, galti se bola". Crossing off is
    the normal thing; this is for things that should never have been on."""
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    r = _pick(_items_of(lst["id"]), what)
    if not r:
        return {"ok": False, "not_found": what, "why": f"{what} is not on it"}
    if str(lst.get("last_read_item_id")) == str(r["id"]):
        _set_cursor(lst["id"], None)
    try:
        _db().table("list_items").delete().eq("id", r["id"]).execute()
    except Exception as e:
        return {"ok": False, "why": str(e)[:80]}
    print(f"[Lists] {user_id}: removed {_what(r)!r}")
    return {"ok": True, "removed": _what(r), "list": key(lst)}


def remove_item(user_id: str, list_id: str, item_id: str) -> bool:
    lst = get(user_id, list_id)
    if not lst:
        return False
    if str(lst.get("last_read_item_id")) == str(item_id):
        _set_cursor(list_id, None)
    try:
        rows = (_db().table("list_items").delete()
                .eq("id", item_id).eq("list_id", list_id).execute()).data
        return bool(rows)
    except Exception as e:
        print(f"[Lists] remove_item failed: {e}")
        return False


# ── finishing, keeping, starting again ───────────────────────────────────────

def _close_row(lst: Dict, keep: bool) -> None:
    if keep:
        _db().table("lists").update({
            "closed_at": _now().isoformat(),
            "last_read_item_id": None, "last_read_at": None,
        }).eq("id", lst["id"]).execute()
    else:
        _db().table("list_items").delete().eq("list_id", lst["id"]).execute()
        _db().table("lists").delete().eq("id", lst["id"]).execute()


def close(user_id: str, list_name: str = "", keep: bool = True) -> Dict:
    """Done with. She decides whether it stays.

    The companion asks — rakh lein agli baar ke liye, ya hata dein — and
    keeping is the default, because dropping something she did not ask to
    drop is the worse mistake. A kept list also accumulates a record of an
    elderly woman's errands and her medical questions, which is why she is
    asked rather than it being assumed.
    """
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    try:
        _close_row(lst, keep)
        print(f"[Lists] {user_id}: closed {key(lst)!r}"
              + ("" if keep else ", dropped"))
        return {"ok": True, "closed": key(lst), "kept": keep}
    except Exception as e:
        return {"ok": False, "why": str(e)[:80]}


def close_by_id(user_id: str, list_id: str, keep: bool = True) -> bool:
    lst = get(user_id, list_id)
    if not lst:
        return False
    try:
        if keep and lst.get("closed_at"):
            return True                       # already kept
        _close_row(lst, keep)
        return True
    except Exception as e:
        print(f"[Lists] close_by_id failed: {e}")
        return False


def _reuse_row(user_id: str, old: Dict) -> Optional[Dict]:
    new = create(user_id, old.get("name") or "list", old.get("purpose") or "")
    if not new:
        return None
    for r in _items_of(old["id"]):
        f = r.get("fields") or {}
        if f.get("what"):
            add_item(new["id"], f["what"], {k: v for k, v in f.items() if k != "what"})
    return new


def reuse(user_id: str, list_name: str = "") -> Dict:
    """'Pichli baar wali Navratri list phir se' — a kept list, started again
    as a new one with nothing crossed off. The old one stays as it was."""
    old = _match(_kept_rows(user_id), list_name)
    if not old:
        return {"ok": False, "why": "no kept list by that name",
                "kept_lists": [key(l) for l in _kept_rows(user_id, 5)]}
    new = _reuse_row(user_id, old)
    if not new:
        return {"ok": False, "why": "could not start it"}
    n = len(_items_of(new["id"]))
    return {"ok": True, "from": key(old), "started": key(new), "items": n}


def reuse_by_id(user_id: str, list_id: str) -> Optional[Dict]:
    old = get(user_id, list_id)
    return _reuse_row(user_id, old) if old else None


def sweep(user_id: str) -> int:
    """Close (and keep) what has expired, or what nobody has touched in a
    fortnight. A market list dies when she gets back; a list of questions
    for her doctor lives until the appointment."""
    n = 0
    today = date.today()
    for lst in _active(user_id):
        exp = _clean_date(lst.get("expires_on"))
        if exp:
            if date.fromisoformat(exp) >= today:
                continue
        else:
            made = _parse_ts(lst.get("created_at"))
            touched = _parse_ts(lst.get("last_read_at"))
            seen = [d for d in (made, touched) if d]
            last = max(seen) if seen else None
            if not last or (today - last.date()).days < STALE_DAYS:
                continue
        try:
            _close_row(lst, keep=True)
            print(f"[Lists] {user_id}: swept {key(lst)!r}")
            n += 1
        except Exception as e:
            print(f"[Lists] sweep failed: {e}")
    return n


# ── one at a time ────────────────────────────────────────────────────────────

def _cursor_live(lst: Dict) -> bool:
    if not lst or not lst.get("last_read_item_id"):
        return False
    at = _parse_ts(lst.get("last_read_at"))
    return bool(at and _now() - at < timedelta(minutes=WALK_MINUTES))


def _set_cursor(list_id: str, item_id: Optional[str]) -> None:
    try:
        _db().table("lists").update({
            "last_read_item_id": item_id,
            "last_read_at": _now().isoformat() if item_id else None,
        }).eq("id", list_id).execute()
    except Exception as e:
        print(f"[Lists] cursor write failed: {e}")


def _cursor_item(lst: Dict) -> Optional[Dict]:
    if not _cursor_live(lst):
        return None
    try:
        rows = (_db().table("list_items").select("*")
                .eq("id", lst["last_read_item_id"]).limit(1).execute()).data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[Lists] cursor read failed: {e}")
        return None


def next_item(user_id: str, list_name: str = "") -> Dict:
    """The next thing to say out loud, and remember that it was said.
    In the order she added them — the order her paper list would be in.
    Skipped things come round again on a second pass."""
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    left = _items_of(lst["id"], include_done=False)
    if not left:
        _set_cursor(lst["id"], None)
        return {"ok": True, "done": True, "list": key(lst), "left": 0}

    here = _cursor_item(lst)
    nxt, second_pass = None, False
    if here:
        after = str(here.get("created_at") or "")
        nxt = next((r for r in left if str(r.get("created_at") or "") > after), None)
        if nxt is None:
            nxt, second_pass = left[0], True
    else:
        nxt = left[0]

    _set_cursor(lst["id"], nxt["id"])
    return {"ok": True, "list": key(lst), "item": nxt.get("fields") or {},
            "left": len(left), "second_pass": second_pass,
            "only_one_left": len(left) == 1}


def tick_current(user_id: str, list_name: str = "") -> Dict:
    """"Mil gaya" — with no name attached. Ticks what was just read out,
    then reads the next."""
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    here = _cursor_item(lst)
    if not here:
        # Say so rather than guess: the wrong tick sends her home without it.
        return {"ok": False, "why": "nothing was being read out — ask which one"}
    if not _set_done(here["id"], True):
        return {"ok": False, "why": "could not save"}
    print(f"[Lists] {user_id}: ticked {_what(here)!r} (reading out)")
    nxt = next_item(user_id, lst.get("name") or "")
    return {"ok": True, "ticked": _what(here), "next": nxt.get("item"),
            "done": nxt.get("done", False), "left": nxt.get("left", 0)}


def skip_current(user_id: str, list_name: str = "") -> Dict:
    """"Nahi mila" — leave it on, move past it. Not finding it today does
    not mean she stopped wanting it."""
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    here = _cursor_item(lst)
    nxt = next_item(user_id, lst.get("name") or "")
    return {"ok": True, "skipped": _what(here) if here else None,
            "next": nxt.get("item"), "done": nxt.get("done", False),
            "left": nxt.get("left", 0),
            "second_pass": nxt.get("second_pass", False)}


def stop_walk(user_id: str, list_name: str = "") -> Dict:
    """She has stopped going through it. Forget where we were."""
    lst = _find(user_id, list_name)
    if not lst:
        return {"ok": False, "why": "no list"}
    _set_cursor(lst["id"], None)
    left = len(_items_of(lst["id"], include_done=False))
    return {"ok": True, "stopped": key(lst), "left": left}


def walking(user_id: str) -> Optional[Dict]:
    """The list she is going through right now, and the item in hand."""
    for lst in _active(user_id):
        here = _cursor_item(lst)
        if here:
            return {"list": lst.get("name"), "key": key(lst), "item": _what(here)}
    return None


# ── for the conversation ─────────────────────────────────────────────────────

def hint(user_id: str) -> str:
    """A few lines for the composer.

    Not read out unprompted — a companion that recites a shopping list
    every morning is a nuisance. This is so it KNOWS, and can say
    "sabudana bhi list mein hai" when the market comes up, and so a bare
    "mil gaya" mid-walk lands on the right thing.
    """
    rows = _active(user_id)
    if not rows:
        return ""
    lines = []
    for lst in rows[:5]:
        left = _items_of(lst["id"], include_done=False)
        line = f"- {key(lst)}: {len(left)} left"
        if left:
            line += " (" + ", ".join(w for w in (_what(r) for r in left[:12]) if w)[:200] + ")"
        if lst.get("expires_on"):
            line += f", until {lst['expires_on']}"
        lines.append(line)
    out = ("\n\nHER LISTS (open):\n" + "\n".join(lines) +
           "\nDo not read these back unless she asks or it is plainly relevant. "
           "Knowing they are there is the point. Use the list tools for any "
           "change; never claim something is on a list without the tool.")
    w = walking(user_id)
    if w:
        out += (f"\n\nSHE IS GOING THROUGH '{w['list']}' ONE THING AT A TIME. "
                f"The last thing you read out was: {w['item']}. "
                "A bare 'mil gaya' / 'le liya' / 'ho gaya' means THAT item → "
                "tick_off_list with current=true, then say the next one. "
                "'Nahi mila' / 'aage' → tick_off_list with skip=true. "
                "'Bas' / 'baad mein' → read_list with stop_reading=true. "
                "One item per reply, short — she is in a shop.")
    return out

"""
After each reply: does her list match what was said?

15 Oct, bazar list. She said everything had come; Nancy said "Sab aa gaya to
ab list khatam — rakh lein ya hata dein?". She said "Hata do"; Nancy said
"Theek hai, hata di. Ab bazar ki list bilkul saaf." No list tool ran on
either turn: five items stayed open and the list was never closed. Single,
direct changes ("carbon hatake tarbooz dal do") worked; what failed was an
action resting on what came before — "sab aa gaya", or a yes to Nancy's own
question.

So after a turn that touches one of her open lists, one model call sees the
turn (her words, what Nancy asked just before, Nancy's reply), what the
list tools did, and the list as it is now. If the list doesn't match what
she said or agreed to, or what Nancy told her was done, it calls the SAME
list tools Nancy has to put it right. It never invents items, and drops a
list only when she said to drop it.

Runs in the background after the reply, so she doesn't wait for it.
Every fix is logged: "[Lists] claimed without action -> fixed: ...".
"""
import json
from typing import List, Dict, Optional

MUTATING = ("add_to_list", "tick_off_list", "change_list_item",
            "close_list", "reuse_list")


def _open_lists(user_id: str, with_kept: bool = False) -> List[Dict]:
    from memory import lists as L
    out = []
    rows_ = list(L._active(user_id) or [])
    if with_kept:
        # Kept lists too: "13 Oct wali list hata di" was said about a kept
        # one, and the guard, reading open lists only, could not see it.
        rows_ += [dict(l, _kept=True) for l in (L._kept_rows(user_id, 5) or [])]
    for lst in rows_:
        rows = L._items_of(lst["id"]) or []
        out.append({"name": L.key(lst), "kept": bool(lst.get("_kept")), "items": [
            {"what": L._what(r), "done": bool(r.get("done")),
             "details": {k: v for k, v in (r.get("fields") or {}).items()
                         if k != "what" and not str(k).startswith("_")}}
            for r in rows]})
    return out


def _touches(lists: List[Dict], *texts: str) -> bool:
    """Is this turn about one of her lists? Matched against her own list
    names and items, not a word list."""
    said = " ".join(t or "" for t in texts).lower()
    if not said.strip():
        return False
    for l in lists:
        name = str(l["name"] or "").lower().strip()
        if name and name not in ("list",) and name in said:
            return True
        for i in l["items"]:
            w = str(i["what"] or "").lower().strip()
            if len(w) >= 3 and w in said:
                return True
    return " list" in f" {said}"


def _state(lists: List[Dict]) -> str:
    if not lists:
        return "(no open lists)"
    lines = []
    for l in lists:
        lines.append(f"List '{l['name']}'" + (" (KEPT: finished, saved for next time)" if l.get("kept") else "") + ":")
        for i in l["items"]:
            d = ", ".join(f"{k}: {v}" for k, v in i["details"].items())
            lines.append(f"  [{'x' if i['done'] else ' '}] {i['what']}" + (f" ({d})" if d else ""))
    return "\n".join(lines)


_PROMPT = """You check a companion's shopping/to-do lists after one turn of conversation with an elderly woman.

Before this turn, the companion said:
"{prev}"

She then said:
"{her}"

The companion replied:
"{reply}"

List tools the companion ran this turn, with results:
{ran}

Her lists NOW (after those tools; [x] = crossed off):
{state}

Does the list match the conversation? It should reflect:
- anything SHE clearly said changed (she got something, wants something added, changed or removed, said everything came), and
- anything she AGREED to when the companion asked (e.g. companion asked "rakh lein ya hata dein?" and she said "hata do" = drop the list; "rakh lo" = keep it), and
- anything the companion's reply TOLD her was done.

If something is missing, call the list tools now to make the list match. Rules:
- Only what she said or agreed to, or what the reply claimed. Never invent items.
- Something she got is crossed off with tick_off_list ("sab aa gaya" = everything=true), not removed.
- close_list with keep=false only if she clearly said to drop/delete that list (it may be a KEPT one;
  name it). keep=true only if she clearly said to keep it. If she asked to close a list but has not
  said keep or drop, do NOT close it: the companion must ask her first.
- If a tool above already did it, do not do it again.
If nothing is missing, call no tool and answer exactly: NONE"""


def check_after_reply(user_id: str, model: str, her_text: str, prev_reply: str,
                      reply: str, tool_results: List[Dict]) -> Optional[List[Dict]]:
    """Returns the fixes made ([] if none, None if the turn wasn't about a list)."""
    try:
        lists = _open_lists(user_id, with_kept=True)
    except Exception as e:
        print(f"[Lists] guard: read failed: {e}")
        return None
    if not lists or not _touches(lists, her_text, prev_reply, reply):
        return None

    ran = [r for r in (tool_results or []) if r.get("tool") in MUTATING or r.get("tool") == "read_list"]
    ran_txt = "\n".join(f"- {r['tool']}: {json.dumps(r.get('data'), ensure_ascii=False)[:300]}"
                        for r in ran) or "(none)"
    prompt = _PROMPT.format(prev=(prev_reply or "")[:600], her=(her_text or "")[:400],
                            reply=(reply or "")[:600], ran=ran_txt, state=_state(lists))
    try:
        import litellm
        from engine.engine_router import _to_litellm_model
        from engine.tools import get_tool_schemas, execute_tool
        tools = [t for t in get_tool_schemas()
                 if t.get("function", {}).get("name") in MUTATING]
        lm, extra = _to_litellm_model(model)
        resp = litellm.completion(model=lm, messages=[{"role": "user", "content": prompt}],
                                  tools=tools, **extra)
        calls = getattr(resp.choices[0].message, "tool_calls", None) or []
    except Exception as e:
        print(f"[Lists] guard: check failed: {e}")
        return None

    fixes = []
    for call in calls:
        name = call.function.name
        if name not in MUTATING:
            continue
        try:
            args = json.loads(call.function.arguments or "{}")
        except Exception:
            args = {}
        result = execute_tool(name, args, user_id=user_id)
        fixes.append({"tool": name, "args": args, "result": result})
        print(f"[Lists] claimed without action -> fixed: {name} {json.dumps(args, ensure_ascii=False)} "
              f"-> {json.dumps(result, ensure_ascii=False)[:160]}")
    if not fixes:
        print(f"[Lists] guard: {user_id}: list matches the turn")
    return fixes

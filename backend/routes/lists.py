"""
LIST ROUTES — the Lists screen.

She can say "likh lena" in chat and it is kept; this is where she LOOKS at
it. Before leaving the house you want to see the nine things, not hear them.

Every route takes the user id and checks the list is hers before touching
it — an item id alone is never enough. The API key is applied where the
router is registered in main.py, like the others.

    GET    /lists/{user_id}                               open + kept lists
    GET    /lists/{user_id}/{list_id}                     one list, with columns
    GET    /lists/{user_id}/{list_id}/shops?places=       is it shopping; where to buy
    POST   /lists/{user_id}                               new list
    POST   /lists/{user_id}/{list_id}/items               add an item
    POST   /lists/{user_id}/{list_id}/items/{item_id}/tick   {done: bool}
    PATCH  /lists/{user_id}/{list_id}/items/{item_id}     {fields: {...}}
    DELETE /lists/{user_id}/{list_id}/items/{item_id}
    POST   /lists/{user_id}/{list_id}/close               {keep: bool}
    POST   /lists/{user_id}/{list_id}/reuse               kept → new open list
"""
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from memory import lists as L

router = APIRouter()


class NewList(BaseModel):
    name: str
    purpose: Optional[str] = ""
    expires_on: Optional[str] = None        # "2026-10-19"


class NewItem(BaseModel):
    what: str
    fields: Optional[Dict[str, str]] = None


class TickIn(BaseModel):
    done: bool = True


class EditIn(BaseModel):
    fields: Dict[str, str]


class CloseIn(BaseModel):
    # Her answer to "rakh lein?". Keeping is the default.
    keep: bool = True


def _mine(user_id: str, list_id: str) -> Dict:
    lst = L.get(user_id, list_id)
    if not lst:
        raise HTTPException(404, "no such list")
    return lst


@router.get("/{user_id}")
def all_lists(user_id: str):
    try:
        L.sweep(user_id)          # close what has expired before showing it
    except Exception as e:
        print(f"[ListsRoute] sweep failed: {e}")
    return L.overview(user_id)


@router.get("/{user_id}/{list_id}")
def one_list(user_id: str, list_id: str):
    d = L.detail(user_id, list_id)
    if not d:
        raise HTTPException(404, "no such list")
    return d


@router.get("/{user_id}/{list_id}/shops")
def list_shops(user_id: str, list_id: str, places: bool = False):
    """Where the things on this list can be bought ("Kahan milega?").

    places=false: only whether it is a shopping list and how its items
    group by kind of shop — the screen asks this when the list opens, to
    know whether to show the button. places=true adds the nearest shops
    for each group, when she taps it.
    """
    _mine(user_id, list_id)
    from memory import shops
    return shops.where(user_id, list_id) if places else shops.plan(user_id, list_id)


@router.post("/{user_id}")
def create_list(user_id: str, body: NewList):
    row = L.create(user_id, body.name, body.purpose or "", body.expires_on or "")
    if not row:
        raise HTTPException(400, "could not create")
    return {"id": row["id"], "key": L.key(row), "name": row.get("name")}


@router.post("/{user_id}/{list_id}/items")
def add_item(user_id: str, list_id: str, body: NewItem):
    lst = _mine(user_id, list_id)
    if lst.get("closed_at"):
        raise HTTPException(409, "list is closed")
    row = L.add_item(list_id, body.what, body.fields or {})
    if not row:
        raise HTTPException(400, "nothing to add")
    return {"id": row["id"], "fields": row.get("fields"), "done": False,
            "created_at": row.get("created_at")}


@router.post("/{user_id}/{list_id}/items/{item_id}/tick")
def tick_item(user_id: str, list_id: str, item_id: str, body: TickIn):
    _mine(user_id, list_id)
    if not L.set_item_done(user_id, list_id, item_id, body.done):
        raise HTTPException(404, "no such item")
    return {"ok": True, "done": bool(body.done)}


@router.patch("/{user_id}/{list_id}/items/{item_id}")
def edit_item(user_id: str, list_id: str, item_id: str, body: EditIn):
    _mine(user_id, list_id)
    f = L.edit_item(user_id, list_id, item_id, body.fields)
    if f is None:
        raise HTTPException(400, "could not change it (is 'what' empty?)")
    return {"ok": True, "fields": f}


@router.delete("/{user_id}/{list_id}/items/{item_id}")
def remove_item(user_id: str, list_id: str, item_id: str):
    _mine(user_id, list_id)
    if not L.remove_item(user_id, list_id, item_id):
        raise HTTPException(404, "no such item")
    return {"ok": True}


@router.post("/{user_id}/{list_id}/close")
def close_list(user_id: str, list_id: str, body: CloseIn):
    """keep=True closes it and leaves it in 'kept'; keep=False deletes the
    list and its items. The screen asks first."""
    _mine(user_id, list_id)
    if not L.close_by_id(user_id, list_id, keep=body.keep):
        raise HTTPException(500, "could not close")
    return {"ok": True, "kept": body.keep}


@router.post("/{user_id}/{list_id}/reuse")
def reuse_list(user_id: str, list_id: str):
    _mine(user_id, list_id)
    new = L.reuse_by_id(user_id, list_id)
    if not new:
        raise HTTPException(500, "could not start it again")
    return {"id": new["id"], "key": L.key(new), "name": new.get("name")}

"""
Replays the 15 Oct bazar list exchange against list_guard, on a throwaway
user, with the same model the app uses. Live (model calls).

    railway run python3 -u backend/tests/sim_list_guard.py

1. "Sab aa gaya" with no tool run      -> all five crossed off
2. "Hata do" to "rakh lein ya hata dein?" -> list dropped
3. "haan theek hai" to a question that changes nothing -> nothing changes
4. "ghee le liya" when the tool already ticked it -> no second action
5. A turn not about the list            -> no check at all
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

UID = "sim_list_guard"
ITEMS = [("tarbooz", {"kitna": "1"}), ("phool", {"kis liye": "Pooja"}),
         ("ghee", {"kitna": "1 kg"}), ("maida", {"kitna": "1 kg"}),
         ("cheeni", {"kitna": "1 kg"})]
READ_OUT = ("Bazar ki list mein paanch cheezein bachi hain, Shobha ji:\n- Tarbooz — 1\n"
            "- Phool — pooja ke liye\n- Ghee — 1 kg\n- Maida — 1 kg\n- Cheeni — 1 kg")


def _db():
    from supabase_store import get_client
    return get_client()


def wipe():
    db = _db()
    ids = [r["id"] for r in db.table("lists").select("id").eq("user_id", UID).execute().data or []]
    if ids:
        db.table("list_items").delete().in_("list_id", ids).execute()
        db.table("lists").delete().eq("user_id", UID).execute()


def fresh_list():
    from memory import lists as L
    wipe()
    lst = L.create(UID, "bazar")
    for what, f in ITEMS:
        L.add_item(lst["id"], what, f)
    return lst


def state():
    from memory.list_guard import _open_lists
    return _open_lists(UID)


def model():
    rows = (_db().table("sessions").select("model").eq("user_id", "default")
            .order("updated_at", desc=True).limit(1).execute()).data or []
    return (rows[0].get("model") if rows else None) or "gemini"


def main():
    from memory.list_guard import check_after_reply
    from memory import lists as L
    m = model()
    print(f"model: {m}\n")
    fails = 0

    def check(ok, label):
        nonlocal fails
        fails += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {label}")

    try:
        # 1
        fresh_list()
        check_after_reply(UID, m, "Haan sab aa gaya, online order kar diya tha",
                          READ_OUT, "Bahut achha. Sab aa gaya to ab list khatam — isko rakh lein "
                          "agli baar ke liye, ya hata dein?", [])
        s = state()
        check(bool(s) and all(i["done"] for i in s[0]["items"]),
              "1. 'sab aa gaya' with no tool run -> all crossed off "
              f"({[(i['what'], i['done']) for i in s[0]['items']] if s else 'no list'})")

        # 2
        check_after_reply(UID, m, "Hata do",
                          "Bahut achha. Sab aa gaya to ab list khatam — isko rakh lein agli baar "
                          "ke liye, ya hata dein?",
                          "Theek hai, hata di. Ab bazar ki list bilkul saaf.", [])
        check(not state(), f"2. 'Hata do' -> list dropped (open lists: {[l['name'] for l in state()]})")

        # 3
        fresh_list()
        check_after_reply(UID, m, "haan theek hai", READ_OUT + "\n\nBazaar kab jaana hai?",
                          "Achha, jab mann ho tab chaliye.", [])
        s = state()
        check(bool(s) and not any(i["done"] for i in s[0]["items"]) and len(s[0]["items"]) == 5,
              "3. 'haan theek hai' to a question that changes nothing -> unchanged")

        # 4
        fresh_list()
        r = L.tick(UID, "ghee", "bazar")
        fixes = check_after_reply(UID, m, "ghee le liya", READ_OUT,
                                  "Wah, ghee ho gaya. Ab chaar cheezein bachi hain.",
                                  [{"tool": "tick_off_list", "data": r}])
        s = state()
        done = [i["what"] for i in s[0]["items"] if i["done"]] if s else []
        check(done == ["ghee"] and not any(f["tool"] == "add_to_list" for f in (fixes or [])),
              f"4. tool already ticked ghee -> nothing more (done: {done}, fixes: {[f['tool'] for f in fixes or []]})")

        # 5
        fixes = check_after_reply(UID, m, "Aaj mausam bahut accha hai",
                                  "Shobha ji, lunch kaisa raha?", "Haan bilkul, hawa bhi achhi hai.", [])
        check(fixes is None, "5. turn not about the list -> no check")
    finally:
        wipe()

    print(f"\n{5 - fails}/5 {'ALL GREEN' if not fails else 'FAILED'}")


if __name__ == "__main__":
    main()

"""
Two guessed facts already in her profile, removed once (16 Oct).

"Occupation: likely retired or pensioner" and "Lives with or near family
(son Shubham)" were never said by her. New guesses are stopped before saving
now (profile_store._only_stated); these two were saved before that, and a
stored value is never overwritten, so they are removed here, once.

Her location is NOT touched: the location code keeps it current from what
she says, and the summary no longer keeps its own copy (summarizer rule 10),
so the address there drops out at her next chat's end.

    cd backend
    PYTHONPATH=. railway run python3 scripts/fix_profile_facts.py default          # preview
    PYTHONPATH=. railway run python3 scripts/fix_profile_facts.py default --go     # write, with a backup
    PYTHONPATH=. railway run python3 scripts/fix_profile_facts.py --undo backups/profilefix_default_....json
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

GUESSES = ("occupation", "living_situation")


def main():
    from supabase_store import get_client
    db = get_client()

    if "--undo" in sys.argv:
        b = json.load(open(sys.argv[sys.argv.index("--undo") + 1]))
        db.table("user_profile").update({"life_context": b["life_context"]}) \
            .eq("user_id", b["user_id"]).execute()
        print(f"Restored life context for {b['user_id']}.")
        return

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    uid = args[0] if args else "default"
    go = "--go" in sys.argv
    p = (db.table("user_profile").select("life_context").eq("user_id", uid)
         .limit(1).execute()).data
    if not p:
        print(f"{uid}: no profile.")
        return
    life = dict(p[0].get("life_context") or {})
    gone = {k: life[k] for k in GUESSES if life.get(k)}
    print(f"\n{uid}: {'WRITING' if go else 'PREVIEW'}\n")
    if not gone:
        print("  nothing to remove")
        return
    for k, v in gone.items():
        print(f"  life_context.{k}: {v!r} -> removed")
    if not go:
        print("\nNothing changed. Add --go to write.")
        return
    os.makedirs("backups", exist_ok=True)
    path = f"backups/profilefix_{uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    json.dump({"user_id": uid, "life_context": life}, open(path, "w"), ensure_ascii=False, indent=1)
    db.table("user_profile").update({"life_context": {k: v for k, v in life.items() if k not in GUESSES}}) \
        .eq("user_id", uid).execute()
    print(f"\nWritten. Backup: {os.path.abspath(path)}")
    print(f"Undo: PYTHONPATH=. railway run python3 scripts/fix_profile_facts.py --undo {path}")


if __name__ == "__main__":
    main()

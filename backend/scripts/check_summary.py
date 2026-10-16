"""
Check her current profile summary against what is actually stored, once.

New profiles are checked at every chat's end (user_memory_store, step 9b).
This cleans the one that drifted before that existed: each claim is tested
against her own words, her concepts, her declared profile, the day notes and
month lines; what nothing supports is dropped, and key facts are drawn again
from the checked text.

    cd backend
    PYTHONPATH=. railway run python3 scripts/check_summary.py default          # preview
    PYTHONPATH=. railway run python3 scripts/check_summary.py default --go     # write THAT preview, with a backup
    PYTHONPATH=. railway run python3 scripts/check_summary.py --undo backups/summary_default_....json
    PYTHONPATH=. railway run python3 scripts/check_summary.py --set default /tmp/profile.txt   # a profile a person wrote
"""
import json
import os
import sys
import textwrap
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    from supabase_store import get_client
    db = get_client()

    if "--undo" in sys.argv:
        b = json.load(open(sys.argv[sys.argv.index("--undo") + 1]))
        db.table("user_memory").update({"summary": b["summary"], "key_facts": b["key_facts"]}) \
            .eq("user_id", b["user_id"]).execute()
        print(f"Restored the previous summary and key facts for {b['user_id']}.")
        return

    if "--set" in sys.argv:
        # Write a profile written and approved by a person, from a text file.
        uid = sys.argv[sys.argv.index("--set") + 1]
        text = open(sys.argv[sys.argv.index("--set") + 2]).read().strip()
        from memory.summarizer import extract_key_facts
        row = (db.table("user_memory").select("summary,key_facts").eq("user_id", uid)
               .limit(1).execute()).data or [{}]
        os.makedirs("backups", exist_ok=True)
        path = f"backups/summary_{uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        json.dump({"user_id": uid, "summary": row[0].get("summary"),
                   "key_facts": row[0].get("key_facts") or []}, open(path, "w"),
                  ensure_ascii=False, indent=1)
        facts = extract_key_facts(text)
        db.table("user_memory").update({"summary": text, "key_facts": facts}).eq("user_id", uid).execute()
        print("Written.\n  key facts: " + "; ".join(facts))
        print(f"Backup: {os.path.abspath(path)}")
        print(f"Undo: PYTHONPATH=. railway run python3 scripts/check_summary.py --undo {path}")
        return

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    uid = args[0] if args else "default"
    go = "--go" in sys.argv
    preview_path = f"backups/summary_preview_{uid}.json"

    row = (db.table("user_memory").select("summary,key_facts").eq("user_id", uid)
           .limit(1).execute()).data
    if not row or not row[0].get("summary"):
        print(f"{uid}: no summary to check.")
        return
    old, old_facts = row[0]["summary"], row[0].get("key_facts") or []

    if go:
        # Writes exactly what the preview showed — no second model reading,
        # which came out differently from the one reviewed.
        if not os.path.exists(preview_path):
            print("No preview to write. Run without --go first and read it.")
            return
        pv = json.load(open(preview_path))
        if pv.get("old") != old:
            print("Her summary has changed since the preview (a chat ended). Preview again.")
            return
        os.makedirs("backups", exist_ok=True)
        path = f"backups/summary_{uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        json.dump({"user_id": uid, "summary": old, "key_facts": old_facts}, open(path, "w"),
                  ensure_ascii=False, indent=1)
        db.table("user_memory").update({"summary": pv["new"], "key_facts": pv["facts"]}) \
            .eq("user_id", uid).execute()
        os.remove(preview_path)
        print(f"Written: the reviewed preview. Backup: {os.path.abspath(path)}")
        print(f"Undo: PYTHONPATH=. railway run python3 scripts/check_summary.py --undo {path}")
        return

    from memory.user_memory_store import summary_evidence
    from memory.summarizer import check_summary, extract_key_facts
    ev = summary_evidence(uid)
    print(f"\n{uid}: evidence {len(ev)} characters\n")
    res = check_summary(old, ev)
    if not res:
        print("The check could not be made. Nothing changed.")
        return
    facts = extract_key_facts(res["summary"])
    w = lambda t: textwrap.fill(t, 100, initial_indent="  ", subsequent_indent="  ")
    print("== NOW\n" + w(old))
    print("\n== CHECKED\n" + w(res["summary"]))
    print("\n== KEPT (each with words found in the evidence)")
    for k in res.get("kept") or []:
        print("  +", k)
    print("\n== DROPPED (no supporting words in the evidence)")
    for d in res["dropped"] or ["(nothing)"]:
        print("  -", d)
    print("\n== KEY FACTS, now -> checked")
    print("  now:     " + "; ".join(map(str, old_facts)))
    print("  checked: " + "; ".join(facts))
    os.makedirs("backups", exist_ok=True)
    json.dump({"old": old, "new": res["summary"], "facts": facts}, open(preview_path, "w"),
              ensure_ascii=False, indent=1)
    print(f"\nNothing changed. This preview is saved; --go writes exactly it.")


if __name__ == "__main__":
    main()

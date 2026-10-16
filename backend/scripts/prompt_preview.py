"""
What Nancy's reply is given about her, for one message, block by block.

    cd backend
    PYTHONPATH=. railway run python3 scripts/prompt_preview.py default "Hum zoo kab gaye the?"
    PYTHONPATH=. railway run python3 scripts/prompt_preview.py default "Shubham ka number kya hai?"
    PYTHONPATH=. railway run python3 scripts/prompt_preview.py default --proactive

Changes nothing of hers except what any message does anyway: the day notes
it reads are marked as read, and episodes quiet for a week are closed.
At the end, for each of her people and lasting conditions, how many blocks
name it — the point of step 3 is that each is named in ONE place
(the summary aside, which is her own prose).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    uid = args[0] if args else "default"
    text = args[1] if len(args) > 1 else ""
    proactive = "--proactive" in sys.argv

    from memory.user_memory_store import build_memory_prompt
    from memory.episodes import prompt_note
    blocks = {}
    if proactive:
        blocks["memory (proactive)"] = build_memory_prompt(uid) or ""
        blocks["health (proactive)"] = prompt_note(uid) or ""
    else:
        from memory.profile_store import build_profile_prompt
        from engine.engine_router import _food_notes, _retrieve_memory
        blocks["profile"] = build_profile_prompt(uid) or ""
        blocks["memory"] = build_memory_prompt(uid, None, text, in_chat=True) or ""
        blocks["food"] = _food_notes(uid) or ""
        blocks["health"] = prompt_note(uid, lasting=True) or ""
        blocks["things that happened"] = (_retrieve_memory(None, "", uid, query_text=text) or "") if text else ""

    print(f"\n{uid}" + (f' asks: "{text}"' if text else "") + (" — proactive" if proactive else "") + "\n")
    total = 0
    for name, b in blocks.items():
        total += len(b)
        print(f"===== {name.upper()}  ({len(b)} characters)")
        print(b.strip() or "(empty)")
        print()
    print(f"Total {total} characters.\n")

    # Where each of her people and conditions is named. The summary is
    # counted apart: it is her prose, written once, and not split by topic.
    from supabase_store import get_client
    rows = (get_client().table("interest_clusters").select("label,kind,pillar")
            .eq("user_id", uid).eq("status", "active").in_("kind", ["person", "concern"])
            .execute()).data or []
    mem = blocks.get("memory") or blocks.get("memory (proactive)") or ""
    summary = ""
    if "Summary of past conversations:" in mem:
        summary = mem.split("Summary of past conversations:", 1)[1].split("\n\n", 1)[0]
    print("===== WHERE EACH IS NAMED (blocks, not counting the summary)")
    for r in sorted(rows, key=lambda r: (r["kind"], r["label"])):
        lab = r["label"].lower()
        where = []
        for name, b in blocks.items():
            body = b.replace(summary, "") if summary and name.startswith("memory") else b
            n = body.lower().count(lab)
            if n:
                where.append(f"{name} x{n}")
        insum = " (+ summary)" if lab in summary.lower() else ""
        print(f"  {r['kind']:8} {r['label'][:28]:28} {', '.join(where) or 'nowhere'}{insum}")


if __name__ == "__main__":
    main()

"""What it knows about her, and whether each entry earns its place."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from supabase_store import get_client

db = get_client()
rows = (db.table("interest_clusters")
        .select("id,label,kind,pillar,strength,event_count,attributes,"
                "last_event,status")
        .eq("user_id", "default").eq("status", "active")
        .order("strength", desc=True).execute()).data or []

print(f"{len(rows)} active clusters\n")
print(f"  {'label':28} {'kind':9} {'cat':9} {'str':>5} {'n':>3}  source")
offerable = 0
for r in rows:
    a = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
    cat = a.get("category")
    if cat and r.get("kind") == "interest":
        offerable += 1
    print(f"  {str(r['label'])[:26]:28} {str(r.get('kind')):9} "
          f"{str(cat or '-'):9} {float(r.get('strength') or 0):5.1f} "
          f"{r.get('event_count'):>3}  {a.get('source') or '-'}")

print(f"\n  {offerable} offerable")

# things that look like fragments rather than subjects
sus = [r["label"] for r in rows
       if len(str(r["label"]).split()) > 3
       or str(r["label"]).lower() in ("good", "fine", "health", "everything",
                                      "rest", "home", "aram")]
print(f"  {len(sus)} look like fragments: {sus}")

# the same thing under two names
labels = [str(r["label"]).lower() for r in rows]
dupes = [(a, b) for i, a in enumerate(labels) for b in labels[i+1:]
         if a in b or b in a]
print(f"  {len(dupes)} possible duplicates: {dupes}")

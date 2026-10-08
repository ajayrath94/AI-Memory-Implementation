"""Yesterday and today, side by side — for seeing what should have carried."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from supabase_store import get_client
from datetime import datetime, timezone, timedelta
from collections import defaultdict

db = get_client()
IST = timedelta(hours=5, minutes=30)
since = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()

def ist(ts):
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00")) + IST

rows = []
for s in (db.table("sessions").select("id").eq("user_id", "default")
          .gte("updated_at", since).execute()).data or []:
    for m in (db.table("messages").select("role,content,timestamp")
              .eq("session_id", s["id"]).gte("timestamp", since)
              .execute()).data or []:
        rows.append((ist(m["timestamp"]), m["role"], m["content"]))

byday = defaultdict(list)
for t, role, c in sorted(rows):
    byday[t.date()].append((t, role, c))

for day in sorted(byday):
    print(f"\n=== {day.strftime('%A %d %B')} ===")
    for t, role, c in byday[day]:
        who = "SHE  " if role == "user" else "nancy"
        print(f"  {t.strftime('%H:%M')} {who} {str(c)[:120]}")

print("\n=== the day's notes ===")
for r in (db.table("day_notes").select("on_day,note")
          .eq("user_id", "default").order("on_day", desc=True)
          .limit(3).execute()).data or []:
    print(f"  {r['on_day']}: {str(r.get('note'))[:300]}")

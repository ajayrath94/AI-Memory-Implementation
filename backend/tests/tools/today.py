"""What she was sent today, what she said, and what the scheduler decided.

Lives in the repo rather than /tmp, which is cleared overnight and took this
with it three mornings running.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from supabase_store import get_client
from datetime import datetime, timezone, timedelta

db = get_client()
IST = timedelta(hours=5, minutes=30)
since = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()


def ist(ts):
    return (datetime.fromisoformat(str(ts).replace("Z", "+00:00")) + IST)


print("WHAT WAS SAID")
rows = []
for s in (db.table("sessions").select("id").eq("user_id", "default")
          .gte("updated_at", since).execute()).data or []:
    for m in (db.table("messages").select("role,content,timestamp")
              .eq("session_id", s["id"]).gte("timestamp", since)
              .execute()).data or []:
        rows.append((ist(m["timestamp"]), m["role"], m["content"]))
for t, role, content in sorted(rows):
    who = "she  " if role == "user" else "nancy"
    print(f"  {t.strftime('%H:%M')} {who} {str(content)[:150]}")

print("\nWHAT THE SCHEDULER DECIDED")
for r in (db.table("proactive_events")
          .select("action,detail,created_at,delivered_at")
          .eq("user_id", "default").gte("created_at", since)
          .order("created_at").execute()).data or []:
    print(f"  {ist(r['created_at']).strftime('%H:%M')} "
          f"{str(r['action'])[:18]:20} {str(r.get('detail'))[:24]:26} "
          f"{'sent' if r.get('delivered_at') else 'held'}")

print("\nCLUSTERS MADE TODAY")
for r in (db.table("interest_clusters")
          .select("label,kind,attributes,created_at")
          .eq("user_id", "default").gte("created_at", since)
          .execute()).data or []:
    a = r.get("attributes") or {}
    print(f"  {str(r['label'])[:26]:28} {str(r.get('kind')):9} "
          f"{a.get('category') or '-'}")

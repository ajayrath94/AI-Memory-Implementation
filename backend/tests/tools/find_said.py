"""Every time she mentioned something, from her own messages."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from supabase_store import get_client
from datetime import datetime, timedelta

db = get_client()
WORDS = ("chicken", "murg", "mutton", "fish", "machli", "anda", "ande", "egg",
         "keema", "biryani")

sess = (db.table("sessions").select("id")
        .eq("user_id", "default").limit(400).execute()).data or []
hits = []
for s in sess:
    for m in (db.table("messages").select("content,timestamp")
              .eq("session_id", s["id"]).eq("role", "user")
              .execute()).data or []:
        txt = str(m.get("content") or "").lower()
        if any(w in txt for w in WORDS):
            t = (datetime.fromisoformat(str(m["timestamp"]).replace("Z", "+00:00"))
                 + timedelta(hours=5, minutes=30))
            hits.append((t, m["content"]))

for t, c in sorted(hits):
    print(f"  {t.strftime('%Y-%m-%d %a %H:%M')}  {str(c)[:70]}")
print(f"\n  {len(hits)} mentions, on "
      f"{len({t.date() for t, _ in hits})} different days")

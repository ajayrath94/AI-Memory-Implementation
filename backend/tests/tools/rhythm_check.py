"""Is her Sunday chicken being captured?"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from supabase_store import get_client
from datetime import date, timedelta

db = get_client()
since = (date.today() - timedelta(days=42)).isoformat()

print("EVERY SUBJECT, BY DAY")
rows = (db.table("subject_mentions").select("subject,happened_on")
        .eq("user_id", "default").gte("happened_on", since)
        .order("happened_on", desc=True).execute()).data or []
for r in rows[:30]:
    d = date.fromisoformat(str(r["happened_on"])[:10])
    print(f"  {r['happened_on']} {d.strftime('%a')}  {r['subject']}")
print(f"  ({len(rows)} in six weeks)")

print("\nMEAT, AND WHEN")
from memory.diet import observed_meat_days, can_eat_meat_today
seen = observed_meat_days("default", weeks=6)
print(f"  days: {seen['days']}")
print(f"  weekdays: {seen['weekdays']}  (6 = Sunday)")
print(f"  today: {can_eat_meat_today('default')}")

print("\nRHYTHMS")
from memory.rhythms import rhythms_for, due_today
for r in rhythms_for("default"):
    print(f"  {r['subject'][:22]:24} {r['weekday']:10} "
          f"{r['on_that_day']}/{r['of']}")
print(f"  due today: {[r['subject'] for r in due_today('default')] or 'nothing'}")

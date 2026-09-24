"""
The same thing, offered at four different distances.

    railway run python3 -u backend/tests/sim_when.py
    railway run python3 -u backend/tests/sim_when.py --keep

The picker handed the composer a label and nothing else, so "chole" — which
she ate two days ago — was offered as though it were a new idea. The dates
were in the database the whole time: last_event on the cluster, every day in
subject_mentions.

ONE SUBJECT IS FOUR DIFFERENT OFFERS

    never mentioned     an introduction. "Chole try kijiye?"
    today               nothing. She has already had it.
    two days ago        a callback. "Phir se chole?" — which is a person
                        remembering, where "try kijiye" is a stranger.
    three weeks ago     the gap is the reason. "Bahut din se khichdi nahi
                        banayi" — warm, and impossible without the date.

Four subjects are seeded at four distances and each is drawn in turn, so the
difference between the messages is only the date.

WHAT TO READ
The four messages. They should not be interchangeable. If the three-week one
reads the same as the never-mentioned one, the date reached the prompt and
did nothing with it.
"""
import os
import sys
from datetime import date, datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase_store import get_client

UID = "whensim"

# (label, category, how many days ago she last had it or None for never)
SUBJECTS = [
    ("khichdi",       "khana",   21),    # a long gap — the gap is the reason
    ("chole",         "khana",    2),    # recent — a callback
    ("Lata Mangeshkar", "sangeet", 0),   # today — do not offer at all
    ("Sholay",        "dekhna", None),   # never — an introduction
]


def teardown():
    db = get_client()
    for t in ("subject_mentions", "memory_stm", "memory_cache", "suggestions",
              "user_behavioral_events", "interest_clusters", "user_patterns",
              "user_memory", "user_profile"):
        try:
            db.table(t).delete().eq("user_id", UID).execute()
        except Exception:
            pass
    try:
        from memory.suggestions import _SETTLED
        _SETTLED.clear()
    except Exception:
        pass


def setup():
    teardown()
    db = get_client()
    db.table("user_profile").insert({
        "user_id": UID, "name": "Kamala", "language_pref": "hinglish",
        "location": "Jaipur",
    }).execute()
    db.table("user_memory").insert({"user_id": UID, "session_count": 6}).execute()
    for kind, label, at in (("wake", None, "06:30"),
                            ("meal", "breakfast", "08:30"),
                            ("meal", "lunch", "13:00"),
                            ("meal", "dinner", "19:30"),
                            ("sleep", None, "22:00")):
        db.table("user_patterns").insert({
            "user_id": UID, "kind": kind, "label": label,
            "declared_at": at, "source": "declared",
        }).execute()

    ids = {}
    today = date.today()
    for label, cat, ago in SUBJECTS:
        row = {
            "user_id": UID, "label": label, "pillar": "GENERAL",
            "kind": "interest", "status": "active", "strength": 2.0,
            "attributes": {"category": cat, "source": "conversation"},
        }
        if ago is not None:
            # Evening, because the hour is part of what is being carried.
            when = (datetime.now(timezone.utc) - timedelta(days=ago)
                    ).replace(hour=14, minute=30)
            row["last_event"] = when.isoformat()
        r = db.table("interest_clusters").insert(row).execute()
        ids[label] = r.data[0]["id"]

        if ago is not None:
            db.table("subject_mentions").insert({
                "user_id": UID, "subject": label, "pillar": "GENERAL",
                "sentiment": 0.6,
                "happened_on": (today - timedelta(days=ago)).isoformat(),
                "cluster_id": ids[label],
            }).execute()
    return ids


def main():
    import memory.suggestions as S
    import memory.day as D
    from memory.schedule_engine import generate_proactive_script

    ids = setup()
    print(f"{len(SUBJECTS)} subjects, seeded at four distances\n")
    for label, cat, ago in SUBJECTS:
        when = "never" if ago is None else "today" if ago == 0 else f"{ago}d ago"
        print(f"  {label:18} {cat:8} last had: {when}")

    real_moment, real_boundary = S._moment, D.boundary
    real_pick = S.pick_suggestion

    def at_eleven(uid):
        m = real_moment(uid)
        m["now_min"] = 11 * 60
        return m

    for label, cat, ago in SUBJECTS:
        # Force this one to be the drawn subject, so the only thing that
        # differs between the four messages is how long ago she had it.
        S._moment = at_eleven
        D.boundary = lambda uid, now_min=None: real_boundary(uid, now_min=11 * 60)

        def only_this(uid, _l=label):
            p = real_pick(uid)
            if p and p.get("label") == _l:
                return p
            # build it directly, with the same fields the picker returns
            db = get_client()
            r = (db.table("interest_clusters")
                 .select("id,label,pillar,attributes,last_event")
                 .eq("user_id", uid).eq("label", _l).limit(1).execute()).data
            if not r:
                return None
            row = r[0]
            last_on, days_ago = None, None
            m = (db.table("subject_mentions").select("happened_on")
                 .eq("user_id", uid).ilike("subject", f"%{_l}%")
                 .order("happened_on", desc=True).limit(1).execute()).data or []
            if m:
                last_on = str(m[0]["happened_on"])[:10]
                days_ago = (date.today() - date.fromisoformat(last_on)).days
            return {"cluster_id": row["id"], "label": row["label"],
                    "pillar": row.get("pillar"),
                    "last_on": last_on,
                    "last_at": str(row.get("last_event") or "") or None,
                    "days_ago": days_ago,
                    "attributes": row.get("attributes") or {}}

        S.pick_suggestion = only_this
        try:
            out = generate_proactive_script(UID, action="RECOMMENDATION", force_slot="midday") or {}
            when = ("never had it" if ago is None
                    else "had it today" if ago == 0 else f"had it {ago} days ago")
            print(f"\n— {label}, {when} —")
            print(f"  {out.get('script', '')[:230] or '(nothing)'}")
        except Exception as e:
            print(f"\n— {label} — failed: {str(e)[:90]}")
        finally:
            S.pick_suggestion = real_pick
            S._moment, D.boundary = real_moment, real_boundary

    print("\nThe four should not be interchangeable. If the three-week one")
    print("reads like the never-mentioned one, the date reached the prompt")
    print("and nothing was done with it.")


if __name__ == "__main__":
    if "--purge" in sys.argv:
        teardown()
        print("purged")
    else:
        try:
            main()
        finally:
            if "--keep" not in sys.argv:
                print()
                teardown()
                print("torn down")

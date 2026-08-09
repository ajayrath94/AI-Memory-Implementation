#!/usr/bin/env python3
"""
NANCY HEARTBEAT — the recurring background job.

Run on a schedule by Railway cron. One pass, then exits (cron handles repetition).
Currently runs run_scheduler_pass(), which:
  - Summarizes idle, unsummarized sessions (the auto session-summarizer backstop)
  - Runs the proactive engine check per active user
Later this same heartbeat will fire due reminders.

Usage (local / cron):
  cd backend && python scripts/heartbeat.py
"""
import os, sys, json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def main():
    started = datetime.now(timezone.utc).isoformat()
    print(f"[Heartbeat] start {started}")
    try:
        from memory.scheduler import run_scheduler_pass
        result = run_scheduler_pass(dry_run=False)
        print(f"[Heartbeat] scheduler pass: "
              f"checked={result.get('checked')} would_fire={result.get('would_fire')}")
    except Exception as e:
        import traceback
        print(f"[Heartbeat] scheduler pass FAILED: {e}")
        traceback.print_exc()
        sys.exit(1)
    print(f"[Heartbeat] done {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()

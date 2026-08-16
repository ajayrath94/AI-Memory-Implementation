# Server-Side Push Notifications — Build Plan

## Goal
Reminders + calendar events fire notifications on the phone **regardless of app
activity** (app closed, force-quit, offline). Current system is app-triggered
(app polls /proactive), so it fails the "fire no matter what" requirement.
Fix = server-driven push via a cron-run heartbeat.

## What already exists (the foundation)
- `backend/scripts/heartbeat.py` — cron-ready ("Later this same heartbeat will
  fire due reminders"). Runs `run_scheduler_pass()`.
- `run_scheduler_pass()` (backend/memory/scheduler.py, line ~46) — ALREADY finds
  + fires due reminders via `get_due_reminders()` / `mark_nudge_fired()`. Currently
  fires them as pollable proactive nudges (log_decision), NOT pushes.
- `get_due_reminders()` (reminder_engine.py ~191) → items: {reminder:{user_id,
  what,...}, message, nudge_index}.
- Local notification service (mobile/services/notificationService.ts) — schedules
  local notifs on app-open (the interim layer we built; keep as supplement).

## The gaps to close
1. **NO cron is running** — Railway has only the web service. heartbeat.py never
   runs automatically. THIS is the #1 enabler (activates the whole dormant
   server-side proactive/reminder layer).
2. **No push arm** — firing a reminder logs a proactive nudge (app must poll);
   needs to also send an Expo push to reach a closed app.
3. **No push tokens** — app never registers a push token with the backend.

## Build (3 pieces)

### Piece 1 — Railway cron (THE enabler, do first)
- Add a Railway **Cron service** running: `cd backend && python scripts/heartbeat.py`
  on schedule `*/2 * * * *` (every 2 min).
- Options: Railway dashboard (New service → Cron) OR railway.json cron config.
- Test: confirm heartbeat logs appear every 2 min in that service's logs.
- NOTE: this alone makes existing reminders/proactive fire server-side.

### Piece 2 — Push tokens
- SQL: `create table push_tokens (user_id text primary key, expo_token text,
  platform text, updated_at timestamptz default now());`
- Backend: `POST /push/register` {user_id, expo_token, platform} → upsert.
- Frontend (notificationService.ts): `getExpoPushTokenAsync()` on app open →
  POST /push/register. Requires projectId (Expo). Needs a real device or
  dev-build for a real token (simulator can't get push tokens — test on device).

### Piece 3 — Push delivery in the scheduler
- In scheduler.py reminder-firing loop (after mark_nudge_fired, ~line 62):
  look up user's expo_token, POST to Expo Push API:
  `POST https://exp.host/--/api/v2/push/send`
  body: {to: token, title: "Nancy", body: message, sound: "default"}
- Add a `pushed_at` guard (or reuse nudge-fired) so no double-send.

## Critical testing notes
- Push tokens DON'T work on iOS Simulator — need a physical device or a
  dev/standalone build. (Local notifs work on simulator; push does not.)
- Expo Push → APNs/FCM: Expo handles cert complexity for dev. Production
  standalone builds need APNs key (Apple) + FCM setup — part of store launch.
- Test end-to-end: set a reminder 3 min out → close app fully → confirm push
  arrives on the (physical) device with app closed.

## Sequence
1. Piece 1 (cron) — biggest win, activates server-side firing. Verify heartbeat runs.
2. Piece 2 (tokens) — table + endpoint + frontend registration.
3. Piece 3 (push send) — hook into the firing loop.
4. Test on a physical device, app closed.

## Interim state (today)
Local-notification sync on app-open (mobile) is live + committed — good foreground/
recently-opened coverage. Server push is the guarantee layer added next.

# Nancy — Project Status & Reference

_Last updated: 13 August 2026_

A warm, Hinglish AI companion for elderly users, with caregiver alerts. This
document is the current-state reference: what's built, how it fits together,
what's ready for multiple users, and what's deferred.

---

## 1. The big picture (architecture)

Nancy is built around one principle: **the LLM comprehends (meaning), code
executes (mechanics).** Applied at every layer.

Two foundational ideas:

1. **Memory is the always-on substrate** — everything the user says flows into
   memory (two tracks). Memory is never gated by anything; a misclassification
   must never cause memory loss ("fail toward did-less").
2. **The router (planned) is the universal coarse dispatch** — one classification
   pass routes each message conditionally to APIs/modules, and addressably to the
   right memory location. Modules (reminders, agents, recommendations) subscribe.
   *Not built yet — earned from 2+ concrete modules.*

### Two-track memory

- **Track 1 — Narrative (the compounding summary).** Emotional/relational texture.
  Each session is summarized; summaries compound over time into a rich profile.
  Lossy on specifics, strong on the "who this person is" story.
- **Track 2 — Clusters (precise facts).** Entities (people, health, interests)
  with strength, decay, attributes, trajectory. Precise on specifics.

The two tracks cover each other's blind spots. Recall blends both.

### Progressive compression tiers

`Cache (raw, fast decay) -> STM (fused, 7d) -> LTM (distilled) -> Summary (permanent)`
- Cache: raw, fast decay (~42s half-life), read-time lazy decay.
- STM: summarized/fused, no decay until 7d.
- LTM: distilled, slow decay (~95d half-life). Note: promotion to LTM rarely
  fires (needs recall>=3); the Summary does the long-term job.
- Summary: the permanent compounding narrative (Track 1).

### The heartbeat spine

An external cron (cron-job.org) pings endpoints on a schedule. This one pattern
drives all periodic work — proven across three subscribers:
- Auto-summarizer (`/debug/backstop`, 15-min) — summarizes idle sessions.
- Cluster-cleaner (rides the full scheduler pass) — Track 2 distillation.
- Reminder firing (`/debug/fire-reminders`, 5-min) — fires due reminders.

---

## 2. What's built and working

### Memory (both tracks — DONE, self-maintaining)
- Cross-session compounding summary (verified)
- Auto-summarizer catches never-returning users (live on cron)
- Soft-delete, user-scoped decay, STM cleanup, 3072-dim vectors
- Track 2 clean canonical clusters
- Cluster-cleaner: vector-candidate + LLM confirm/merge/rename/drop (live on heartbeat)
- Summarizer correctly attributes to the user, never mislabels as "Nancy" (verified)
- Memory viewer: `/view/memory/{user_id}` (both tracks + tier state)

The cluster-cleaner is Track 2 distillation: centroid cosine finds merge
candidates (vectors propose similarity), an LLM confirms same-entity + supplies
canonical labels (LLM supplies meaning), then merge/rename/drop is applied.
Conservative — never over-merges distinct entities.

### Reactive engine — Reminders (first module — DONE, end to end)
1. Capture — "kal 12 baje doctor yaad dilana" (natural Hinglish)
2. Resolve — relative time -> absolute, using the user's real clock (`time_context`, IST default)
3. Store — `reminders` table, absolute UTC `fire_at`
4. Confirm — chat returns a structured `reminder` event (a card)
5. Visible — reminders tab: `GET /reminders/{user_id}`, plus cancel/update
6. Fire — heartbeat (`/debug/fire-reminders`, 5-min cron)
7. Deliver — `/proactive/{user_id}` surfaces a fired reminder first, once (via `delivered_at`)

### Inspection / continuous improvement
- Excel export: `GET /export/memory-xlsx?user_id=optional` — 5 sheets
  (Track1_Narrative, Track2_Clusters, Sessions, Messages, Reminders).
- `./report.sh [user_id]` — one-command timestamped download + open.

---

## 3. Multi-user readiness

**Ready for: testing with a few users -> rolling out to first few users.**

### What IS ready (the hard-to-retrofit part — done right)
- Data isolation is correct — everything scoped by `user_id`. Users can't see or
  corrupt each other's data. (The one cross-user leak — `decay_stm` — was fixed.)
- Pipelines are per-user; adding users doesn't break logic.
- Sessions per-user (hybrid continue-or-fresh); concurrent users work.

### What is NOT yet production-hardened (deferred, by plan)
1. Auth — ONE shared API key; no per-user login. First security item before real
   (non-trusted) users: per-user tokens + Row-Level Security.
2. Performance at scale — synchronous DB calls, Python-parsed vectors (not native
   pgvector). Fine to low-hundreds of users.
3. Cluster-cleaner LLM cost — one call per active user per heartbeat; needs an
   "only if changed" guard at higher scale.
4. No rate limiting / per-user quotas.

**Bottom line:** the multi-user foundation (isolation) is correct — the hard part.
Auth + performance are additive layers, planned before wider launch.

---

## 4. Roadmap — Phase 1 (to first users)

1. [DONE] Memory (both tracks, tested, visualized, inspectable)
2. [DONE] Reminders (reactive engine's first module, end to end)
3. Frontend — app screens (chat, memory, reminders tab)
4. API integrations (the "armory" — weather, music, news, places)
5. Recommendations — reads the clean Track 2 clusters (the flywheel)
6. Agents — e.g. order agents; the second router module. Design rule:
   confirmation before consequence (any action costing money / committing /
   hard-to-undo must confirm first).
7. The router — extracted once 2+ modules exist (reminders + agents). Stays
   coarse (dispatch only) or it becomes a god-object. Never gates memory.
8. Before real users: security hardening (auth/RLS/key rotation) + eval harness.
9. Extensive testing -> roll out to first few users.

---

## 5. Key design principles

- LLM comprehends, code executes — at every layer.
- Memory = always-on substrate; router = coarse dispatch; modules = subscribers.
- Fail toward "did less," not "did wrong."
- Two differently-lossy tracks = don't-lose-context.
- Vectors propose similarity; the LLM supplies meaning. (The cluster-cleaner is
  the clearest instance — the design philosophy in one line.)
- Earn abstractions from 2+ concrete instances.
- Confirmation before consequence — especially for agents.
- Test at depth on clean data; inspect clusters directly (the summary smooths
  over cluster bugs — why the export + viewer matter).

---

## 6. Deferred / parked (consciously)

- Native pgvector + HNSW (scale, ~100+ users)
- Fusion nodes / meta-clusters / super-clusters (20-50 users)
- Trajectory on clusters computes when data flows (BP showed "improving");
  matters more for health-alerting later
- Railway-native cron (external pinger works for now)
- Router / merging the 2 extraction LLM calls into 1
- Security: JWT / RLS / rotate keys — the gate before real users
- Voice integration
- Eval harness (labeled test set -> pass/fail per failure-class)
- Push notifications (app-open proactive delivery works now)
- Re-summarize old stale test summaries (cosmetic; not worth it)

---

## 7. Operational reference

- Working dir: `~/Developer/AI-Memory-Implementation-fresh` (NOT iCloud)
- Repo: github.com/ajayrath94/AI-Memory-Implementation, branch `staging`
- Prod: https://ai-memory-implementation-production.up.railway.app (Railway HOBBY)
- Deploys take ~9 min — always confirm health 200 before testing.
- Crons (cron-job.org): `/debug/backstop` (15-min), `/debug/fire-reminders` (5-min)
- Models: chat = Claude Haiku; extraction/embeddings = Gemini; summarizer +
  cluster-cleaner + reminder extraction = Claude Haiku.
- Timezone: `time_context.py` resolves per-user local time (defaults IST).

### Key endpoints
| Endpoint | Purpose |
|---|---|
| `POST /chat/` | Main chat (returns `reminder` event when one is set) |
| `GET /reminders/{user_id}` | Reminders tab (upcoming + past) |
| `POST /reminders/{id}/cancel` / `/update` | Correction loop |
| `GET /schedule/proactive/{user_id}` | Proactive open (fired reminders first) |
| `GET /view/memory/{user_id}` | Memory viewer (both tracks) |
| `GET /export/memory-xlsx` | 5-sheet inspection workbook |
| `GET /debug/scheduler-pass?dry_run=false` | Full heartbeat |
| `POST /debug/fire-reminders` | Lightweight reminder firing |
| `POST /debug/clean-clusters/{user_id}?dry_run=` | Manual cluster-cleaner |

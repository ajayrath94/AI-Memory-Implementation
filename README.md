# AI Memory Implementation

A multi-engine AI chat with a three-layered vector memory system based on pillar classification and cosine similarity.

## Architecture

```
Voice / Text Interface
        ↓
   AI Engine (Sonnet / Haiku / Opus)
        ↓
  Pillar Classifier  →  Core · Emotion · Functional · Modifiers → 3×3 Matrix
        ↓
  ┌─────────────────────────────────────┐
  │         Memory System               │
  │  Cache → Recall (STM/LTM) → Decay  │
  └─────────────────────────────────────┘
        ↓
  Pillar Vector Store (cosine similarity + correlation tracking)
```

## Memory Layers

| Layer | File | Formula | Decay Rate |
|---|---|---|---|
| Cache | `memory/cache/CacheMemory.js` | `M(x,t) = (1-α)·M(x,t-1) + α·I(x,t)` | λ=1.0 (minutes) |
| Recall STM | `memory/recall/RecallMemory.js` | `cos(I(t), M_c) > θ` | λ=0.1 (hours) |
| Recall LTM | `memory/recall/RecallMemory.js` | cosine similarity retrieval | λ=0.01 (days) |
| Decay | `memory/decay/DecayMemory.js` | `M(x,t) = M(x,t₀)·e^(-λ(t-t₀))` | tier-specific |

## Pillar System

**Core Pillars:** FINANCE · ASPIRATIONS · CAREER_GOAL · HEALTH_WELLNESS · ENTERTAINMENT · GENERAL

**Emotion Pillars:** OPTIMISM · JOY · FEAR · SADNESS · ANGER · STRESS · NEUTRAL

**Functional Pillars:** PLAN · SEARCH · ORDER · TRACK · NUDGE · CHAT

**Modifiers:** QUANTITY · SPECIFICITY · FORMAT · LOCATION · EXCLUSION · URGENCY · CONDITION · PREFERENCE · TEMPORAL · COMPARISON

## Getting Started

```bash
npm install
cp .env.example .env.local
# Add your VITE_ANTHROPIC_API_KEY to .env.local
npm run dev
```

## Phase 2 (after MVP)
- [ ] Replace `textToVector` with Anthropic Embeddings API
- [ ] Connect LTM store to Supabase / Postgres
- [ ] Add user auth (memories scoped per user)
- [ ] Add memory debug panel (visualize active slots + decay state)

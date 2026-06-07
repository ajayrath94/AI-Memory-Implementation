/**
 * RECALL MEMORY
 * Implements vector resonance retrieval from the paper.
 *
 * Trigger condition: cos(I(t), M_c) > θ
 * Expansion:         M(x,t) = E(M_c)
 * Reintegration:     M'(x,t) = (1-α)·E(M_c) + α·I(x,t)
 *
 * Two tiers:
 *   STM — short-term memory (minutes → hours)
 *   LTM — long-term memory  (days → weeks, DB later)
 */

import { getActiveSlots } from '../cache/CacheMemory.js'

const RECALL_THRESHOLD = 0.3   // θ — cosine similarity threshold to trigger recall
const STM_MAX = 50             // max entries in short-term memory
const LTM_MAX = 200            // max entries in long-term memory (in-memory for now)

// In-memory stores (will be swapped for DB in phase 2)
let stmStore = []
let ltmStore = []

// ── Simple term-frequency vector ──────────────────────────────────────────────

/**
 * Build a simple keyword vector from text for cosine similarity.
 * In phase 2, swap this for real embeddings (e.g. Anthropic embed API).
 */
function textToVector(text) {
  const words = text.toLowerCase().replace(/[^a-z\s]/g, '').split(/\s+/)
  const freq = {}
  words.forEach(w => { if (w.length > 2) freq[w] = (freq[w] ?? 0) + 1 })
  return freq
}

function cosineSimilarity(vecA, vecB) {
  const keysA = Object.keys(vecA)
  const keysB = new Set(Object.keys(vecB))

  const dot    = keysA.reduce((sum, k) => sum + (vecA[k] ?? 0) * (vecB[k] ?? 0), 0)
  const magA   = Math.sqrt(keysA.reduce((sum, k) => sum + vecA[k] ** 2, 0))
  const magB   = Math.sqrt([...keysB].reduce((sum, k) => sum + vecB[k] ** 2, 0))

  if (magA === 0 || magB === 0) return 0
  return dot / (magA * magB)
}

// ── Store a memory ────────────────────────────────────────────────────────────

export function storeMemory(text, metadata = {}) {
  const entry = {
    text,
    vector:    textToVector(text),
    metadata,
    timestamp: Date.now(),
    strength:  1.0,
    recallCount: 0,
  }

  stmStore.unshift(entry)

  // Promote oldest STM entries to LTM when STM is full
  if (stmStore.length > STM_MAX) {
    const promoted = stmStore.splice(STM_MAX)
    ltmStore.unshift(...promoted)
    if (ltmStore.length > LTM_MAX) ltmStore = ltmStore.slice(0, LTM_MAX)
  }
}

// ── Recall ────────────────────────────────────────────────────────────────────

/**
 * Find memories that resonate with the current input above threshold θ.
 * Searches STM first (faster), then LTM.
 */
export function recall(inputText, topK = 3) {
  const inputVec = textToVector(inputText)
  const candidates = [...stmStore, ...ltmStore]

  const scored = candidates
    .map(entry => ({
      entry,
      score: cosineSimilarity(inputVec, entry.vector),
    }))
    .filter(({ score }) => score > RECALL_THRESHOLD)
    .sort((a, b) => b.score - a.score)
    .slice(0, topK)

  // Reinforce recalled memories
  scored.forEach(({ entry }) => {
    entry.recallCount += 1
    entry.strength = Math.min(1.0, entry.strength + 0.1)
  })

  return scored.map(({ entry, score }) => ({ text: entry.text, score, metadata: entry.metadata }))
}

// ── Build memory context string for prompt injection ──────────────────────────

export function buildMemoryContext(inputText) {
  const recalled = recall(inputText)
  if (recalled.length === 0) return null

  return recalled
    .map(({ text, score }) => `[memory: ${Math.round(score * 100)}% match] ${text}`)
    .join('\n')
}

// ── Auto-store cache snapshot into recall ─────────────────────────────────────

/**
 * Called after each turn to compress active cache into recall store.
 * Implements the compression-as-logic paradigm from the paper.
 */
export function compressToRecall() {
  const activeSlots = getActiveSlots()
  if (activeSlots.length === 0) return

  const summary = activeSlots
    .filter(s => s.strength > 0.3)
    .map(s => `${s.key}: ${s.value}`)
    .join(', ')

  if (summary) storeMemory(summary, { source: 'cache_compression', ts: Date.now() })
}

// ── Getters ───────────────────────────────────────────────────────────────────

export function getSTM() { return [...stmStore] }
export function getLTM() { return [...ltmStore] }

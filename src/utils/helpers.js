/**
 * SHARED UTILITIES
 * Helpers used across the memory pipeline.
 * Phase 2: swap textToVector for real Anthropic embeddings.
 */

// ── Timestamp helpers ──────────────────────────────────────────────────────────

export const now = () => Date.now()

export function minutesElapsed(timestamp) {
  return (Date.now() - timestamp) / 60000
}

export function hoursElapsed(timestamp) {
  return (Date.now() - timestamp) / 3600000
}

export function daysElapsed(timestamp) {
  return (Date.now() - timestamp) / 86400000
}

export function formatAge(timestamp) {
  const mins = minutesElapsed(timestamp)
  if (mins < 60)    return `${Math.round(mins)}m ago`
  if (mins < 1440)  return `${Math.round(mins / 60)}h ago`
  return `${Math.round(mins / 1440)}d ago`
}

// ── Text compression helpers ──────────────────────────────────────────────────

/**
 * Compress a block of text to key terms only.
 * Phase 2: replace with LLM summarization call.
 */
export function compressText(text, maxWords = 20) {
  const stopWords = new Set(['the','a','an','is','it','in','on','at','to','for','of','and','or','but','with','this','that','was','are','be','have','has'])
  const words = text.toLowerCase().split(/\s+/).filter(w => !stopWords.has(w) && w.length > 2)
  return [...new Set(words)].slice(0, maxWords).join(' ')
}

// ── Vector helpers ────────────────────────────────────────────────────────────

/**
 * Build a simple TF-IDF-style vector from text.
 * Phase 2: replace with Anthropic embed API.
 */
export function textToVector(text) {
  const words = text.toLowerCase().replace(/[^a-z\s]/g, '').split(/\s+/)
  const freq = {}
  words.forEach(w => { if (w.length > 2) freq[w] = (freq[w] ?? 0) + 1 })
  return freq
}

export function cosineSimilarity(vecA, vecB) {
  const dot  = Object.keys(vecA).reduce((sum, k) => sum + (vecA[k] ?? 0) * (vecB[k] ?? 0), 0)
  const magA = Math.sqrt(Object.values(vecA).reduce((s, v) => s + v ** 2, 0))
  const magB = Math.sqrt(Object.values(vecB).reduce((s, v) => s + v ** 2, 0))
  if (magA === 0 || magB === 0) return 0
  return dot / (magA * magB)
}

// ── Alpha-blend helper ────────────────────────────────────────────────────────

/**
 * M(x,t) = (1-α)·M(x,t-1) + α·I(x,t)
 */
export function alphaBlend(oldVal, newVal, alpha = 0.4) {
  return (1 - alpha) * oldVal + alpha * newVal
}

// ── Exponential decay ─────────────────────────────────────────────────────────

/**
 * M(x,t) = M(x,t₀)·e^(-λ(t-t₀))
 */
export function exponentialDecay(strength, lambda, elapsedUnits) {
  return strength * Math.exp(-lambda * elapsedUnits)
}

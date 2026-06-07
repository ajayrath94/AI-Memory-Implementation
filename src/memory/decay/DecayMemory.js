/**
 * DECAY MEMORY
 * Implements the thermodynamic forgetting model from the paper.
 *
 * Base decay:     M(x,t) = M(x,t₀)·e^(-λₓ(t-t₀))
 * Global flow:    ∂M/∂t = -Λ⊙M
 * Void threshold: |M(x,t)| < ε → slot eligible for recycling
 *
 * Decay rate hierarchy (per paper):
 *   λ_cache = 1.0  (seconds → minutes)
 *   λ_stm   = 0.1  (minutes → hours)
 *   λ_ltm   = 0.01 (hours → days)
 */

import { applyDecay as applyCacheDecay, getCache } from '../cache/CacheMemory.js'
import { getSTM, getLTM } from '../recall/RecallMemory.js'

export const DECAY_RATES = {
  cache: 1.0,
  stm:   0.1,
  ltm:   0.01,
}

export const VOID_THRESHOLD = 0.05  // ε from the paper

// Track last decay run
let lastDecayRun = Date.now()

// ── Decay application ─────────────────────────────────────────────────────────

/**
 * Apply decay to a memory entry based on its tier.
 * Returns updated strength, or null if voided.
 */
export function decayEntry(entry, tier) {
  const lambda = DECAY_RATES[tier] ?? DECAY_RATES.stm
  const now = Date.now()

  // Convert elapsed time based on tier
  let elapsed
  if (tier === 'cache') elapsed = (now - entry.timestamp) / 60000        // minutes
  else if (tier === 'stm') elapsed = (now - entry.timestamp) / 3600000   // hours
  else elapsed = (now - entry.timestamp) / 86400000                       // days

  const decayedStrength = entry.strength * Math.exp(-lambda * elapsed)

  return decayedStrength < VOID_THRESHOLD ? null : decayedStrength
}

// ── System-wide decay tick ─────────────────────────────────────────────────────

/**
 * Run decay across all memory tiers.
 * Called once per user turn (not on a timer — event-driven per paper's δ(t-tᵤ)).
 */
export function trackDecay() {
  const now = Date.now()
  lastDecayRun = now

  // Cache decay — handled inside CacheMemory itself
  applyCacheDecay()

  // STM + LTM decay — update strength values in place
  const stm = getSTM()
  const ltm = getLTM()

  let stmVoided = 0, ltmVoided = 0

  stm.forEach(entry => {
    const newStrength = decayEntry(entry, 'stm')
    if (newStrength === null) {
      entry.strength = 0  // mark for cleanup
      stmVoided++
    } else {
      entry.strength = newStrength
    }
  })

  ltm.forEach(entry => {
    const newStrength = decayEntry(entry, 'ltm')
    if (newStrength === null) {
      entry.strength = 0
      ltmVoided++
    } else {
      entry.strength = newStrength
    }
  })

  if (stmVoided > 0 || ltmVoided > 0) {
    console.log(`[DecayMemory] Voided — STM: ${stmVoided}, LTM: ${ltmVoided}`)
  }
}

// ── Entropy report ────────────────────────────────────────────────────────────

/**
 * System entropy S(t) = Σ(1 - e^(-λᵢ(t-t₀)))
 * High entropy = lots of forgotten/faded memory.
 * Low entropy = fresh, strong memory field.
 */
export function systemEntropy() {
  const now = Date.now()
  const cache = Object.values(getCache())
  const stm   = getSTM()
  const ltm   = getLTM()

  const computeEntropy = (entries, tier) =>
    entries.reduce((sum, entry) => {
      const lambda  = DECAY_RATES[tier]
      const elapsed = (now - entry.timestamp) / 60000
      return sum + (1 - Math.exp(-lambda * elapsed))
    }, 0)

  return {
    cache: computeEntropy(cache, 'cache'),
    stm:   computeEntropy(stm,   'stm'),
    ltm:   computeEntropy(ltm,   'ltm'),
    total: computeEntropy([...cache, ...stm, ...ltm], 'stm'),
    lastRun: lastDecayRun,
  }
}

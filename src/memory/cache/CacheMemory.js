/**
 * CACHE MEMORY
 * Implements the vector field M(x,t) from the paper.
 *
 * Core update rule:   M(x,t) = (1-α)·M(x,t-1) + α·I(x,t)
 * Decay function:     M(x,t) = M(x,t₀)·e^(-λ(t-t₀))
 * Decay constant:     λ_cache = 1.0 (seconds → minutes scale)
 */

const ALPHA = 0.4          // memory plasticity — how fast new info overrides old
const LAMBDA_CACHE = 1.0   // decay constant for cache layer (fastest)
const VOID_THRESHOLD = 0.05 // ε — below this, slot is considered void

// In-memory vector field: { slotKey: { value, strength, timestamp, pillar } }
let cacheField = {}

// ── Update rule ────────────────────────────────────────────────────────────────

/**
 * Update a memory slot using the α-blend rule from the paper.
 * M(x,t) = (1-α)·M(x,t-1) + α·I(x,t)
 */
function updateSlot(key, newValue, pillar) {
  const existing = cacheField[key]

  if (!existing) {
    // New slot — initialize with full strength
    cacheField[key] = {
      value:     newValue,
      strength:  1.0,
      timestamp: Date.now(),
      pillar,
      accessCount: 1,
    }
    return
  }

  // α-blend: weighted average of old and new value
  const blendedStrength = (1 - ALPHA) * existing.strength + ALPHA * 1.0

  cacheField[key] = {
    value:       newValue,
    strength:    blendedStrength,
    timestamp:   Date.now(),
    pillar,
    accessCount: existing.accessCount + 1,
  }
}

// ── Main update ────────────────────────────────────────────────────────────────

export function updateCache(classified) {
  const { core, emotion, functional, modifiers, text, timestamp } = classified

  // Each pillar dimension becomes a slot in the vector field
  updateSlot('core',       core,       'CORE')
  updateSlot('emotion',    emotion,    'EMOTION')
  updateSlot('functional', functional, 'FUNCTIONAL')
  updateSlot('last_input', text,       'RAW')

  // Modifiers each get their own slot
  modifiers.forEach(mod => {
    updateSlot(`modifier_${mod}`, mod, 'MODIFIER')
  })

  console.log('[CacheMemory] Updated field:', Object.keys(cacheField))
}

// ── Decay function ─────────────────────────────────────────────────────────────

/**
 * Apply exponential decay to all slots:
 * M(x,t) = M(x,t₀)·e^(-λ(t-t₀))
 * Measured in minutes for cache layer.
 */
export function applyDecay() {
  const now = Date.now()
  const voidedSlots = []

  for (const [key, slot] of Object.entries(cacheField)) {
    const minutesElapsed = (now - slot.timestamp) / 60000
    const decayed = slot.strength * Math.exp(-LAMBDA_CACHE * minutesElapsed)

    if (decayed < VOID_THRESHOLD) {
      voidedSlots.push(key)
    } else {
      cacheField[key] = { ...slot, strength: decayed }
    }
  }

  // Remove voided slots
  voidedSlots.forEach(key => {
    console.log('[CacheMemory] Voided slot:', key)
    delete cacheField[key]
  })
}

// ── Read ───────────────────────────────────────────────────────────────────────

export function getCache() {
  return { ...cacheField }
}

export function getCacheSlot(key) {
  return cacheField[key] ?? null
}

/**
 * Get active slots sorted by strength (strongest memory first).
 */
export function getActiveSlots() {
  return Object.entries(cacheField)
    .sort((a, b) => b[1].strength - a[1].strength)
    .map(([key, slot]) => ({ key, ...slot }))
}

// ── Reset ──────────────────────────────────────────────────────────────────────

export function clearCache() {
  cacheField = {}
}

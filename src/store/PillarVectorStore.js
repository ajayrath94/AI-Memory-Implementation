/**
 * PILLAR VECTOR STORE
 * Tracks pillar vectors and their cross-pillar correlations over time.
 *
 * Formula: y = m·x^n
 *   x = pillar matrix
 *   m = slope (intensity/weight of the pillar)
 *   n = count (how many times this pillar has appeared)
 *
 * Cosine similarity tracks which pillars co-occur and correlate.
 */

// Pillar occurrence history: { 'FINANCE': { count, weight, lastSeen } }
let pillarRegistry = {}

// Correlation matrix: { 'FINANCE_STRESS': { count, strength } }
let correlationMatrix = {}

// ── Register a classified input ───────────────────────────────────────────────

export function registerPillars(classified) {
  const { core, emotion, functional, modifiers } = classified
  const activePillars = [core, emotion, functional, ...modifiers].filter(Boolean)

  // Update occurrence counts
  activePillars.forEach(pillar => {
    if (!pillarRegistry[pillar]) {
      pillarRegistry[pillar] = { count: 0, weight: 1.0, lastSeen: Date.now() }
    }
    pillarRegistry[pillar].count    += 1
    pillarRegistry[pillar].lastSeen  = Date.now()
    // weight = m·x^n (slope × count^n, simplified as log growth)
    pillarRegistry[pillar].weight    = Math.log1p(pillarRegistry[pillar].count)
  })

  // Track co-occurrences (pairwise correlations)
  for (let i = 0; i < activePillars.length; i++) {
    for (let j = i + 1; j < activePillars.length; j++) {
      const key = [activePillars[i], activePillars[j]].sort().join('_')
      if (!correlationMatrix[key]) {
        correlationMatrix[key] = { count: 0, strength: 0 }
      }
      correlationMatrix[key].count    += 1
      correlationMatrix[key].strength  = Math.log1p(correlationMatrix[key].count)
    }
  }
}

// ── Query correlations ────────────────────────────────────────────────────────

/**
 * Get the strongest correlated pillar for a given pillar.
 * e.g. "FINANCE" → "STRESS" if they frequently co-occur.
 */
export function getTopCorrelations(pillar, topK = 3) {
  return Object.entries(correlationMatrix)
    .filter(([key]) => key.includes(pillar))
    .sort((a, b) => b[1].strength - a[1].strength)
    .slice(0, topK)
    .map(([key, data]) => {
      const other = key.replace(pillar + '_', '').replace('_' + pillar, '')
      return { pillar: other, ...data }
    })
}

/**
 * Get all pillars ranked by weight (most dominant first).
 */
export function getDominantPillars(topK = 5) {
  return Object.entries(pillarRegistry)
    .sort((a, b) => b[1].weight - a[1].weight)
    .slice(0, topK)
    .map(([pillar, data]) => ({ pillar, ...data }))
}

// ── Cosine similarity between two pillar vectors ──────────────────────────────

/**
 * Compare two pillar sets as binary presence vectors.
 * Used to find how similar two conversations are across pillar space.
 */
export function pillarCosineSimilarity(pillarsA, pillarsB) {
  const allPillars = [...new Set([...pillarsA, ...pillarsB])]
  const vecA = allPillars.map(p => pillarsA.includes(p) ? 1 : 0)
  const vecB = allPillars.map(p => pillarsB.includes(p) ? 1 : 0)

  const dot  = vecA.reduce((sum, v, i) => sum + v * vecB[i], 0)
  const magA = Math.sqrt(vecA.reduce((sum, v) => sum + v ** 2, 0))
  const magB = Math.sqrt(vecB.reduce((sum, v) => sum + v ** 2, 0))

  if (magA === 0 || magB === 0) return 0
  return dot / (magA * magB)
}

// ── Getters ───────────────────────────────────────────────────────────────────

export function getPillarRegistry() { return { ...pillarRegistry } }
export function getCorrelationMatrix() { return { ...correlationMatrix } }

export function resetStore() {
  pillarRegistry    = {}
  correlationMatrix = {}
}

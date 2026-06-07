/**
 * PILLAR CLASSIFIER
 * Classifies any input text into:
 *   - Core pillar (life domain)
 *   - Emotion pillar (emotional state)
 *   - Functional pillar (action intent)
 *   - Modifiers (refinement signals)
 * Then builds a 3x3 matrix per your paper spec.
 */

// ── Pillar definitions ────────────────────────────────────────────────────────

const CORE_PILLARS = {
  FINANCE:         ['money', 'budget', 'invest', 'expense', 'salary', 'savings', 'debt', 'cost', 'price', 'bank'],
  ASPIRATIONS:     ['dream', 'goal', 'future', 'ambition', 'hope', 'vision', 'aspire', 'achieve', 'want to be'],
  CAREER_GOAL:     ['job', 'career', 'work', 'promotion', 'skill', 'resume', 'interview', 'project', 'startup', 'business'],
  HEALTH_WELLNESS: ['health', 'exercise', 'diet', 'sleep', 'stress', 'mental', 'fitness', 'workout', 'eat', 'weight'],
  ENTERTAINMENT:   ['movie', 'music', 'game', 'book', 'show', 'watch', 'read', 'play', 'fun', 'enjoy'],
  GENERAL:         [], // fallback
}

const EMOTION_PILLARS = {
  OPTIMISM: ['excited', 'hopeful', 'confident', 'positive', 'great', 'awesome', 'motivated', 'happy'],
  JOY:      ['happy', 'joy', 'love', 'wonderful', 'amazing', 'fantastic', 'glad', 'thrilled'],
  FEAR:     ['scared', 'afraid', 'worried', 'nervous', 'anxious', 'fear', 'uncertain', 'unsure'],
  SADNESS:  ['sad', 'depressed', 'unhappy', 'down', 'lonely', 'miss', 'lost', 'disappointed'],
  ANGER:    ['angry', 'frustrated', 'annoyed', 'mad', 'upset', 'hate', 'irritated'],
  STRESS:   ['stress', 'overwhelmed', 'tired', 'exhausted', 'pressure', 'busy', 'burnout'],
  NEUTRAL:  [], // fallback
}

const FUNCTIONAL_PILLARS = {
  PLAN:   ['plan', 'schedule', 'organize', 'prepare', 'strategy', 'roadmap', 'layout'],
  SEARCH: ['find', 'search', 'look for', 'where', 'what is', 'who is', 'recommend'],
  ORDER:  ['order', 'buy', 'get', 'purchase', 'book', 'reserve'],
  TRACK:  ['track', 'monitor', 'follow', 'check', 'status', 'progress', 'update'],
  NUDGE:  ['remind', 'nudge', 'notify', 'alert', 'don\'t forget', 'make sure'],
  CHAT:   [], // fallback - general conversation
}

const MODIFIERS = {
  QUANTITY:    ['how many', 'how much', 'number', 'count', 'total', 'amount'],
  SPECIFICITY: ['specific', 'exactly', 'particular', 'precise', 'detail'],
  FORMAT:      ['list', 'table', 'summary', 'brief', 'detailed', 'format', 'explain'],
  LOCATION:    ['where', 'location', 'place', 'near', 'in ', 'at '],
  EXCLUSION:   ['not', 'except', 'without', 'avoid', 'exclude', 'don\'t'],
  URGENCY:     ['urgent', 'asap', 'now', 'immediately', 'today', 'quick', 'fast'],
  CONDITION:   ['if', 'when', 'unless', 'only if', 'in case', 'depends'],
  PREFERENCE:  ['prefer', 'like', 'want', 'would rather', 'favorite', 'best'],
  TEMPORAL:    ['yesterday', 'today', 'tomorrow', 'week', 'month', 'year', 'soon', 'later', 'ago'],
  COMPARISON:  ['vs', 'versus', 'compare', 'better', 'worse', 'difference', 'or'],
}

// ── Keyword scorer ─────────────────────────────────────────────────────────────

function scoreKeywords(text, keywordMap, fallback) {
  const lower = text.toLowerCase()
  const scores = {}

  for (const [pillar, keywords] of Object.entries(keywordMap)) {
    if (keywords.length === 0) continue
    scores[pillar] = keywords.filter(kw => lower.includes(kw)).length
  }

  const best = Object.entries(scores).sort((a, b) => b[1] - a[1])[0]
  return best && best[1] > 0 ? best[0] : fallback
}

function detectModifiers(text) {
  const lower = text.toLowerCase()
  return Object.entries(MODIFIERS)
    .filter(([, keywords]) => keywords.some(kw => lower.includes(kw)))
    .map(([mod]) => mod)
}

// ── 3x3 Matrix builder ─────────────────────────────────────────────────────────

/**
 * Matrix structure per paper:
 *            PRIMARY    SECONDARY    MODIFIER
 * SUBJECT →  [1,1]      [1,2]        [1,3]
 * ACTION  →  [2,1]      [2,2]        [2,3]
 * CONTEXT →  [3,1]      [3,2]        [3,3]
 */
function buildMatrix(core, emotion, functional, modifiers, text) {
  const words = text.split(' ')
  const subject = words.slice(0, 3).join(' ')   // rough subject extraction
  const action  = functional                      // functional pillar IS the action
  const context = emotion                         // emotion gives context

  return {
    subject: { primary: subject,    secondary: core,      modifier: modifiers[0] ?? null },
    action:  { primary: action,     secondary: functional, modifier: modifiers[1] ?? null },
    context: { primary: context,    secondary: emotion,   modifier: modifiers[2] ?? null },
  }
}

// ── Main export ────────────────────────────────────────────────────────────────

export function classifyInput(text) {
  const core       = scoreKeywords(text, CORE_PILLARS, 'GENERAL')
  const emotion    = scoreKeywords(text, EMOTION_PILLARS, 'NEUTRAL')
  const functional = scoreKeywords(text, FUNCTIONAL_PILLARS, 'CHAT')
  const modifiers  = detectModifiers(text)
  const matrix     = buildMatrix(core, emotion, functional, modifiers, text)

  return {
    text,
    core,
    emotion,
    functional,
    modifiers,
    matrix,
    timestamp: Date.now(),
  }
}

import { classifyInput } from '../classifier/PillarClassifier.js'
import { updateCache, getCache } from '../memory/cache/CacheMemory.js'
import { buildMemoryContext } from '../memory/recall/RecallMemory.js'
import { trackDecay } from '../memory/decay/DecayMemory.js'

/**
 * Main pipeline:
 * input → pillar classify → update cache → recall relevant memory → call AI → return reply
 */
export async function processInput(text, model, history) {
  // 1. Classify input into pillars + build 3x3 matrix
  const classified = classifyInput(text)
  console.log('[Classifier]', classified)

  // 2. Update cache memory with new classified input
  updateCache(classified)

  // 3. Run decay on stale slots
  trackDecay()

  // 4. Build memory context from recall layer
  const memoryContext = buildMemoryContext(text)

  // 5. Build system prompt injecting memory
  const systemPrompt = buildSystemPrompt(memoryContext, classified)

  // 6. Call Anthropic API
  const reply = await callClaude(text, model, history, systemPrompt)

  return reply
}

function buildSystemPrompt(memoryContext, classified) {
  return `You are a memory-aware AI assistant.

Current context classification:
- Core pillar: ${classified.core}
- Emotion pillar: ${classified.emotion}
- Functional pillar: ${classified.functional}
- Modifiers: ${classified.modifiers.join(', ') || 'none'}

${memoryContext ? `Relevant memory context:\n${memoryContext}` : ''}

Respond naturally and helpfully. Use the memory context when relevant.`
}

async function callClaude(text, model, history, systemPrompt) {
  const messages = [
    ...history.map(m => ({ role: m.role, content: m.content })),
    { role: 'user', content: text }
  ]

  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model,
      max_tokens: 1024,
      system: systemPrompt,
      messages,
    })
  })

  if (!res.ok) {
    const err = await res.text()
    throw new Error(`API error: ${err}`)
  }

  const data = await res.json()
  return data.content?.[0]?.text ?? '(no response)'
}

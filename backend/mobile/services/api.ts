import { API_BASE } from '../constants'

export interface Message {
  role:    'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  reply:       string
  classified:  { core: string; emotion: string; functional: string; modifiers: string[] }
  memory_used: boolean
}

export interface MemoryState {
  slots:   any[]
  entropy: { cache: number; stm: number; ltm: number }
  pillars: { dominant: any[]; correlations: any }
}

// ── Chat ───────────────────────────────────────────────────────────────────────

export async function sendMessage(
  text:    string,
  model:   string,
  history: Message[]
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat/`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ text, model, history }),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

// ── Memory state ───────────────────────────────────────────────────────────────

export async function fetchMemoryState(): Promise<MemoryState> {
  const [cacheRes, entropyRes, pillarsRes] = await Promise.all([
    fetch(`${API_BASE}/memory/cache`),
    fetch(`${API_BASE}/memory/entropy`),
    fetch(`${API_BASE}/memory/pillars`),
  ])
  const [cache, entropy, pillars] = await Promise.all([
    cacheRes.json(),
    entropyRes.json(),
    pillarsRes.json(),
  ])
  return { slots: cache.slots, entropy, pillars }
}

// ── Health check ───────────────────────────────────────────────────────────────

export async function checkBackend(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/`, { signal: AbortSignal.timeout(3000) })
    return res.ok
  } catch {
    return false
  }
}

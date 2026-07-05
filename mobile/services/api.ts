import { API_BASE, API_KEY } from '../constants'

export interface Message {
  role:    'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  reply:       string
  session_id:  string
  message_id:  string
  classified:  {
    core:          string
    emotion:       string
    functional:    string
    modifiers:     string[]
    core_score:    number
    keyword_count: number
  }
  memory_used: boolean
  model:       string
}

export async function sendMessage(
  text:       string,
  model:      string,
  session_id: string | null,
  user_id:    string = "default",
): Promise<ChatResponse> {
  // 60 second timeout — Supabase + AI can be slow
  const controller = new AbortController()
  const timeoutId  = setTimeout(() => controller.abort(), 60000)

  try {
    const res = await fetch(`${API_BASE}/chat/`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body:    JSON.stringify({ text, model, session_id, user_id }),
      signal:  controller.signal,
    })
    clearTimeout(timeoutId)
    if (!res.ok) {
      const err = await res.text()
      throw new Error(`API error: ${res.status} - ${err}`)
    }
    return res.json()
  } catch (err: any) {
    clearTimeout(timeoutId)
    if (err.name === 'AbortError') {
      throw new Error('Request timed out after 60 seconds')
    }
    throw err
  }
}

export async function checkBackend(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/`, { signal: AbortSignal.timeout(3000) })
    return res.ok
  } catch {
    return false
  }
}

import { API_BASE } from '../constants'

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
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat/`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ text, model, session_id }),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`API error: ${res.status} - ${err}`)
  }
  return res.json()
}

export async function checkBackend(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/`, { signal: AbortSignal.timeout(3000) })
    return res.ok
  } catch {
    return false
  }
}

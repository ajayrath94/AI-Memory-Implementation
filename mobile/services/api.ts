import { API_BASE } from '../constants'

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
  }
  memory_used: boolean
  model:       string
}

export async function sendMessage(
  text:       string,
  model:      string,
  session_id: string | null,
): Promise<ChatResponse> {
  const controller = new AbortController()
  const timeoutId  = setTimeout(() => controller.abort(), 60000)
  try {
    const res = await fetch(`${API_BASE}/chat/`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ text, model, session_id }),
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
    if (err.name === 'AbortError') throw new Error('Request timed out')
    throw err
  }
}

export async function endSession(session_id: string): Promise<void> {
  try {
    await fetch(`${API_BASE}/chat/end-session`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ session_id, user_id: 'default' }),
    })
  } catch (err) {
    console.log('End session error:', err)
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

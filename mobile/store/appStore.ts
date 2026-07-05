import { create } from 'zustand'
import { MODELS, API_BASE, API_KEY } from '../constants'

export interface Message {
  id:          string
  role:        'user' | 'assistant'
  content:     string
  model:       string
  timestamp:   number
  pillar?:     { core: string; emotion: string; functional: string }
  memoryUsed?: boolean
}

interface AppState {
  messages:    Message[]
  model:       string
  loading:     boolean
  sessionId:   string | null
  userId:      string        // real user_id — set after auth, default for now
  lastMeta:    { core: string; emotion: string; functional: string } | null
  memoryUsed:  boolean

  addMessage:    (msg: Message) => void
  setModel:      (model: string) => void
  setLoading:    (v: boolean) => void
  setSessionId:  (id: string | null) => void
  setUserId:     (id: string) => void
  setLastMeta:   (meta: any) => void
  setMemoryUsed: (v: boolean) => void
  clearChat:     () => void
  endSession:    () => Promise<void>
}

export const useAppStore = create<AppState>((set, get) => ({
  messages:   [],
  model:      MODELS[0].value,
  loading:    false,
  sessionId:  null,
  userId:     'default',   // will be replaced with real user_id after auth
  lastMeta:   null,
  memoryUsed: false,

  addMessage:    (msg)   => set(s => ({ messages: [...s.messages, msg] })),
  setModel:      (model) => set({ model }),
  setLoading:    (v)     => set({ loading: v }),
  setSessionId:  (id)    => set({ sessionId: id }),
  setUserId:     (id)    => set({ userId: id }),
  setLastMeta:   (meta)  => set({ lastMeta: meta }),
  setMemoryUsed: (v)     => set({ memoryUsed: v }),

  clearChat: () => {
    const { sessionId, userId } = get()
    // End current session before clearing
    if (sessionId) {
      fetch(`${API_BASE}/chat/end-session`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body:    JSON.stringify({ session_id: sessionId, user_id: userId }),
      }).catch(() => {})
    }
    set({ messages: [], lastMeta: null, sessionId: null, memoryUsed: false })
  },

  endSession: async () => {
    const { sessionId, userId } = get()
    if (!sessionId) return
    try {
      await fetch(`${API_BASE}/chat/end-session`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body:    JSON.stringify({ session_id: sessionId, user_id: userId }),
      })
      set({ sessionId: null })
      console.log('[Session] Ended:', sessionId)
    } catch (e) {
      console.log('[Session] End failed:', e)
    }
  },
}))

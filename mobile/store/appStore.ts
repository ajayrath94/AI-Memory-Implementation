import AsyncStorage from '@react-native-async-storage/async-storage'
import { create } from 'zustand'
import { MODELS } from '../constants'

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
  // When the app last went to background. Drives whether the companion opens
  // the conversation on return — see the proactive-open effect in index.tsx.
  lastSeenAt:  number | null
  // Kept locally so the first frame renders in the right language rather than
  // waiting on a network call. Reconciled with the profile at startup.
  language:    string
  userId:      string
  bgColor:     string
  lastMeta:    { core: string; emotion: string; functional: string } | null
  memoryUsed:  boolean

  addMessage:    (msg: Message) => void
  setModel:      (model: string) => void
  setLoading:    (v: boolean) => void
  setSessionId:  (id: string | null) => void
  setLastSeenAt: (t: number) => void
  setLanguage:   (l: string) => void
  setUserId:     (id: string) => void
  setBgColor:    (color: string) => void
  setLastMeta:   (meta: any) => void
  setMemoryUsed: (v: boolean) => void
  clearChat:     () => void
  endSession:    () => Promise<void>
  loadSession:   (id: string) => Promise<void>
}

export const useAppStore = create<AppState>((set, get) => ({
  messages:   [],
  model:      MODELS[0].value,
  loading:    false,
  sessionId:  null,
  lastSeenAt: null,
  language:   'hinglish',
  userId:     'default',
  bgColor:    '#0a0a0a',
  lastMeta:   null,
  memoryUsed: false,

  addMessage:    (msg)   => set(s => ({ messages: [...s.messages, msg] })),
  setModel:      (model) => {
    set({ model })
    // Held in memory only, so every launch reverted to MODELS[0] — and when
    // that was a model with no credits the app looked broken on opening.
    AsyncStorage.setItem('model', model).catch(() => {})
  },
  setLoading:    (v)     => set({ loading: v }),
  setSessionId:  (id)    => set({ sessionId: id }),
  setLastSeenAt: (t)     => set({ lastSeenAt: t }),
  setLanguage:   (l)     => set({ language: l }),
  setUserId:     (id)    => set({ userId: id }),
  setBgColor:    (color) => set({ bgColor: color }),
  setLastMeta:   (meta)  => set({ lastMeta: meta }),
  setMemoryUsed: (v)     => set({ memoryUsed: v }),

  clearChat: () => {
    const { sessionId, userId, endSession } = get()
    if (sessionId) endSession()
    set({ messages: [], lastMeta: null, sessionId: null, memoryUsed: false })
  },

  endSession: async () => {
    const { sessionId, userId } = get()
    if (!sessionId) return
    try {
      const { API_BASE, API_KEY } = require('../constants')
      await fetch(`${API_BASE}/chat/end-session`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body:    JSON.stringify({ session_id: sessionId, user_id: userId }),
      })
      set({ sessionId: null })
    } catch (e) {
      console.log('[Session] End failed:', e)
    }
  },
  loadSession: async (id: string) => {
    try {
      const { API_BASE, API_KEY } = require('../constants')
      const res  = await fetch(`${API_BASE}/memory/sessions/${id}/messages`, {
        headers: { 'X-API-Key': API_KEY },
      })
      const data = await res.json()
      const loaded: Message[] = (data.messages || []).map((m: any) => ({
        id:         m.id,
        role:       m.role,
        content:    m.content,
        model:      m.model,
        timestamp:  m.timestamp ? new Date(m.timestamp).getTime() : Date.now(),
        pillar:     m.pillar || undefined,
      }))
      set({ messages: loaded, sessionId: id })
    } catch (e) {
      console.log('[Session] Load failed:', e)
    }
  },
}))

// Read back on launch, beside loadLanguage(). Without this the persisted
// choice is written and never used.
export async function loadModel() {
  try {
    const saved = await AsyncStorage.getItem('model')
    if (saved) useAppStore.getState().setModel(saved)
  } catch {}
}

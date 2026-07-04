import { create } from 'zustand'
import { MODELS } from '../constants'

export interface Message {
  id:         string
  role:       'user' | 'assistant'
  content:    string
  model:      string
  timestamp:  number
  pillar?:    { core: string; emotion: string; functional: string }
  memoryUsed?: boolean
}

interface AppState {
  messages:    Message[]
  model:       string
  loading:     boolean
  sessionId:   string | null
  lastMeta:    { core: string; emotion: string; functional: string } | null
  memoryUsed:  boolean

  addMessage:    (msg: Message) => void
  setModel:      (model: string) => void
  setLoading:    (v: boolean) => void
  setSessionId:  (id: string) => void
  setLastMeta:   (meta: any) => void
  setMemoryUsed: (v: boolean) => void
  clearChat:     () => void
}

export const useAppStore = create<AppState>((set) => ({
  messages:   [],
  model:      MODELS[0].value,
  loading:    false,
  sessionId:  null,
  lastMeta:   null,
  memoryUsed: false,

  addMessage:    (msg)  => set(s => ({ messages: [...s.messages, msg] })),
  setModel:      (model) => set({ model }),
  setLoading:    (v)    => set({ loading: v }),
  setSessionId:  (id)   => set({ sessionId: id }),
  setLastMeta:   (meta) => set({ lastMeta: meta }),
  setMemoryUsed: (v)    => set({ memoryUsed: v }),
  clearChat:     ()     => set({ messages: [], lastMeta: null, sessionId: null }),
}))

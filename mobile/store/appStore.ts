import { create } from 'zustand'
import { Message } from '../services/api'
import { MODELS } from '../constants'

interface AppState {
  messages:    Message[]
  model:       string
  loading:     boolean
  lastMeta:    { core: string; emotion: string; functional: string } | null
  memoryUsed:  boolean

  addMessage:    (msg: Message) => void
  setModel:      (model: string) => void
  setLoading:    (v: boolean) => void
  setLastMeta:   (meta: any) => void
  setMemoryUsed: (v: boolean) => void
  clearChat:     () => void
}

export const useAppStore = create<AppState>((set) => ({
  messages:   [],
  model:      MODELS[0].value,
  loading:    false,
  lastMeta:   null,
  memoryUsed: false,

  addMessage:    (msg)  => set(s => ({ messages: [...s.messages, msg] })),
  setModel:      (model) => set({ model }),
  setLoading:    (v)    => set({ loading: v }),
  setLastMeta:   (meta) => set({ lastMeta: meta }),
  setMemoryUsed: (v)    => set({ memoryUsed: v }),
  clearChat:     ()     => set({ messages: [], lastMeta: null }),
}))

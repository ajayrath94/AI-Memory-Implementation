import { useCallback } from 'react'
import { useAppStore } from '../store/appStore'
import { sendMessage } from '../services/api'
import { API_BASE, API_KEY, DEFAULT_MODEL } from '../constants'

export function useChat() {
  const {
    model, sessionId, userId,
    addMessage, setLoading, setSessionId,
    setLastMeta, setMemoryUsed, messages,
  } = useAppStore()

  const send = useCallback(async (text: string) => {
    if (!text.trim()) return

    const userMsg = {
      id:        Date.now().toString(),
      role:      'user' as const,
      content:   text.trim(),
      model:     model || DEFAULT_MODEL,
      timestamp: Date.now(),
    }
    addMessage(userMsg)
    setLoading(true)

    try {
      const data = await sendMessage(text.trim(), model || DEFAULT_MODEL, sessionId, userId)

      if (data.session_id && !sessionId) {
        setSessionId(data.session_id)
      }

      addMessage({
        id:          data.message_id || (Date.now() + 1).toString(),
        role:        'assistant',
        content:     data.reply,
        model:       data.model || model,
        timestamp:   Date.now(),
        pillar:      data.classified ? {
          core:       data.classified.core,
          emotion:    data.classified.emotion,
          functional: data.classified.functional,
        } : undefined,
        memoryUsed:  data.memory_used,
      })

      setLastMeta(data.classified)
      setMemoryUsed(data.memory_used)

    } catch (err: any) {
      addMessage({
        id:        (Date.now() + 1).toString(),
        role:      'assistant',
        content:   'Sorry, something went wrong. Please try again.',
        model:     model,
        timestamp: Date.now(),
      })
      console.error('Chat error:', err)
    } finally {
      setLoading(false)
    }
  }, [model, sessionId, userId, addMessage, setLoading, setSessionId, setLastMeta, setMemoryUsed])

  // Edit & resend — soft deletes old messages in DB, resends new text
  const resend = useCallback(async (newText: string, messageId: string) => {
    const state    = useAppStore.getState()
    const msgs     = state.messages
    const idx      = msgs.findIndex(m => m.id === messageId)
    if (idx === -1) return

    // Get the Nancy reply that followed this message
    const replyMsg = msgs[idx + 1]?.role === 'assistant' ? msgs[idx + 1] : null

    // Trim UI messages from this point
    useAppStore.setState({ messages: msgs.slice(0, idx) })
    setLoading(true)

    try {
      // Call edit endpoint — soft deletes old, processes new
      const res = await fetch(`${API_BASE}/chat/edit`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body:    JSON.stringify({
          old_message_id: messageId,
          old_reply_id:   replyMsg?.id || null,
          new_text:       newText,
          model:          model || DEFAULT_MODEL,
          session_id:     sessionId,
          user_id:        userId,
        }),
      })

      const data = await res.json()

      // Add edited user message to UI
      addMessage({
        id:        Date.now().toString(),
        role:      'user',
        content:   newText,
        model:     model || DEFAULT_MODEL,
        timestamp: Date.now(),
      })

      // Add Nancy's new reply
      addMessage({
        id:          data.message_id || (Date.now() + 1).toString(),
        role:        'assistant',
        content:     data.reply,
        model:       data.model || model,
        timestamp:   Date.now(),
        memoryUsed:  data.memory_used,
      })

      if (data.session_id && !sessionId) {
        setSessionId(data.session_id)
      }

    } catch (err) {
      console.error('Resend error:', err)
      // Restore original messages on failure
      useAppStore.setState({ messages: msgs })
    } finally {
      setLoading(false)
    }
  }, [model, sessionId, userId, addMessage, setLoading, setSessionId])

  const clearAndSummarize = useCallback(() => {
    useAppStore.getState().clearChat()
  }, [])

  return { send, resend, clearAndSummarize }
}

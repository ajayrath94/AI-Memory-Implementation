import { useAppStore } from '../store/appStore'
import { sendMessage, endSession } from '../services/api'
import * as Haptics from 'expo-haptics'
import { API_BASE } from '../constants'

export function useChat() {
  const {
    messages, model, sessionId,
    addMessage, setLoading, setLastMeta,
    setMemoryUsed, setSessionId, clearChat
  } = useAppStore()

  const send = async (text: string) => {
    if (!text.trim()) return

    const userMsg = {
      id:        Date.now().toString(),
      role:      'user' as const,
      content:   text,
      model:     model,
      timestamp: Date.now(),
    }
    addMessage(userMsg)
    setLoading(true)

    try {
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
      const data = await sendMessage(text, model, sessionId)

      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id)
      }

      addMessage({
        id:         data.message_id || Date.now().toString(),
        role:       'assistant',
        content:    data.reply,
        model:      data.model,
        timestamp:  Date.now(),
        pillar:     data.classified,
        memoryUsed: data.memory_used,
      })

      setLastMeta(data.classified)
      setMemoryUsed(data.memory_used)

    } catch (err) {
      console.log('Error:', err)
      addMessage({
        id:        Date.now().toString(),
        role:      'assistant',
        content:   `⚠️ Error: ${err}`,
        model:     model,
        timestamp: Date.now(),
      })
    } finally {
      setLoading(false)
    }
  }

  // Call this when clearing chat or starting new session
  const endCurrentSession = async () => {
    if (!sessionId) return
    try {
      await endSession(sessionId)
      console.log('[useChat] Session ended and summarized:', sessionId)
    } catch (err) {
      console.log('[useChat] Session end error:', err)
    }
  }

  const clearAndSummarize = async () => {
    await endCurrentSession()
    clearChat()
  }

  return { send, endCurrentSession, clearAndSummarize }
}

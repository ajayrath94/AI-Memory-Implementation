import { useAppStore } from '../store/appStore'
import { sendMessage } from '../services/api'
import * as Haptics from 'expo-haptics'
import { API_BASE } from '../constants'

export function useChat() {
  const {
    messages, model, sessionId,
    addMessage, setLoading, setLastMeta,
    setMemoryUsed, setSessionId
  } = useAppStore()

  const send = async (text: string) => {
    if (!text.trim()) return

    // Add user message immediately
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

      console.log('Sending to:', `${API_BASE}/chat/`)
      console.log('Model:', model, 'Session:', sessionId)

      const data = await sendMessage(text, model, sessionId)

      // Save session_id for context continuity
      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id)
      }

      // Add assistant message with full metadata
      addMessage({
        id:        data.message_id,
        role:      'assistant',
        content:   data.reply,
        model:     data.model,
        timestamp: Date.now(),
        pillar:    data.classified,
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

  return { send }
}

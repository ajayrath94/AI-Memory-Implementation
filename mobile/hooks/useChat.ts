import { useAppStore } from '../store/appStore'
import { sendMessage } from '../services/api'
import * as Haptics from 'expo-haptics'

export function useChat() {
  const { messages, model, addMessage, setLoading, setLastMeta, setMemoryUsed } = useAppStore()

  const send = async (text: string) => {
    if (!text.trim()) return

    addMessage({ role: 'user', content: text })
    setLoading(true)

    try {
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
      const data = await sendMessage(text, model, messages)
      addMessage({ role: 'assistant', content: data.reply })
      setLastMeta(data.classified)
      setMemoryUsed(data.memory_used)
    } catch (err) {
      addMessage({ role: 'assistant', content: '⚠️ Could not reach backend. Is it running?' })
    } finally {
      setLoading(false)
    }
  }

  return { send }
}

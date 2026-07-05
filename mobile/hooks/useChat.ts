import { useAppStore } from '../store/appStore'
import { API_BASE } from '../constants'
import * as Haptics from 'expo-haptics'

export function useChat() {
  const { messages, model, addMessage, setLoading, setLastMeta, setMemoryUsed } = useAppStore()

  const send = async (text: string) => {
    if (!text.trim()) return

    addMessage({ role: 'user', content: text })
    setLoading(true)

    try {
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
      
      console.log('Sending to:', `${API_BASE}/chat/`)
      console.log('Model:', model)
      
      const res = await fetch(`${API_BASE}/chat/`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ text, model, history: messages }),
      })

      console.log('Response status:', res.status)
      
      if (!res.ok) {
        const errText = await res.text()
        console.log('Error body:', errText)
        throw new Error(`API error: ${res.status} - ${errText}`)
      }

      const data = await res.json()
      addMessage({ role: 'assistant', content: data.reply })
      setLastMeta(data.classified)
      setMemoryUsed(data.memory_used)
    } catch (err) {
      console.log('Full error:', err)
      addMessage({ role: 'assistant', content: `⚠️ Error: ${err}` })
    } finally {
      setLoading(false)
    }
  }

  return { send }
}

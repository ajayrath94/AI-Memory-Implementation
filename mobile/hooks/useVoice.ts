import { useState } from 'react'
import { Alert, Platform } from 'react-native'
import { Audio } from 'expo-av'
import * as Haptics from 'expo-haptics'

export function useVoice(onTranscript: (text: string) => void) {
  const [isListening, setIsListening] = useState(false)

  const startListening = async () => {
    try {
      // Request mic permission
      const { status } = await Audio.requestPermissionsAsync()
      if (status !== 'granted') {
        Alert.alert('Permission needed', 'Microphone access is required for voice input.')
        return
      }

      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium)

      // Try to load @react-native-voice/voice
      let Voice: any
      try {
        Voice = require('@react-native-voice/voice').default
      } catch {
        Alert.alert(
          'Voice not available',
          'Run: npx expo install @react-native-voice/voice\nThen rebuild the app.'
        )
        return
      }

      Voice.onSpeechResults = (e: any) => {
        const transcript = e.value?.[0]
        if (transcript) {
          onTranscript(transcript)
          setIsListening(false)
        }
      }
      Voice.onSpeechEnd   = () => setIsListening(false)
      Voice.onSpeechError = (e: any) => {
        console.error('Speech error:', e)
        setIsListening(false)
      }

      await Voice.start('en-US')
      setIsListening(true)
    } catch (err) {
      console.error('Voice start error:', err)
      setIsListening(false)
    }
  }

  const stopListening = async () => {
    try {
      const Voice = require('@react-native-voice/voice').default
      await Voice.stop()
      await Voice.destroy()
    } catch {}
    setIsListening(false)
  }

  const toggle = () => isListening ? stopListening() : startListening()

  return { isListening, toggle }
}

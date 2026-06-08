import { useState } from 'react'
import { Alert } from 'react-native'
import * as Haptics from 'expo-haptics'

export function useVoice(onTranscript: (text: string) => void) {
  const [isListening, setIsListening] = useState(false)

  const toggle = async () => {
    // Voice recognition requires a development build
    // It will work when you build the app properly
    // For now, show a message
    Alert.alert(
      'Voice Input',
      'Voice input will be available in the full app build. Use text input for now!',
      [{ text: 'OK' }]
    )
  }

  return { isListening, toggle }
}

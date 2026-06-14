import { useState, useRef } from 'react'
import { Alert, Platform } from 'react-native'
import { Audio } from 'expo-av'
import * as Haptics from 'expo-haptics'
import * as FileSystem from 'expo-file-system'
import { API_BASE } from '../constants'

export function useVoice(onTranscript: (text: string) => void) {
  const [isListening, setIsListening]   = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const recordingRef = useRef<Audio.Recording | null>(null)

  const startListening = async () => {
    try {
      // Request permissions
      const { status } = await Audio.requestPermissionsAsync()
      if (status !== 'granted') {
        Alert.alert('Permission needed', 'Microphone access is required for voice input.')
        return
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS:   true,
        playsInSilentModeIOS: true,
      })

      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium)

      // Start recording
      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      )
      recordingRef.current = recording
      setIsListening(true)

    } catch (err) {
      console.error('Start recording error:', err)
      Alert.alert('Error', 'Could not start recording. Please try again.')
    }
  }

  const stopListening = async () => {
    if (!recordingRef.current) return

    try {
      setIsListening(false)
      setIsProcessing(true)

      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)

      // Stop recording
      await recordingRef.current.stopAndUnloadAsync()
      const uri = recordingRef.current.getURI()
      recordingRef.current = null

      if (!uri) {
        setIsProcessing(false)
        return
      }

      // Send to backend for Groq Whisper transcription
      const formData = new FormData()
      formData.append('file', {
        uri,
        type: 'audio/m4a',
        name: 'recording.m4a',
      } as any)

      const res = await fetch(`${API_BASE}/voice/transcribe`, {
        method:  'POST',
        body:    formData,
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      if (!res.ok) {
        throw new Error(`Transcription failed: ${res.status}`)
      }

      const data = await res.json()
      if (data.transcript && data.transcript.trim()) {
        onTranscript(data.transcript.trim())
      }

    } catch (err) {
      console.error('Stop recording error:', err)
      Alert.alert('Voice Error', 'Could not transcribe audio. Please try typing instead.')
    } finally {
      setIsProcessing(false)
      // Reset audio mode
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false })
    }
  }

  const toggle = () => {
    if (isProcessing) return
    if (isListening) {
      stopListening()
    } else {
      startListening()
    }
  }

  return { isListening, isProcessing, toggle }
}

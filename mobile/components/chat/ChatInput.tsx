import React, { useState } from 'react'
import {
  View, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, Animated
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { Colors } from '../../constants'
import { useVoice } from '../../hooks/useVoice'

interface Props {
  onSubmit: (text: string) => void
  loading:  boolean
}

export function ChatInput({ onSubmit, loading }: Props) {
  const [text, setText] = useState('')
  const { isListening, isProcessing, toggle } = useVoice((transcript) => {
    onSubmit(transcript)
  })

  const send = () => {
    if (!text.trim() || loading) return
    onSubmit(text.trim())
    setText('')
  }

  const getMicColor = () => {
    if (isProcessing) return Colors.accent
    if (isListening)  return Colors.accentRed
    return Colors.textMuted
  }

  const getMicIcon = () => {
    if (isProcessing) return 'hourglass-outline'
    if (isListening)  return 'mic'
    return 'mic-outline'
  }

  const getMicBg = () => {
    if (isProcessing) return '#1a2a3a'
    if (isListening)  return '#3a1e1e'
    return Colors.bgInput
  }

  return (
    <View style={styles.container}>

      {/* Voice button */}
      <TouchableOpacity
        onPress={toggle}
        disabled={loading}
        style={[styles.voiceBtn, { backgroundColor: getMicBg() }]}
        activeOpacity={0.7}
      >
        {isProcessing ? (
          <ActivityIndicator size="small" color={Colors.accent} />
        ) : (
          <Ionicons name={getMicIcon()} size={22} color={getMicColor()} />
        )}
      </TouchableOpacity>

      {/* Text input */}
      <TextInput
        value={text}
        onChangeText={setText}
        placeholder={
          isListening   ? '🎙️ Listening...' :
          isProcessing  ? '⏳ Transcribing...' :
          'Type a message'
        }
        placeholderTextColor={Colors.textHint}
        multiline
        style={styles.input}
        onSubmitEditing={send}
        editable={!isListening && !isProcessing}
      />

      {/* Send button */}
      <TouchableOpacity
        onPress={send}
        disabled={!text.trim() || loading}
        style={[styles.sendBtn,
          (!text.trim() || loading) && styles.sendBtnDisabled]}
        activeOpacity={0.7}
      >
        {loading
          ? <ActivityIndicator size="small" color={Colors.text} />
          : <Ionicons name="arrow-up" size={20} color={Colors.text} />
        }
      </TouchableOpacity>

    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    flexDirection:     'row',
    alignItems:        'flex-end',
    paddingHorizontal: 12,
    paddingVertical:   10,
    borderTopWidth:    1,
    borderTopColor:    Colors.border,
    backgroundColor:   Colors.bg,
    gap: 8,
  },
  voiceBtn: {
    width:           42,
    height:          42,
    borderRadius:    21,
    borderWidth:     1,
    borderColor:     Colors.border,
    alignItems:      'center',
    justifyContent:  'center',
  },
  input: {
    flex:              1,
    backgroundColor:   Colors.bgInput,
    color:             Colors.text,
    borderWidth:       1,
    borderColor:       Colors.border,
    borderRadius:      20,
    paddingHorizontal: 14,
    paddingVertical:   10,
    fontSize:          15,
    maxHeight:         120,
  },
  sendBtn: {
    width:           42,
    height:          42,
    borderRadius:    21,
    backgroundColor: Colors.accent,
    alignItems:      'center',
    justifyContent:  'center',
  },
  sendBtnDisabled: { opacity: 0.35 },
})

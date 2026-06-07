import React, { useState } from 'react'
import { View, TextInput, TouchableOpacity, Text, StyleSheet, ActivityIndicator } from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { Colors } from '../../constants'
import { useVoice } from '../../hooks/useVoice'

interface Props {
  onSubmit: (text: string) => void
  loading:  boolean
}

export function ChatInput({ onSubmit, loading }: Props) {
  const [text, setText] = useState('')
  const { isListening, toggle } = useVoice((transcript) => {
    onSubmit(transcript)
  })

  const send = () => {
    if (!text.trim() || loading) return
    onSubmit(text.trim())
    setText('')
  }

  return (
    <View style={styles.container}>

      {/* Voice button */}
      <TouchableOpacity
        onPress={toggle}
        style={[styles.voiceBtn, isListening && styles.voiceBtnActive]}
        activeOpacity={0.7}
      >
        <Ionicons
          name={isListening ? 'mic' : 'mic-outline'}
          size={22}
          color={isListening ? Colors.accentRed : Colors.textMuted}
        />
      </TouchableOpacity>

      {/* Text input */}
      <TextInput
        value={text}
        onChangeText={setText}
        placeholder={isListening ? 'Listening…' : 'Type a message'}
        placeholderTextColor={Colors.textHint}
        multiline
        style={styles.input}
        returnKeyType="send"
        onSubmitEditing={send}
        editable={!isListening}
      />

      {/* Send button */}
      <TouchableOpacity
        onPress={send}
        disabled={!text.trim() || loading}
        style={[styles.sendBtn, (!text.trim() || loading) && styles.sendBtnDisabled]}
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
    flexDirection:   'row',
    alignItems:      'flex-end',
    paddingHorizontal: 12,
    paddingVertical:   10,
    borderTopWidth:  1,
    borderTopColor:  Colors.border,
    backgroundColor: Colors.bg,
    gap: 8,
  },
  voiceBtn: {
    width:           42,
    height:          42,
    borderRadius:    21,
    backgroundColor: Colors.bgInput,
    borderWidth:     1,
    borderColor:     Colors.border,
    alignItems:      'center',
    justifyContent:  'center',
  },
  voiceBtnActive: {
    backgroundColor: '#3a1e1e',
    borderColor:     '#5a2e2e',
  },
  input: {
    flex:            1,
    backgroundColor: Colors.bgInput,
    color:           Colors.text,
    borderWidth:     1,
    borderColor:     Colors.border,
    borderRadius:    20,
    paddingHorizontal: 14,
    paddingVertical:   10,
    fontSize:        15,
    maxHeight:       120,
  },
  sendBtn: {
    width:           42,
    height:          42,
    borderRadius:    21,
    backgroundColor: Colors.accent,
    alignItems:      'center',
    justifyContent:  'center',
  },
  sendBtnDisabled: {
    opacity: 0.35,
  },
})

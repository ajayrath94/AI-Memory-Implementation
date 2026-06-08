import React from 'react'
import { View, Text, StyleSheet } from 'react-native'
import { Colors } from '../../constants'

interface Message {
  id:         string
  role:       'user' | 'assistant'
  content:    string
  model:      string
  timestamp:  number
  pillar?:    { core: string; emotion: string; functional: string; core_score?: number }
  memoryUsed?: boolean
}

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'

  return (
    <View style={[styles.wrapper, isUser ? styles.wrapperUser : styles.wrapperBot]}>
      <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleBot]}>
        <Text style={styles.text}>{message.content}</Text>

        {/* Pillar tags on assistant messages */}
        {!isUser && message.pillar && (
          <View style={styles.metaRow}>
            <PillTag label={message.pillar.core} />
            <PillTag label={message.pillar.emotion} />
            {message.memoryUsed && <PillTag label="🧠 memory" highlight />}
          </View>
        )}

        {/* Model + time */}
        <Text style={styles.meta}>
          {!isUser ? message.model?.split('-')[0] + ' · ' : ''}
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </Text>
      </View>
    </View>
  )
}

function PillTag({ label, highlight }: { label: string; highlight?: boolean }) {
  return (
    <View style={[styles.pill, highlight && styles.pillHighlight]}>
      <Text style={styles.pillText}>{label}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  wrapper:      { marginVertical: 4, paddingHorizontal: 16 },
  wrapperUser:  { alignItems: 'flex-end' },
  wrapperBot:   { alignItems: 'flex-start' },
  bubble: {
    maxWidth: '85%', borderRadius: 18,
    paddingHorizontal: 14, paddingVertical: 10,
  },
  bubbleUser: {
    backgroundColor: Colors.bgUserBubble,
    borderBottomRightRadius: 4,
    borderWidth: 1, borderColor: Colors.borderBlue,
  },
  bubbleBot: {
    backgroundColor: Colors.bgCard,
    borderBottomLeftRadius: 4,
    borderWidth: 1, borderColor: Colors.border,
  },
  text:       { color: Colors.text, fontSize: 15, lineHeight: 22 },
  metaRow:    { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 6 },
  pill: {
    backgroundColor: '#1a2a3a', borderRadius: 8,
    paddingHorizontal: 6, paddingVertical: 2,
  },
  pillHighlight:  { backgroundColor: '#1a3a2a' },
  pillText:       { color: Colors.textMuted, fontSize: 10, fontWeight: '500' },
  meta:           { color: Colors.textHint, fontSize: 10, marginTop: 4 },
})

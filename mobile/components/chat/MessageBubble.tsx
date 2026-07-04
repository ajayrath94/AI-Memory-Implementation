import React from 'react'
import { View, Text, StyleSheet } from 'react-native'
import { Colors, Typography, Spacing, Radius } from '../../constants'

interface Message {
  id:         string
  role:       'user' | 'assistant'
  content:    string
  model?:     string
  timestamp:  number
  pillar?:    { core: string; emotion: string; functional: string }
  memoryUsed?: boolean
}

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'
  const time   = new Date(message.timestamp).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit'
  })

  return (
    <View style={[styles.wrapper, isUser ? styles.wrapperUser : styles.wrapperBot]}>

      {/* Nancy avatar dot for assistant messages */}
      {!isUser && (
        <View style={styles.nancyDot} />
      )}

      <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleBot]}>
        <Text style={[styles.text, isUser ? styles.textUser : styles.textBot]}>
          {message.content}
        </Text>

        <View style={styles.footer}>
          {/* Memory indicator — subtle, not cluttered */}
          {!isUser && message.memoryUsed && (
            <View style={styles.memoryTag}>
              <Text style={styles.memoryText}>🧠</Text>
            </View>
          )}
          <Text style={styles.time}>{time}</Text>
        </View>
      </View>

    </View>
  )
}

const styles = StyleSheet.create({
  wrapper: {
    marginVertical:    3,
    paddingHorizontal: Spacing.lg,
    flexDirection:     'row',
    alignItems:        'flex-end',
    gap:               Spacing.sm,
  },
  wrapperUser: { justifyContent: 'flex-end' },
  wrapperBot:  { justifyContent: 'flex-start' },

  // Nancy's subtle presence indicator
  nancyDot: {
    width:         8,
    height:        8,
    borderRadius:  4,
    backgroundColor: Colors.accent + '60',
    marginBottom:  16,
    flexShrink:    0,
  },

  bubble: {
    maxWidth:          '82%',
    borderRadius:      Radius.xl,
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.md,
  },

  bubbleUser: {
    backgroundColor:    Colors.bgUserBubble,
    borderBottomRightRadius: Radius.sm,
    borderWidth:        0.5,
    borderColor:        Colors.borderBlue,
  },

  bubbleBot: {
    backgroundColor:   Colors.bgCard,
    borderBottomLeftRadius: Radius.sm,
    borderWidth:        0.5,
    borderColor:        Colors.border,
  },

  text: {
    ...Typography.body,
    lineHeight: 24,
  },
  textUser: { color: Colors.text },
  textBot:  { color: Colors.text },

  footer: {
    flexDirection:  'row',
    alignItems:     'center',
    justifyContent: 'flex-end',
    marginTop:      Spacing.xs,
    gap:            Spacing.xs,
  },

  memoryTag: {
    backgroundColor: Colors.accentPurple + '15',
    borderRadius:    Radius.sm,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  memoryText: { fontSize: 10 },
  time:       { ...Typography.caption, color: Colors.textHint },
})

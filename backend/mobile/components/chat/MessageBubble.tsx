import React from 'react'
import { View, Text, StyleSheet } from 'react-native'
import { Colors } from '../../constants'
import { Message } from '../../services/api'

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'

  return (
    <View style={[styles.wrapper, isUser ? styles.wrapperUser : styles.wrapperBot]}>
      <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleBot]}>
        <Text style={styles.text}>{message.content}</Text>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  wrapper: {
    marginVertical: 4,
    paddingHorizontal: 16,
  },
  wrapperUser: { alignItems: 'flex-end' },
  wrapperBot:  { alignItems: 'flex-start' },
  bubble: {
    maxWidth: '82%',
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  bubbleUser: {
    backgroundColor: Colors.bgUserBubble,
    borderBottomRightRadius: 4,
    borderWidth: 1,
    borderColor: Colors.borderBlue,
  },
  bubbleBot: {
    backgroundColor: Colors.bgCard,
    borderBottomLeftRadius: 4,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  text: {
    color:      Colors.text,
    fontSize:   15,
    lineHeight: 22,
  },
})

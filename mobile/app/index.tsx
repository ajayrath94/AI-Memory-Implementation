import React, { useRef, useEffect } from 'react'
import {
  View, FlatList, Text, StyleSheet, SafeAreaView, TouchableOpacity
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { Ionicons } from '@expo/vector-icons'
import { Colors } from '../constants'
import { useAppStore } from '../store/appStore'
import { useChat } from '../hooks/useChat'
import { MessageBubble } from '../components/chat/MessageBubble'
import { ChatInput } from '../components/chat/ChatInput'
import { ModelPicker } from '../components/chat/ModelPicker'

export default function ChatScreen() {
  const { messages, loading, lastMeta, memoryUsed, sessionId, clearChat } = useAppStore()
  const { send } = useChat()
  const listRef = useRef<FlatList>(null)

  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100)
    }
  }, [messages])

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />

      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>AI Memory</Text>
          {sessionId && (
            <Text style={styles.sessionId}>
              Session: {sessionId.slice(0, 8)}...
            </Text>
          )}
        </View>
        <View style={styles.headerRight}>
          <ModelPicker />
          <TouchableOpacity onPress={clearChat} style={styles.clearBtn}>
            <Ionicons name="trash-outline" size={18} color={Colors.textMuted} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Pillar context bar */}
      {lastMeta && (
        <View style={styles.contextBar}>
          <Text style={styles.contextText}>
            {lastMeta.core} · {lastMeta.emotion} · {lastMeta.functional}
            {memoryUsed ? ' · 🧠 memory active' : ''}
          </Text>
        </View>
      )}

      {/* Messages */}
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(m, i) => m.id || String(i)}
        renderItem={({ item }) => <MessageBubble message={item} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyIcon}>🧠</Text>
            <Text style={styles.emptyText}>Start a conversation</Text>
            <Text style={styles.emptyHint}>Memory builds as you chat</Text>
          </View>
        }
      />

      {loading && (
        <View style={styles.typing}>
          <Text style={styles.typingText}>thinking…</Text>
        </View>
      )}

      <ChatInput onSubmit={send} loading={loading} />
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe:         { flex: 1, backgroundColor: Colors.bg },
  header: {
    flexDirection: 'row', alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
  },
  headerTitle:  { color: Colors.text, fontSize: 17, fontWeight: '600' },
  sessionId:    { color: Colors.textHint, fontSize: 10, marginTop: 2 },
  headerRight:  { flexDirection: 'row', alignItems: 'center', gap: 10 },
  clearBtn:     { padding: 4 },
  contextBar: {
    paddingHorizontal: 16, paddingVertical: 5,
    backgroundColor: '#111', borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  contextText:  { color: Colors.textMuted, fontSize: 11 },
  list:         { paddingVertical: 12, flexGrow: 1 },
  empty: {
    flex: 1, alignItems: 'center',
    justifyContent: 'center', paddingTop: 120, gap: 8,
  },
  emptyIcon:    { fontSize: 40 },
  emptyText:    { color: Colors.textMuted, fontSize: 16 },
  emptyHint:    { color: Colors.textHint,  fontSize: 13 },
  typing:       { paddingHorizontal: 20, paddingVertical: 6 },
  typingText:   { color: Colors.textMuted, fontSize: 13 },
})

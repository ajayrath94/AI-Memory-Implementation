import React, { useRef, useEffect, useState } from 'react'
import {
  View, FlatList, Text, StyleSheet,
  SafeAreaView, TouchableOpacity, AppState,
  Animated, Image,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { Ionicons } from '@expo/vector-icons'
import { Colors, Typography, Spacing, Radius, API_BASE, API_KEY } from '../constants'
import { useAppStore } from '../store/appStore'
import { useChat } from '../hooks/useChat'
import { MessageBubble } from '../components/chat/MessageBubble'
import { ChatInput } from '../components/chat/ChatInput'

// Nancy's avatar initials placeholder
function NancyAvatar({ size = 36 }: { size?: number }) {
  return (
    <View style={[styles.avatar, { width: size, height: size, borderRadius: size / 2 }]}>
      <Text style={[styles.avatarText, { fontSize: size * 0.4 }]}>N</Text>
    </View>
  )
}

export default function ChatScreen() {
  const { messages, loading, sessionId } = useAppStore()
  const { send, clearAndSummarize } = useChat()
  const listRef  = useRef<FlatList>(null)
  const appState = useRef(AppState.currentState)
  const pulseAnim = useRef(new Animated.Value(1)).current

  // Pulse animation when Nancy is thinking
  useEffect(() => {
    if (loading) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 0.4, duration: 600, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1.0, duration: 600, useNativeDriver: true }),
        ])
      ).start()
    } else {
      pulseAnim.stopAnimation()
      pulseAnim.setValue(1)
    }
  }, [loading])

  // Auto-scroll
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100)
    }
  }, [messages])

  // End session when app goes to background
  useEffect(() => {
    const sub = AppState.addEventListener('change', next => {
      if (appState.current.match(/active/) && next.match(/inactive|background/)) {
        if (sessionId) {
          fetch(`${API_BASE}/chat/end-session`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
            body:    JSON.stringify({ session_id: sessionId, user_id: 'default' }),
          }).catch(() => {})
        }
      }
      appState.current = next
    })
    return () => sub.remove()
  }, [sessionId])

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />

      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <NancyAvatar size={38} />
          <View style={styles.headerInfo}>
            <Text style={styles.headerName}>Nancy</Text>
            <View style={styles.onlineRow}>
              <View style={styles.onlineDot} />
              <Text style={styles.onlineText}>Your companion</Text>
            </View>
          </View>
        </View>
        <View style={styles.headerActions}>
          <TouchableOpacity onPress={clearAndSummarize} style={styles.headerBtn}>
            <Ionicons name="create-outline" size={22} color={Colors.textMuted} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Messages */}
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(m, i) => m.id || String(i)}
        renderItem={({ item }) => <MessageBubble message={item} />}
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          <View style={styles.empty}>
            <NancyAvatar size={72} />
            <Text style={styles.emptyTitle}>Hi, I'm Nancy</Text>
            <Text style={styles.emptySubtitle}>
              I'm here to listen, remember, and care.{'\n'}
              Tell me how you're feeling today.
            </Text>
          </View>
        }
      />

      {/* Typing indicator */}
      {loading && (
        <View style={styles.typingRow}>
          <NancyAvatar size={24} />
          <View style={styles.typingBubble}>
            <Animated.View style={[styles.typingDot, { opacity: pulseAnim }]} />
            <Animated.View style={[styles.typingDot, { opacity: pulseAnim, marginHorizontal: 3 }]} />
            <Animated.View style={[styles.typingDot, { opacity: pulseAnim }]} />
          </View>
        </View>
      )}

      <ChatInput onSubmit={send} loading={loading} />
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },

  // Header
  header: {
    flexDirection:     'row',
    alignItems:        'center',
    justifyContent:    'space-between',
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.md,
    borderBottomWidth: 0.5,
    borderBottomColor: Colors.border,
    backgroundColor:   Colors.bg,
  },
  headerLeft:    { flexDirection: 'row', alignItems: 'center', gap: Spacing.md },
  headerInfo:    { gap: 2 },
  headerName:    { ...Typography.heading, color: Colors.text },
  onlineRow:     { flexDirection: 'row', alignItems: 'center', gap: 5 },
  onlineDot:     { width: 7, height: 7, borderRadius: 4, backgroundColor: Colors.accentGreen },
  onlineText:    { ...Typography.caption, color: Colors.textMuted },
  headerActions: { flexDirection: 'row', gap: Spacing.sm },
  headerBtn:     { padding: Spacing.sm },

  // Avatar
  avatar: {
    backgroundColor: Colors.accent + '22',
    borderWidth:     1.5,
    borderColor:     Colors.accent + '44',
    alignItems:      'center',
    justifyContent:  'center',
  },
  avatarText: { color: Colors.accent, fontWeight: '700' },

  // Messages
  list: { paddingVertical: Spacing.md, flexGrow: 1 },

  // Empty state
  empty: {
    flex:           1,
    alignItems:     'center',
    justifyContent: 'center',
    paddingTop:     100,
    paddingHorizontal: Spacing.xl,
    gap:            Spacing.lg,
  },
  emptyTitle:    { ...Typography.title, color: Colors.text, marginTop: Spacing.md },
  emptySubtitle: {
    ...Typography.body,
    color:     Colors.textMuted,
    textAlign: 'center',
    lineHeight: 24,
  },

  // Typing indicator
  typingRow: {
    flexDirection:  'row',
    alignItems:     'center',
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.sm,
    gap: Spacing.sm,
  },
  typingBubble: {
    flexDirection:     'row',
    alignItems:        'center',
    backgroundColor:   Colors.bgCard,
    borderRadius:      Radius.lg,
    borderBottomLeftRadius: 4,
    paddingHorizontal: Spacing.md,
    paddingVertical:   Spacing.md,
    borderWidth:       0.5,
    borderColor:       Colors.border,
  },
  typingDot: {
    width:           7,
    height:          7,
    borderRadius:    4,
    backgroundColor: Colors.textMuted,
  },
})

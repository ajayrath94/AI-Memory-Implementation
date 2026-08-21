import React, { useRef, useEffect, useState } from 'react'
import {
  View, FlatList, Text, StyleSheet,
  SafeAreaView, TouchableOpacity, AppState,
  Animated,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { Ionicons } from '@expo/vector-icons'
import { useTheme } from '../hooks/useTheme'
import { Colors, Typography, Spacing, Radius, API_BASE, API_KEY, DEFAULT_MODEL } from '../constants'
import AsyncStorage from '@react-native-async-storage/async-storage'
import { useAppStore } from '../store/appStore'
import { syncLocation } from '../services/locationService'
import { useChat } from '../hooks/useChat'
import { MessageBubble } from '../components/chat/MessageBubble'
import { ChatInput } from '../components/chat/ChatInput'

function NancyAvatar({ size = 36 }: { size?: number }) {
  return (
    <View style={[styles.avatar, { width: size, height: size, borderRadius: size / 2 }]}>
      <Text style={[styles.avatarText, { fontSize: size * 0.4 }]}>N</Text>
    </View>
  )
}

export default function ChatScreen() {
  const theme = useTheme()
  const { messages, loading, sessionId, endSession, clearChat, userId } = useAppStore()
  const { send, resend } = useChat()
  const listRef   = useRef<FlatList>(null)
  const appState  = useRef(AppState.currentState)
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

  // Auto-scroll to bottom
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100)
    }
  }, [messages])

  // End session when app goes to background
  useEffect(() => {
    const sub = AppState.addEventListener('change', next => {
      if (appState.current.match(/active/) && next.match(/inactive|background/)) {
        useAppStore.getState().setLastSeenAt(Date.now())
        AsyncStorage.setItem('lastSeenAt', String(Date.now())).catch(() => {})
        endSession()
      }
      if (appState.current.match(/inactive|background/) && next === 'active') {
        syncLocation(userId)
      }
      appState.current = next
    })
    return () => sub.remove()
  }, [sessionId])

  // ── Nancy opens the conversation ──────────────────────────────────────────
  // The backend has had should_nancy_open() since the beginning and nothing
  // called it, so a proactive push woke the user and dropped them into an
  // empty screen. The gate stays server-side: she speaks only after 4+ hours
  // away or when priority is high, otherwise the reply is empty.
  useEffect(() => {
    console.log('[proactive-open] mount — messages:', messages.length, 'session:', sessionId)
    if (messages.length > 0 || sessionId) return
    let cancelled = false

    const openConversation = async () => {
      try {
        // Read from disk, not the store: the store is in-memory only, so after a
        // cold start lastSeenAt is null and every launch looks like a 24-hour
        // absence — she would greet you five times in an afternoon.
        const stored = await AsyncStorage.getItem('lastSeenAt')
        const lastSeen = stored ? Number(stored) : null
        const hoursAway = lastSeen ? (Date.now() - lastSeen) / 3600000 : 24

        const res = await fetch(`${API_BASE}/chat/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
          body: JSON.stringify({
            text: '', user_id: userId, model: DEFAULT_MODEL,
            context: {
              hour: new Date().getHours(),
              last_seen_hours: hoursAway,
              opened_app: true,
            },
          }),
        })
        const data = await res.json()
        console.log('[proactive-open] reply:', JSON.stringify(data).slice(0, 200))
        if (cancelled || !data?.reply) return

        if (data.session_id) useAppStore.getState().setSessionId(data.session_id)
        useAppStore.getState().addMessage({
          id: data.message_id || String(Date.now()),
          role: 'assistant',
          content: data.reply,
          model: data.model || DEFAULT_MODEL,
          timestamp: Date.now(),
        })
      } catch (e) {
        console.log('[proactive-open]', e)
      }
    }

    openConversation()
    return () => { cancelled = true }
  }, [])

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: Colors.bg }]}>
      <StatusBar style="light" />

      {/* Header */}
      <View style={[styles.header, { backgroundColor: Colors.bg, borderBottomColor: theme.border }]}>
        <View style={styles.headerLeft}>
          <NancyAvatar size={38} />
          <View style={styles.headerInfo}>
            <Text style={[styles.headerName, { color: theme.text }]}>Nancy</Text>
            <View style={styles.onlineRow}>
              <View style={styles.onlineDot} />
              <Text style={[styles.onlineText, { color: theme.textMuted }]}>Your companion</Text>
            </View>
          </View>
        </View>
        <TouchableOpacity onPress={clearChat} style={styles.headerBtn}>
          <Ionicons name="create-outline" size={22} color={theme.textMuted} />
        </TouchableOpacity>
      </View>

      {/* Messages */}
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(m, i) => m.id || String(i)}
        renderItem={({ item }) => <MessageBubble message={item} onResend={resend} />}
        contentContainerStyle={[styles.list, { backgroundColor: Colors.bg }]}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          <View style={[styles.empty, { backgroundColor: Colors.bg }]}>
            <NancyAvatar size={72} />
            <Text style={[styles.emptyTitle, { color: theme.text }]}>Hi, I'm Nancy</Text>
            <Text style={[styles.emptySubtitle, { color: theme.textMuted }]}>
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
          <View style={[styles.typingBubble, { backgroundColor: Colors.bgCard, borderColor: theme.border }]}>
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
  header: {
    flexDirection:     'row',
    alignItems:        'center',
    justifyContent:    'space-between',
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.md,
    borderBottomWidth: 0.5,
    borderBottomColor: Colors.border,
  },
  headerLeft:    { flexDirection: 'row', alignItems: 'center', gap: Spacing.md },
  headerInfo:    { gap: 2 },
  headerName:    { ...Typography.heading, color: Colors.text },
  onlineRow:     { flexDirection: 'row', alignItems: 'center', gap: 5 },
  onlineDot:     { width: 7, height: 7, borderRadius: 4, backgroundColor: Colors.accentGreen },
  onlineText:    { ...Typography.caption, color: Colors.textMuted },
  headerBtn:     { padding: Spacing.sm },
  avatar: {
    backgroundColor: Colors.accent + '22',
    borderWidth:     1.5,
    borderColor:     Colors.accent + '44',
    alignItems:      'center',
    justifyContent:  'center',
  },
  avatarText: { color: Colors.accent, fontWeight: '700' },
  list:       { paddingVertical: Spacing.md, flexGrow: 1 },
  empty: {
    flex:              1,
    alignItems:        'center',
    justifyContent:    'center',
    paddingTop:        100,
    paddingHorizontal: Spacing.xl,
    gap:               Spacing.lg,
  },
  emptyTitle:    { ...Typography.title, color: Colors.text, marginTop: Spacing.md },
  emptySubtitle: { ...Typography.body, color: Colors.textMuted, textAlign: 'center', lineHeight: 24 },
  typingRow: {
    flexDirection:     'row',
    alignItems:        'center',
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.sm,
    gap:               Spacing.sm,
  },
  typingBubble: {
    flexDirection:          'row',
    alignItems:             'center',
    backgroundColor:        Colors.bgCard,
    borderRadius:           Radius.lg,
    borderBottomLeftRadius: 4,
    paddingHorizontal:      Spacing.md,
    paddingVertical:        Spacing.md,
    borderWidth:            0.5,
    borderColor:            Colors.border,
  },
  typingDot: {
    width:           7,
    height:          7,
    borderRadius:    4,
    backgroundColor: Colors.textMuted,
  },
})

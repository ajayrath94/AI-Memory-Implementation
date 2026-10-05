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
import { useT } from '../hooks/useT'
import { MessageBubble } from '../components/chat/MessageBubble'
import { speak, stop as stopVoice, getPreference, onPlayingChange, type Playback } from '../services/voiceService'
import { ChatInput } from '../components/chat/ChatInput'

// Takes the companion's name rather than assuming it. Someone whose companion
// is Shubham was seeing "Nancy" in the header and an N in the avatar, which
// undoes the whole point of letting them name it.
function CompanionAvatar({ size = 36, name = 'N' }: { size?: number; name?: string }) {
  return (
    <View style={[styles.avatar, { width: size, height: size, borderRadius: size / 2 }]}>
      <Text style={[styles.avatarText, { fontSize: size * 0.4 }]}>{name?.[0]?.toUpperCase() || 'N'}</Text>
    </View>
  )
}

// Guards the proactive open against a double mount. See the effect below.
let openingConversation = false

export default function ChatScreen() {
  const theme = useTheme()
  const { messages, loading, sessionId, endSession, clearChat, userId } = useAppStore()
  const { send, resend } = useChat()
  const t = useT()

  // The companion's own name, not the product's.
  const [botName, setBotName] = useState('Nancy')
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/persona/${userId}`, {
          headers: { 'X-API-Key': API_KEY },
        })
        const d = await res.json()
        if (d?.bot_name) setBotName(d.bot_name)
      } catch {}
    })()
  }, [userId])
  const listRef   = useRef<FlatList>(null)

  // Which message is speaking, so its icon can show it.
  const [speakingId, setSpeakingId] = useState<string | null>(null)
  const [playback, setPlayback] = useState<Playback>('tap')
  // The last message spoken on its own — so opening the app does not read
  // the whole history aloud.
  const spokenRef = useRef<string | null>(null)

  useEffect(() => onPlayingChange(setSpeakingId), [])

  useEffect(() => {
    getPreference(userId).then((p) => setPlayback(p.playback)).catch(() => {})
  }, [userId])

  // Speak a new arrival, when she has asked for that. Only the newest, and
  // only once: auto-play is for the message that just came in, not for the
  // conversation she is scrolling back through.
  useEffect(() => {
    if (playback !== 'auto' || !messages.length) return
    const last = messages[messages.length - 1]
    if (!last || last.role !== 'assistant') return
    if (spokenRef.current === last.id) return
    spokenRef.current = last.id
    speak(last.content, { id: last.id, userId })
  }, [messages, playback, userId])

  // A voice still talking about the last thing while she writes the next is
  // the worst of it.
  useEffect(() => () => { stopVoice() }, [])
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
    // Set BEFORE any await. Two mounts raced, both saw session=null because
    // neither had finished, and she got two greetings in two different
    // sessions — one in Devanagari and one in Latin Hinglish, so they did not
    // even match each other.
    //
    // Module scope rather than a ref: a ref is per instance, and two mounts
    // may be two instances.
    if (openingConversation) return
    openingConversation = true
    let cancelled = false

    const openConversation = async () => {
      try {
        // Resume before greeting. The screen started empty on every launch, so
        // a proactive message read on the lock screen led to a blank chat when
        // the notification was tapped — the thing she had just responded to was
        // gone. More generally, a companion that forgets the conversation each
        // time the app closes is a strange thing to be talking to.
        try {
          const res = await fetch(`${API_BASE}/memory/conversation/${userId}`, {
            headers: { 'X-API-Key': API_KEY },
          })
          const conv = await res.json()
          console.log('[proactive-open] resume:', userId, res.status,
                      conv?.messages?.length ?? 'none')
          if (!cancelled && conv?.messages?.length) {
            useAppStore.getState().setSessionId(conv.session_id)
            for (const m of conv.messages) {
              useAppStore.getState().addMessage({
                id:        m.id || String(Math.random()),
                role:      m.role,
                content:   m.content,
                model:     m.model || DEFAULT_MODEL,
                timestamp: m.timestamp ? Date.parse(m.timestamp) : Date.now(),
              })
            }
            return                    // there is a conversation; do not open a new one
          }
        } catch (e) {
          // Not being able to resume is not a reason to say nothing.
          console.log('[proactive-open] resume failed', e)
        }

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
          <CompanionAvatar size={38} name={botName} />
          <View style={styles.headerInfo}>
            <Text style={[styles.headerName, { color: theme.text }]}>{botName}</Text>
            <View style={styles.onlineRow}>
              <View style={styles.onlineDot} />
              <Text style={[styles.onlineText, { color: theme.textMuted }]}>{t('chat.online')}</Text>
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
        renderItem={({ item }) => (
          <MessageBubble
            message={item}
            onResend={resend}
            speaking={speakingId === item.id}
            onSpeak={() => {
              if (speakingId === item.id) { stopVoice(); return }
              speak(item.content, { id: item.id, userId })
            }}
          />
        )}
        contentContainerStyle={[styles.list, { backgroundColor: Colors.bg }]}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          <View style={[styles.empty, { backgroundColor: Colors.bg }]}>
            <CompanionAvatar size={72} name={botName} />
            <Text style={[styles.emptyTitle, { color: theme.text }]}>{t('chat.empty.title')}</Text>
            <Text style={[styles.emptySubtitle, { color: theme.textMuted }]}>
              {t('chat.empty.sub')}
            </Text>
          </View>
        }
      />

      {/* Typing indicator */}
      {loading && (
        <View style={styles.typingRow}>
          <CompanionAvatar size={24} name={botName} />
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

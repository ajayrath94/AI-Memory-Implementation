import React, { useEffect, useState } from 'react'
import {
  View, Text, FlatList, StyleSheet,
  SafeAreaView, TouchableOpacity, ActivityIndicator, RefreshControl
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { Ionicons } from '@expo/vector-icons'
import { Colors, API_BASE } from '../constants'
import { useAppStore } from '../store/appStore'
import { useRouter } from 'expo-router'

interface Session {
  id:         string
  title:      string | null
  model:      string
  summary:    string | null
  created_at: string
  updated_at: string
  weight:     number
}

const PILLAR_COLORS: Record<string, string> = {
  FINANCE:         '#1a3a2a',
  HEALTH_WELLNESS: '#1a3a1a',
  CAREER_GOAL:     '#1a2a3a',
  ASPIRATIONS:     '#2a1a3a',
  ENTERTAINMENT:   '#3a2a1a',
  GENERAL:         '#2a2a2a',
}

export default function SessionsScreen() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading,  setLoading]  = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const { setSessionId } = useAppStore()
  const router = useRouter()

  const fetchSessions = async () => {
    try {
      const res  = await fetch(`${API_BASE}/memory/sessions/list`)
      const data = await res.json()
      setSessions(data.sessions || [])
    } catch (err) {
      console.error('Failed to fetch sessions:', err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { fetchSessions() }, [])

  const onRefresh = () => {
    setRefreshing(true)
    fetchSessions()
  }

  const openSession = (session: Session) => {
    setSessionId(session.id)
    router.push('/')
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    const now  = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / 86400000)

    if (days === 0) return 'Today'
    if (days === 1) return 'Yesterday'
    if (days < 7)  return `${days} days ago`
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  const getModelShort = (model: string) => {
    if (model.includes('sonnet')) return 'Sonnet'
    if (model.includes('haiku'))  return 'Haiku'
    if (model.includes('opus'))   return 'Opus'
    if (model.includes('gpt'))    return 'GPT'
    if (model.includes('gemini')) return 'Gemini'
    if (model.includes('grok'))   return 'Grok'
    return model.split('-')[0]
  }

  const getPillarFromTitle = (title: string | null) => {
    if (!title) return 'GENERAL'
    return title.split(' · ')[0] || 'GENERAL'
  }

  const renderSession = ({ item }: { item: Session }) => {
    const pillar    = getPillarFromTitle(item.title)
    const titleText = item.title
      ? item.title.split(' · ').slice(1).join(' ')
      : 'Untitled conversation'

    return (
      <TouchableOpacity
        style={styles.card}
        onPress={() => openSession(item)}
        activeOpacity={0.7}
      >
        {/* Header row */}
        <View style={styles.cardHeader}>
          <View style={[styles.pillarBadge,
            { backgroundColor: PILLAR_COLORS[pillar] || PILLAR_COLORS.GENERAL }]}>
            <Text style={styles.pillarText}>{pillar}</Text>
          </View>
          <View style={styles.cardMeta}>
            <Text style={styles.modelText}>{getModelShort(item.model)}</Text>
            <Text style={styles.dateText}>{formatDate(item.updated_at)}</Text>
          </View>
        </View>

        {/* Title */}
        <Text style={styles.cardTitle} numberOfLines={1}>
          {titleText}
        </Text>

        {/* Summary */}
        {item.summary ? (
          <Text style={styles.cardSummary} numberOfLines={3}>
            {item.summary}
          </Text>
        ) : (
          <Text style={styles.cardNoSummary}>
            No summary yet
          </Text>
        )}

        {/* Footer */}
        <View style={styles.cardFooter}>
          <Ionicons name="arrow-forward" size={14} color={Colors.textHint} />
        </View>
      </TouchableOpacity>
    )
  }

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}>
          <ActivityIndicator color={Colors.accent} size="large" />
          <Text style={styles.loadingText}>Loading sessions...</Text>
        </View>
      </SafeAreaView>
    )
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />

      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Sessions</Text>
        <TouchableOpacity onPress={onRefresh}>
          <Ionicons name="refresh-outline" size={20} color={Colors.textMuted} />
        </TouchableOpacity>
      </View>

      {/* Sessions list */}
      <FlatList
        data={sessions}
        keyExtractor={s => s.id}
        renderItem={renderSession}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={Colors.accent}
          />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="time-outline" size={48} color={Colors.textHint} />
            <Text style={styles.emptyText}>No sessions yet</Text>
            <Text style={styles.emptyHint}>Start a conversation to see it here</Text>
          </View>
        }
      />
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe:         { flex: 1, backgroundColor: Colors.bg },
  header: {
    flexDirection:    'row',
    alignItems:       'center',
    justifyContent:   'space-between',
    paddingHorizontal: 16,
    paddingVertical:   14,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  headerTitle:  { color: Colors.text, fontSize: 17, fontWeight: '600' },
  list:         { padding: 16, gap: 12 },
  card: {
    backgroundColor: Colors.bgCard,
    borderRadius:    12,
    padding:         14,
    borderWidth:     1,
    borderColor:     Colors.border,
    gap:             8,
  },
  cardHeader: {
    flexDirection:  'row',
    alignItems:     'center',
    justifyContent: 'space-between',
  },
  pillarBadge: {
    borderRadius:      8,
    paddingHorizontal: 8,
    paddingVertical:   3,
  },
  pillarText:   { color: Colors.textMuted, fontSize: 10, fontWeight: '600' },
  cardMeta: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           8,
  },
  modelText:    { color: Colors.textMuted, fontSize: 11 },
  dateText:     { color: Colors.textHint,  fontSize: 11 },
  cardTitle: {
    color:      Colors.text,
    fontSize:   15,
    fontWeight: '600',
  },
  cardSummary: {
    color:      Colors.textMuted,
    fontSize:   13,
    lineHeight: 18,
  },
  cardNoSummary: {
    color:      Colors.textHint,
    fontSize:   12,
    fontStyle:  'italic',
  },
  cardFooter: {
    alignItems: 'flex-end',
    marginTop:  4,
  },
  center: {
    flex:           1,
    alignItems:     'center',
    justifyContent: 'center',
    gap:            12,
  },
  loadingText:  { color: Colors.textMuted, fontSize: 14 },
  empty: {
    alignItems:     'center',
    justifyContent: 'center',
    paddingTop:     100,
    gap:            10,
  },
  emptyText:    { color: Colors.textMuted, fontSize: 16 },
  emptyHint:    { color: Colors.textHint,  fontSize: 13 },
})

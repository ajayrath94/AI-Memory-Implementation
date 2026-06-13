import React, { useEffect, useState } from 'react'
import {
  View, Text, ScrollView, StyleSheet,
  SafeAreaView, TouchableOpacity, ActivityIndicator, RefreshControl
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { Ionicons } from '@expo/vector-icons'
import { Colors, API_BASE } from '../constants'

interface UserMemory {
  user_id:          string
  summary:          string | null
  key_facts:        string[]
  dominant_pillars: string[]
  session_count:    number
  updated_at:       string
}

export default function MemoryScreen() {
  const [memory,     setMemory]     = useState<UserMemory | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchMemory = async () => {
    try {
      const res  = await fetch(`${API_BASE}/memory/user/default`)
      const data = await res.json()
      setMemory(data)
    } catch (err) {
      console.error('Failed to fetch memory:', err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { fetchMemory() }, [])

  const onRefresh = () => {
    setRefreshing(true)
    fetchMemory()
  }

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}>
          <ActivityIndicator color={Colors.accent} size="large" />
          <Text style={styles.loadingText}>Loading memory...</Text>
        </View>
      </SafeAreaView>
    )
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />

      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>🧠 Memory Profile</Text>
        <TouchableOpacity onPress={onRefresh}>
          <Ionicons name="refresh-outline" size={20} color={Colors.textMuted} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh}
            tintColor={Colors.accent} />
        }
      >
        {!memory?.summary ? (
          <View style={styles.empty}>
            <Text style={styles.emptyIcon}>🧠</Text>
            <Text style={styles.emptyText}>No memory yet</Text>
            <Text style={styles.emptyHint}>
              Have a few conversations and end your session — the AI will build a memory profile
            </Text>
          </View>
        ) : (
          <>
            {/* Stats row */}
            <View style={styles.statsRow}>
              <StatCard
                icon="chatbubbles-outline"
                value={String(memory.session_count)}
                label="Sessions"
              />
              <StatCard
                icon="bulb-outline"
                value={String(memory.key_facts?.length || 0)}
                label="Key facts"
              />
              <StatCard
                icon="analytics-outline"
                value={String(memory.dominant_pillars?.length || 0)}
                label="Pillars"
              />
            </View>

            {/* What AI knows */}
            <Section title="What I know about you">
              <Text style={styles.summaryText}>{memory.summary}</Text>
            </Section>

            {/* Key facts */}
            {memory.key_facts && memory.key_facts.length > 0 && (
              <Section title="Key facts">
                {memory.key_facts.map((fact, i) => (
                  <View key={i} style={styles.factRow}>
                    <View style={styles.factDot} />
                    <Text style={styles.factText}>{fact}</Text>
                  </View>
                ))}
              </Section>
            )}

            {/* Dominant pillars */}
            {memory.dominant_pillars && memory.dominant_pillars.length > 0 && (
              <Section title="Your main topics">
                <View style={styles.pillarsRow}>
                  {memory.dominant_pillars.map((pillar, i) => (
                    <View key={i} style={styles.pillarChip}>
                      <Text style={styles.pillarChipText}>{pillar}</Text>
                    </View>
                  ))}
                </View>
              </Section>
            )}

            {/* Last updated */}
            {memory.updated_at && (
              <Text style={styles.updatedAt}>
                Last updated: {new Date(memory.updated_at).toLocaleString()}
              </Text>
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <View style={styles.sectionContent}>
        {children}
      </View>
    </View>
  )
}

function StatCard({ icon, value, label }: { icon: any; value: string; label: string }) {
  return (
    <View style={styles.statCard}>
      <Ionicons name={icon} size={20} color={Colors.accent} />
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: Colors.bg },
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
  scroll:       { padding: 16, gap: 16 },
  statsRow: {
    flexDirection:  'row',
    gap:            10,
    marginBottom:   8,
  },
  statCard: {
    flex:            1,
    backgroundColor: Colors.bgCard,
    borderRadius:    12,
    padding:         14,
    alignItems:      'center',
    gap:             4,
    borderWidth:     1,
    borderColor:     Colors.border,
  },
  statValue:    { color: Colors.text,    fontSize: 22, fontWeight: '700' },
  statLabel:    { color: Colors.textMuted, fontSize: 11 },
  section: {
    backgroundColor: Colors.bgCard,
    borderRadius:    12,
    padding:         14,
    gap:             10,
    borderWidth:     1,
    borderColor:     Colors.border,
  },
  sectionTitle: {
    color:      Colors.textMuted,
    fontSize:   11,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  sectionContent: { gap: 8 },
  summaryText: {
    color:      Colors.text,
    fontSize:   14,
    lineHeight: 22,
  },
  factRow: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           10,
  },
  factDot: {
    width:           6,
    height:          6,
    borderRadius:    3,
    backgroundColor: Colors.accent,
  },
  factText:     { color: Colors.text, fontSize: 14, flex: 1 },
  pillarsRow: {
    flexDirection: 'row',
    flexWrap:      'wrap',
    gap:           8,
  },
  pillarChip: {
    backgroundColor: '#1a2a3a',
    borderRadius:    20,
    paddingHorizontal: 12,
    paddingVertical:   6,
  },
  pillarChipText: { color: Colors.accent, fontSize: 12, fontWeight: '500' },
  updatedAt:    { color: Colors.textHint, fontSize: 11, textAlign: 'center' },
  center: {
    flex:           1,
    alignItems:     'center',
    justifyContent: 'center',
    gap:            12,
  },
  loadingText:  { color: Colors.textMuted, fontSize: 14 },
  empty: {
    alignItems:  'center',
    paddingTop:  80,
    gap:         12,
    paddingHorizontal: 32,
  },
  emptyIcon:    { fontSize: 48 },
  emptyText:    { color: Colors.textMuted, fontSize: 16, fontWeight: '600' },
  emptyHint: {
    color:     Colors.textHint,
    fontSize:  13,
    textAlign: 'center',
    lineHeight: 20,
  },
})

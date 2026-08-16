import React, { useEffect, useState, useCallback } from 'react'
import {
  View, Text, ScrollView, StyleSheet,
  SafeAreaView, TouchableOpacity, ActivityIndicator,
  RefreshControl,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { Ionicons } from '@expo/vector-icons'
import { useTheme } from '../hooks/useTheme'
import { Colors, Typography, Spacing, Radius, API_BASE, API_KEY } from '../constants'
import { useAppStore } from '../store/appStore'

interface CalItem {
  kind:      string          // event | reminder | routine
  id:        string
  title:     string
  at:        string          // ISO timestamp (UTC)
  category?: string
  location?: string | null
  notes?:    string | null
  dose?:     string | null
  status?:   string | null
}
interface CalResponse {
  user_id: string
  from:    string
  to:      string
  items:   CalItem[]
}

// ── category → color + icon ──────────────────────────────────────────────
const CATEGORY: Record<string, { color: string; icon: string }> = {
  medical:   { color: '#4a90d9', icon: 'medkit-outline' },
  social:    { color: '#3dba7a', icon: 'people-outline' },
  festival:  { color: '#e8875a', icon: 'star-outline' },
  routine:   { color: '#7a5ad9', icon: 'time-outline' },
  medication:{ color: '#7a5ad9', icon: 'medical-outline' },
  reminder:  { color: '#e8a23a', icon: 'notifications-outline' },
  personal:  { color: '#888888', icon: 'calendar-outline' },
}
function catStyle(item: CalItem) {
  const key = (item.kind === 'reminder' ? 'reminder'
             : item.kind === 'routine'  ? (item.category || 'routine')
             : item.category || 'personal').toLowerCase()
  return CATEGORY[key] || CATEGORY.personal
}

// ── format a UTC ISO string to IST (manual +5:30 offset — Hermes lacks tz support) ──
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000
function istDate(iso: string): Date {
  const d = new Date(iso.includes('+') || iso.endsWith('Z') ? iso : iso + 'Z')
  return new Date(d.getTime() + IST_OFFSET_MS)  // shifted so UTC getters read as IST
}
const DAYS = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']

function istTime(iso: string): string {
  const d = istDate(iso)
  let h = d.getUTCHours()
  const m = d.getUTCMinutes()
  const ampm = h >= 12 ? 'PM' : 'AM'
  h = h % 12; if (h === 0) h = 12
  return `${h}:${String(m).padStart(2,'0')} ${ampm}`
}
function dayKey(iso: string): string {
  const d = istDate(iso)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth()+1).padStart(2,'0')}-${String(d.getUTCDate()).padStart(2,'0')}`
}
function dayLabel(iso: string): string {
  const d = istDate(iso)
  const now = istDate(new Date().toISOString())
  const todayKey = `${now.getUTCFullYear()}-${String(now.getUTCMonth()+1).padStart(2,'0')}-${String(now.getUTCDate()).padStart(2,'0')}`
  const tmrw = new Date(now.getTime() + 86400000)
  const tmrwKey = `${tmrw.getUTCFullYear()}-${String(tmrw.getUTCMonth()+1).padStart(2,'0')}-${String(tmrw.getUTCDate()).padStart(2,'0')}`
  const k = dayKey(iso)
  const dateStr = `${DAYS[d.getUTCDay()]}, ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`
  if (k === todayKey) return `Aaj · ${dateStr}`
  if (k === tmrwKey)  return `Kal · ${dateStr}`
  return dateStr
}

export default function CalendarScreen() {
  const theme = useTheme()
  const { userId } = useAppStore()
  const [data,       setData]       = useState<CalResponse | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchCalendar = useCallback(async () => {
    try {
      const res  = await fetch(`${API_BASE}/calendar/${userId}?days=14`, {
        headers: { 'X-API-Key': API_KEY },
      })
      const json = await res.json()
      setData(json)
    } catch (err) {
      console.error('Failed to fetch calendar:', err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [userId])

  useEffect(() => {
    fetchCalendar()
    const interval = setInterval(fetchCalendar, 30000)
    return () => clearInterval(interval)
  }, [fetchCalendar])

  const onRefresh = () => { setRefreshing(true); fetchCalendar() }

  // group items by day
  const groups: { label: string; key: string; items: CalItem[] }[] = []
  if (data?.items) {
    const byDay = new Map<string, CalItem[]>()
    for (const it of data.items) {
      const k = dayKey(it.at)
      if (!byDay.has(k)) byDay.set(k, [])
      byDay.get(k)!.push(it)
    }
    const sortedKeys = [...byDay.keys()].sort()
    for (const k of sortedKeys) {
      const items = byDay.get(k)!.sort((a, b) => a.at.localeCompare(b.at))
      groups.push({ key: k, label: dayLabel(items[0].at), items })
    }
  }

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: theme.bg }]}>
      <StatusBar style="light" />

      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={[styles.title, { color: theme.text }]}>Meri Calendar</Text>
          <Text style={[styles.subtitle, { color: theme.textMuted }]}>
            Agle 2 hafte
          </Text>
        </View>
        <View style={[styles.headerIcon, { backgroundColor: Colors.accent + '22' }]}>
          <Ionicons name="calendar" size={24} color={Colors.accent} />
        </View>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={Colors.accent} />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.scroll}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.accent} />
          }
        >
          {groups.length === 0 ? (
            <View style={styles.emptyWrap}>
              <Text style={styles.emptyEmoji}>🌸</Text>
              <Text style={[styles.emptyText, { color: theme.textMuted }]}>
                Abhi koi plan nahi hai.{'\n'}Nancy se baat karke add kar sakti hain.
              </Text>
            </View>
          ) : (
            groups.map((g) => (
              <View key={g.key} style={styles.dayGroup}>
                <Text style={[styles.dayLabel, { color: theme.textSecond }]}>{g.label}</Text>
                {g.items.map((it) => {
                  const cs = catStyle(it)
                  return (
                    <View
                      key={`${it.kind}-${it.id}`}
                      style={[styles.card, { backgroundColor: theme.bgCard, borderColor: theme.border }]}
                    >
                      <View style={[styles.stripe, { backgroundColor: cs.color }]} />
                      <View style={[styles.cardIcon, { backgroundColor: cs.color + '22' }]}>
                        <Ionicons name={cs.icon as any} size={22} color={cs.color} />
                      </View>
                      <View style={styles.cardBody}>
                        <Text style={[styles.cardTitle, { color: theme.text }]}>{it.title}</Text>
                        {it.location ? (
                          <Text style={[styles.cardMeta, { color: theme.textMuted }]}>
                            📍 {it.location}
                          </Text>
                        ) : null}
                        {it.dose ? (
                          <Text style={[styles.cardMeta, { color: theme.textMuted }]}>
                            {it.dose}
                          </Text>
                        ) : null}
                      </View>
                      <Text style={[styles.cardTime, { color: cs.color }]}>{istTime(it.at)}</Text>
                    </View>
                  )
                })}
              </View>
            ))
          )}
          <View style={{ height: 40 }} />
        </ScrollView>
      )}
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe:   { flex: 1 },
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: Spacing.xl, paddingTop: Spacing.lg, paddingBottom: Spacing.md,
  },
  title:    { ...Typography.display },
  subtitle: { ...Typography.label, marginTop: 2 },
  headerIcon: {
    width: 48, height: 48, borderRadius: Radius.full,
    alignItems: 'center', justifyContent: 'center',
  },
  center:   { flex: 1, alignItems: 'center', justifyContent: 'center' },
  scroll:   { paddingHorizontal: Spacing.lg, paddingTop: Spacing.sm },
  dayGroup: { marginBottom: Spacing.xl },
  dayLabel: {
    ...Typography.heading, marginBottom: Spacing.md, marginLeft: Spacing.xs,
    textTransform: 'capitalize',
  },
  card: {
    flexDirection: 'row', alignItems: 'center',
    borderRadius: Radius.lg, borderWidth: 1,
    padding: Spacing.lg, marginBottom: Spacing.md,
    overflow: 'hidden',
  },
  stripe: {
    position: 'absolute', left: 0, top: 0, bottom: 0, width: 5,
  },
  cardIcon: {
    width: 44, height: 44, borderRadius: Radius.md,
    alignItems: 'center', justifyContent: 'center', marginRight: Spacing.md,
    marginLeft: Spacing.xs,
  },
  cardBody:  { flex: 1 },
  cardTitle: { ...Typography.bodyLg, fontWeight: '600' },
  cardMeta:  { ...Typography.label, marginTop: 3 },
  cardTime:  { ...Typography.heading, marginLeft: Spacing.sm },
  emptyWrap: { alignItems: 'center', paddingTop: 80, paddingHorizontal: Spacing.xl },
  emptyEmoji:{ fontSize: 48, marginBottom: Spacing.lg },
  emptyText: { ...Typography.bodyLg, textAlign: 'center', lineHeight: 28 },
})

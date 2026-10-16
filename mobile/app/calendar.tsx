import React, { useEffect, useState, useCallback } from 'react'
import {
  View, Text, ScrollView, StyleSheet,
  SafeAreaView, TouchableOpacity, ActivityIndicator,
  RefreshControl,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { Ionicons } from '@expo/vector-icons'
import { useTheme } from '../hooks/useTheme'
import { useT } from '../hooks/useT'
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
  reminder?: boolean          // an event that will ring (its reminder is pending)
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
  // A bare "06:30" from the schedule is not a timestamp. new Date("06:30Z") is
  // Invalid Date, every getter returns NaN, and the screen read "NaN:NaN AM"
  // under a heading of "Undefined, NaN Undefined" — while the routine screen
  // showed the same times correctly, because it never parsed them.
  let s = String(iso || '').trim()
  if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(s)) {
    const today = new Date().toISOString().slice(0, 10)
    const [h, m] = s.split(':')
    s = `${today}T${h.padStart(2, '0')}:${m}:00`
  }
  const d = new Date(s.includes('+') || s.endsWith('Z') ? s : s + 'Z')
  return new Date(d.getTime() + IST_OFFSET_MS)  // shifted so UTC getters read as IST
}
const DAYS = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']

function istTime(iso: string): string {
  const d = istDate(iso)
  // Anything still unparseable shows a dash rather than NaN.
  if (isNaN(d.getTime())) return '—'
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
  const t = useT()
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

  // Group by day. Her routine (only today's comes from the server) is kept
  // apart from what is planned, so a day reads as its few real things first.
  const groups: { label: string; key: string; planned: CalItem[]; routine: CalItem[] }[] = []
  if (data?.items) {
    const byDay = new Map<string, CalItem[]>()
    for (const it of data.items) {
      if (isNaN(istDate(it.at).getTime())) continue   // unreadable time: never a "NaN" heading
      const k = dayKey(it.at)
      if (!byDay.has(k)) byDay.set(k, [])
      byDay.get(k)!.push(it)
    }
    for (const k of [...byDay.keys()].sort()) {
      const items = byDay.get(k)!.sort((a, b) => a.at.localeCompare(b.at))
      groups.push({
        key: k, label: dayLabel(items[0].at),
        planned: items.filter(i => i.kind !== 'routine'),
        routine: items.filter(i => i.kind === 'routine'),
      })
    }
  }

  const card = (it: CalItem) => {
    const cs = catStyle(it)
    const rings = it.kind === 'reminder' || it.reminder
    return (
      <View
        key={`${it.kind}-${it.id}-${it.at}`}
        style={[styles.card, { backgroundColor: theme.bgCard, borderColor: theme.border }]}
      >
        <View style={[styles.stripe, { backgroundColor: cs.color }]} />
        <View style={styles.timeCol}>
          <Text style={[styles.timeText, { color: cs.color }]}>{istTime(it.at)}</Text>
          <Ionicons name={cs.icon as any} size={18} color={cs.color} style={{ marginTop: 6 }} />
        </View>
        <View style={styles.cardBody}>
          <Text style={[styles.cardTitle, { color: theme.text }]}>{it.title}</Text>
          {it.location ? (
            <Text style={[styles.cardMeta, { color: theme.textMuted }]}>📍 {it.location}</Text>
          ) : null}
          {rings ? (
            <View style={styles.bellRow}>
              <Ionicons name="notifications-outline" size={15} color={CATEGORY.reminder.color} />
              <Text style={[styles.cardMeta, { color: CATEGORY.reminder.color, marginTop: 0, marginLeft: 4 }]}>
                Yaad dilaungi
              </Text>
            </View>
          ) : null}
        </View>
      </View>
    )
  }

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: theme.bg }]}>
      <StatusBar style="light" />

      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={[styles.title, { color: theme.text }]}>{t('calendar.title')}</Text>
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
                {g.planned.map(card)}
                {g.routine.length ? (
                  <View style={[styles.routineBox, { borderColor: theme.border }]}>
                    <Text style={[styles.routineHead, { color: theme.textMuted }]}>Roz ka din</Text>
                    {g.routine.map((it) => (
                      <View key={`r-${it.id}-${it.at}`} style={styles.routineRow}>
                        <Text style={[styles.routineTime, { color: catStyle(it).color }]}>{istTime(it.at)}</Text>
                        <Text style={[styles.routineTitle, { color: theme.text }]}>
                          {it.title}{it.dose ? <Text style={{ color: theme.textMuted }}>{`  ·  ${it.dose}`}</Text> : null}
                        </Text>
                      </View>
                    ))}
                  </View>
                ) : null}
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
    flexDirection: 'row', alignItems: 'flex-start',
    borderRadius: Radius.lg, borderWidth: 1,
    paddingVertical: Spacing.lg, paddingRight: Spacing.lg, paddingLeft: Spacing.md,
    marginBottom: Spacing.md,
    overflow: 'hidden',
  },
  stripe: {
    position: 'absolute', left: 0, top: 0, bottom: 0, width: 5,
  },
  // The time first and large: it is what she looks for. It sat at the right
  // edge and squeezed the title into a column five words wide.
  timeCol:   { width: 84, marginLeft: Spacing.xs, alignItems: 'flex-start' },
  timeText:  { ...Typography.heading, fontWeight: '700' },
  cardBody:  { flex: 1, marginLeft: Spacing.sm },
  cardTitle: { ...Typography.bodyLg, fontWeight: '600', lineHeight: 26 },
  cardMeta:  { ...Typography.label, marginTop: 4 },
  bellRow:   { flexDirection: 'row', alignItems: 'center', marginTop: 6 },
  routineBox: {
    borderWidth: 1, borderRadius: Radius.lg, borderStyle: 'dashed',
    paddingVertical: Spacing.sm, paddingHorizontal: Spacing.lg, marginTop: Spacing.xs,
  },
  routineHead:  { ...Typography.label, marginBottom: Spacing.xs, textTransform: 'uppercase', letterSpacing: 1 },
  routineRow:   { flexDirection: 'row', alignItems: 'flex-start', paddingVertical: 6 },
  routineTime:  { ...Typography.body, fontWeight: '600', width: 84 },
  routineTitle: { ...Typography.body, flex: 1, marginLeft: Spacing.sm },
  emptyWrap: { alignItems: 'center', paddingTop: 80, paddingHorizontal: Spacing.xl },
  emptyEmoji:{ fontSize: 48, marginBottom: Spacing.lg },
  emptyText: { ...Typography.bodyLg, textAlign: 'center', lineHeight: 28 },
})

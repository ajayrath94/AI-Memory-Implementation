import React, { useEffect, useState } from 'react'
import {
  View, Text, ScrollView, StyleSheet,
  SafeAreaView, TouchableOpacity, ActivityIndicator,
  RefreshControl, Alert,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { Ionicons } from '@expo/vector-icons'
import { useTheme } from '../hooks/useTheme'
import { Colors, API_BASE, API_KEY } from '../constants'
import { useAppStore } from '../store/appStore'

interface Reminder {
  id:             string
  what:           string
  fire_at_local:  string
  fire_at_utc:    string
  status:         string
  source:         string
}
interface RemindersResponse {
  upcoming: Reminder[]
  past:     Reminder[]
  counts:   { upcoming: number; past: number }
}

export default function RemindersScreen() {
  const theme = useTheme()
  const { userId } = useAppStore()
  const [data,       setData]       = useState<RemindersResponse | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchReminders = async () => {
    try {
      const res  = await fetch(`${API_BASE}/reminders/${userId}`, {
        headers: { 'X-API-Key': API_KEY },
      })
      const json = await res.json()
      setData(json)
    } catch (err) {
      console.error('Failed to fetch reminders:', err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchReminders()
    const interval = setInterval(fetchReminders, 15000)
    return () => clearInterval(interval)
  }, [])

  const onRefresh = () => { setRefreshing(true); fetchReminders() }

  const cancelReminder = (r: Reminder) => {
    Alert.alert(
      'Cancel reminder?',
      `"${r.what}" — ${r.fire_at_local}`,
      [
        { text: 'Keep it', style: 'cancel' },
        {
          text: 'Cancel it', style: 'destructive',
          onPress: async () => {
            try {
              await fetch(`${API_BASE}/reminders/${r.id}/cancel`, {
                method: 'POST', headers: { 'X-API-Key': API_KEY },
              })
              fetchReminders()
            } catch (err) { console.error('Cancel failed:', err) }
          },
        },
      ],
    )
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.safe, { backgroundColor: theme.bg }]}>
        <View style={styles.center}>
          <ActivityIndicator color={Colors.accent} size="large" />
          <Text style={styles.loadingText}>Loading reminders...</Text>
        </View>
      </SafeAreaView>
    )
  }

  const upcoming = data?.upcoming || []
  const past     = data?.past || []

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: theme.bg }]}>
      <StatusBar style="light" />
      <View style={[styles.header, { backgroundColor: theme.bg, borderBottomColor: theme.border }]}>
        <Text style={styles.headerTitle}>⏰ Reminders</Text>
        <Text style={styles.headerSub}>
          {upcoming.length > 0
            ? `${upcoming.length} coming up`
            : 'Nothing scheduled'}
        </Text>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.accent} />
        }
      >
        {/* Empty state */}
        {upcoming.length === 0 && past.length === 0 && (
          <View style={styles.empty}>
            <Ionicons name="notifications-outline" size={48} color={Colors.textMuted} />
            <Text style={styles.emptyTitle}>No reminders yet</Text>
            <Text style={styles.emptyText}>
              Just tell Nancy in chat — like "kal 12 baje doctor yaad dilana" — and it'll show up here.
            </Text>
          </View>
        )}

        {/* Upcoming */}
        {upcoming.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionLabel}>UPCOMING</Text>
            {upcoming.map(r => (
              <View key={r.id} style={[styles.card, { borderColor: theme.border }]}>
                <View style={styles.cardMain}>
                  <View style={styles.cardDot} />
                  <View style={styles.cardBody}>
                    <Text style={styles.cardWhat}>{r.what}</Text>
                    <Text style={styles.cardTime}>{r.fire_at_local}</Text>
                  </View>
                  <TouchableOpacity
                    onPress={() => cancelReminder(r)}
                    hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                  >
                    <Ionicons name="close-circle-outline" size={22} color={Colors.textMuted} />
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        )}

        {/* Past */}
        {past.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionLabel}>PAST</Text>
            {past.map(r => (
              <View key={r.id} style={[styles.card, styles.cardPast, { borderColor: theme.border }]}>
                <View style={styles.cardMain}>
                  <View style={[styles.cardDot, styles.cardDotPast]} />
                  <View style={styles.cardBody}>
                    <Text style={[styles.cardWhat, styles.cardWhatPast]}>{r.what}</Text>
                    <Text style={styles.cardTime}>{r.fire_at_local}</Text>
                  </View>
                  <Text style={[
                    styles.statusPill,
                    r.status === 'cancelled' ? styles.statusCancelled : styles.statusFired,
                  ]}>
                    {r.status === 'cancelled' ? 'cancelled' : 'done'}
                  </Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe:   { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  loadingText: { color: Colors.textMuted, fontSize: 14 },

  header: {
    paddingHorizontal: 20, paddingTop: 16, paddingBottom: 14,
    borderBottomWidth: 0.5,
  },
  headerTitle: { fontSize: 22, fontWeight: '700', color: Colors.text },
  headerSub:   { fontSize: 13, color: Colors.textMuted, marginTop: 2 },

  scroll:        { flex: 1 },
  scrollContent: { padding: 16, paddingBottom: 40 },

  section:      { marginBottom: 24 },
  sectionLabel: {
    fontSize: 12, fontWeight: '700', color: Colors.textMuted,
    letterSpacing: 1, marginBottom: 10, marginLeft: 4,
  },

  card: {
    borderWidth: 0.5, borderRadius: 14,
    paddingVertical: 14, paddingHorizontal: 16, marginBottom: 10,
    backgroundColor: '#ffffff08',
  },
  cardPast: { opacity: 0.6 },
  cardMain: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  cardDot: {
    width: 8, height: 8, borderRadius: 4,
    backgroundColor: Colors.accent, flexShrink: 0,
  },
  cardDotPast: { backgroundColor: Colors.textMuted },
  cardBody:  { flex: 1 },
  cardWhat:  { fontSize: 16, fontWeight: '600', color: Colors.text, marginBottom: 2 },
  cardWhatPast: { textDecorationLine: 'line-through' },
  cardTime:  { fontSize: 13, color: Colors.textMuted },

  statusPill: {
    fontSize: 11, fontWeight: '600', overflow: 'hidden',
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8,
  },
  statusFired:     { color: Colors.accentGreen, backgroundColor: Colors.accentGreen + '18' },
  statusCancelled: { color: Colors.textMuted, backgroundColor: Colors.textMuted + '18' },

  empty:      { alignItems: 'center', paddingTop: 80, paddingHorizontal: 32, gap: 10 },
  emptyTitle: { fontSize: 17, fontWeight: '600', color: Colors.text },
  emptyText:  { fontSize: 14, color: Colors.textMuted, textAlign: 'center', lineHeight: 20 },
})

import React, { useEffect, useState, useCallback } from 'react'
import {
  View, Text, ScrollView, StyleSheet,
  SafeAreaView, TouchableOpacity, ActivityIndicator,
  RefreshControl, Alert,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { Ionicons } from '@expo/vector-icons'
import { router } from 'expo-router'
import { useTheme } from '../../hooks/useTheme'
import { Colors, Typography, Spacing, Radius, API_BASE, API_KEY } from '../../constants'

// ── Types ──────────────────────────────────────────────────────────────────────
interface Caregiver {
  id:       string
  name:     string
  email:    string
  org_type: string
  care_relationships: CareRelationship[]
}

interface CareRelationship {
  id:          string
  user_id:     string
  relationship: string
  active:      boolean
  user_profile?: UserProfile
}

interface UserProfile {
  user_id:      string
  name:         string | null
  language_pref: string | null
  health:       { conditions?: string[] }
  personality:  { emotional_state?: string }
  updated_at:   string
}

interface Alert {
  id:         string
  user_id:    string
  alert_type: string
  severity:   string
  message:    string
  sent_at:    string
  read_at:    string | null
}

// ── API ────────────────────────────────────────────────────────────────────────
const api = async (path: string, token: string) => {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'X-API-Key': API_KEY, 'Authorization': `Bearer ${token}` }
  })
  if (!res.ok) throw new Error(`${res.status}`)
  return res.json()
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: Colors.accentRed,
  high:     Colors.accentRed,
  medium:   Colors.accentWarm,
  low:      Colors.accent,
}

// ── Main Screen ────────────────────────────────────────────────────────────────
export default function CaregiverDashboard() {
  const theme = useTheme()
  const [caregiver,  setCaregiver]  = useState<Caregiver | null>(null)
  const [alerts,     setAlerts]     = useState<Alert[]>([])
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  // TODO: get token from secure store after auth
  const token = '' // placeholder until auth is wired

  const fetchAll = useCallback(async () => {
    try {
      const [cgData, alertData] = await Promise.all([
        api('/auth/caregiver/me', token),
        caregiver?.id
          ? api(`/alerts/caregiver/${caregiver.id}`, token)
          : Promise.resolve({ alerts: [] }),
      ])
      setCaregiver(cgData.caregiver)
      setAlerts(alertData.alerts || [])
    } catch (e) {
      console.error('Dashboard fetch failed:', e)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [token, caregiver?.id])

  useEffect(() => { fetchAll() }, [])

  const onRefresh = () => { setRefreshing(true); fetchAll() }

  const markRead = async (alertId: string) => {
    try {
      await fetch(`${API_BASE}/alerts/read/${alertId}`, {
        method:  'POST',
        headers: { 'X-API-Key': API_KEY },
      })
      setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, read_at: new Date().toISOString() } : a))
    } catch (e) {}
  }

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}>
          <ActivityIndicator color={Colors.accent} size="large" />
          <Text style={styles.loadingText}>Loading dashboard...</Text>
        </View>
      </SafeAreaView>
    )
  }

  const unreadAlerts    = alerts.filter(a => !a.read_at)
  const relationships   = caregiver?.care_relationships || []
  const criticalAlerts  = alerts.filter(a => a.severity === 'critical' || a.severity === 'high')

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />

      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>Care Dashboard</Text>
          <Text style={styles.headerSub}>
            {caregiver?.name || 'Caregiver'} · {relationships.length} {relationships.length === 1 ? 'person' : 'people'}
          </Text>
        </View>
        <TouchableOpacity
          style={styles.headerBtn}
          onPress={() => router.push('/caregiver/settings')}
        >
          <Ionicons name="settings-outline" size={22} color={Colors.textMuted} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >

        {/* Critical alerts banner */}
        {criticalAlerts.filter(a => !a.read_at).length > 0 && (
          <View style={styles.criticalBanner}>
            <Ionicons name="warning" size={20} color="#fff" />
            <Text style={styles.criticalText}>
              {criticalAlerts.filter(a => !a.read_at).length} urgent alert{criticalAlerts.filter(a => !a.read_at).length > 1 ? 's' : ''} need attention
            </Text>
          </View>
        )}

        {/* Stats row */}
        <View style={styles.statsRow}>
          <StatCard icon="people-outline" value={String(relationships.length)} label="Linked" color={Colors.accent} />
          <StatCard icon="notifications-outline" value={String(unreadAlerts.length)} label="Unread" color={Colors.accentRed} />
          <StatCard icon="checkmark-circle-outline" value={String(alerts.filter(a => a.read_at).length)} label="Resolved" color={Colors.accentGreen} />
        </View>

        {/* Linked users */}
        <SectionTitle title="👥 People you care for" />
        {relationships.length === 0 ? (
          <EmptyCard
            icon="person-add-outline"
            title="No one linked yet"
            subtitle="Add a family member to start monitoring"
            action="Add person"
            onAction={() => router.push('/caregiver/add-user')}
          />
        ) : (
          relationships.map(rel => (
            <UserCard
              key={rel.id}
              relationship={rel}
              alerts={alerts.filter(a => a.user_id === rel.user_id && !a.read_at)}
              onPress={() => router.push(`/caregiver/user/${rel.user_id}`)}
            />
          ))
        )}

        {/* Add person button */}
        {relationships.length > 0 && (
          <TouchableOpacity
            style={styles.addPersonBtn}
            onPress={() => router.push('/caregiver/add-user')}
          >
            <Ionicons name="add-circle-outline" size={20} color={Colors.accent} />
            <Text style={styles.addPersonText}>Add another person</Text>
          </TouchableOpacity>
        )}

        {/* Recent alerts */}
        <SectionTitle title="🔔 Recent alerts" />
        {alerts.length === 0 ? (
          <EmptyCard
            icon="shield-checkmark-outline"
            title="All clear"
            subtitle="No alerts detected yet"
          />
        ) : (
          alerts.slice(0, 10).map(alert => (
            <AlertCard
              key={alert.id}
              alert={alert}
              onRead={() => markRead(alert.id)}
            />
          ))
        )}

      </ScrollView>
    </SafeAreaView>
  )
}

// ── Components ─────────────────────────────────────────────────────────────────

function SectionTitle({ title }: { title: string }) {
  return <Text style={styles.sectionTitle}>{title}</Text>
}

function StatCard({ icon, value, label, color }: {
  icon: any; value: string; label: string; color: string
}) {
  return (
    <View style={styles.statCard}>
      <Ionicons name={icon} size={20} color={color} />
      <Text style={[styles.statValue, { color }]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  )
}

function UserCard({ relationship, alerts, onPress }: {
  relationship: CareRelationship; alerts: Alert[]; onPress: () => void
}) {
  const profile = relationship.user_profile
  const name    = profile?.name || relationship.user_id

  return (
    <TouchableOpacity style={styles.userCard} onPress={onPress} activeOpacity={0.8}>
      <View style={styles.userCardLeft}>
        <View style={styles.userAvatar}>
          <Text style={styles.userAvatarText}>
            {name ? name[0].toUpperCase() : '?'}
          </Text>
        </View>
        <View style={{ flex: 1, gap: 3 }}>
          <Text style={styles.userName}>{name}</Text>
          <Text style={styles.userRelation}>{relationship.relationship || 'Family'}</Text>
          {profile?.personality?.emotional_state && (
            <Text style={styles.userEmotion}>{profile.personality.emotional_state}</Text>
          )}
          {profile?.health?.conditions && profile.health.conditions.length > 0 && (
            <Text style={styles.userHealth} numberOfLines={1}>
              ⚕️ {profile.health.conditions[0]}
            </Text>
          )}
        </View>
      </View>
      <View style={styles.userCardRight}>
        {alerts.length > 0 && (
          <View style={styles.alertBadge}>
            <Text style={styles.alertBadgeText}>{alerts.length}</Text>
          </View>
        )}
        <Ionicons name="chevron-forward" size={16} color={Colors.textMuted} />
      </View>
    </TouchableOpacity>
  )
}

function AlertCard({ alert, onRead }: { alert: Alert; onRead: () => void }) {
  const color   = SEVERITY_COLORS[alert.severity] || Colors.accent
  const isUnread = !alert.read_at

  return (
    <View style={[styles.alertCard, isUnread && styles.alertCardUnread]}>
      <View style={[styles.alertDot, { backgroundColor: color }]} />
      <View style={{ flex: 1, gap: 4 }}>
        <View style={styles.alertHeader}>
          <Text style={[styles.alertType, { color }]}>
            {alert.alert_type.toUpperCase()} · {alert.severity}
          </Text>
          <Text style={styles.alertTime}>
            {new Date(alert.sent_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </Text>
        </View>
        <Text style={styles.alertUserId}>{alert.user_id}</Text>
        <Text style={styles.alertMsg} numberOfLines={2}>{alert.message}</Text>
        {isUnread && (
          <TouchableOpacity onPress={onRead} style={styles.markReadBtn}>
            <Text style={styles.markReadText}>Mark as read</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  )
}

function EmptyCard({ icon, title, subtitle, action, onAction }: {
  icon: any; title: string; subtitle: string; action?: string; onAction?: () => void
}) {
  return (
    <View style={styles.emptyCard}>
      <Ionicons name={icon} size={32} color={Colors.textMuted} />
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptySub}>{subtitle}</Text>
      {action && onAction && (
        <TouchableOpacity style={styles.emptyAction} onPress={onAction}>
          <Text style={styles.emptyActionText}>{action}</Text>
        </TouchableOpacity>
      )}
    </View>
  )
}

// ── Styles ─────────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  safe:         { flex: 1, backgroundColor: Colors.bg },
  center:       { flex: 1, alignItems: 'center', justifyContent: 'center', gap: Spacing.md },
  loadingText:  { ...Typography.body, color: Colors.textMuted },
  header: {
    flexDirection:     'row',
    alignItems:        'center',
    justifyContent:    'space-between',
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.md,
    borderBottomWidth: 0.5,
    borderBottomColor: Colors.border,
  },
  headerTitle:  { ...Typography.heading, color: Colors.text },
  headerSub:    { ...Typography.caption, color: Colors.textMuted, marginTop: 2 },
  headerBtn:    { padding: Spacing.sm },
  scroll:       { padding: Spacing.lg, gap: Spacing.md },
  criticalBanner: {
    flexDirection:   'row',
    alignItems:      'center',
    gap:             Spacing.sm,
    backgroundColor: Colors.accentRed,
    borderRadius:    Radius.md,
    padding:         Spacing.md,
  },
  criticalText:   { ...Typography.label, color: '#fff', flex: 1 },
  statsRow:       { flexDirection: 'row', gap: Spacing.sm },
  statCard: {
    flex:            1,
    backgroundColor: Colors.bgCard,
    borderRadius:    Radius.md,
    padding:         Spacing.md,
    alignItems:      'center',
    gap:             4,
    borderWidth:     0.5,
    borderColor:     Colors.border,
  },
  statValue:      { fontSize: 20, fontWeight: '600' },
  statLabel:      { ...Typography.caption, color: Colors.textMuted },
  sectionTitle:   { ...Typography.label, color: Colors.textMuted, marginTop: Spacing.sm },
  userCard: {
    flexDirection:   'row',
    alignItems:      'center',
    backgroundColor: Colors.bgCard,
    borderRadius:    Radius.lg,
    padding:         Spacing.lg,
    borderWidth:     0.5,
    borderColor:     Colors.border,
    gap:             Spacing.md,
  },
  userCardLeft:   { flexDirection: 'row', flex: 1, gap: Spacing.md, alignItems: 'flex-start' },
  userCardRight:  { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  userAvatar: {
    width:           44,
    height:          44,
    borderRadius:    22,
    backgroundColor: Colors.accent + '22',
    borderWidth:     1.5,
    borderColor:     Colors.accent + '44',
    alignItems:      'center',
    justifyContent:  'center',
    flexShrink:      0,
  },
  userAvatarText: { fontSize: 18, fontWeight: '700', color: Colors.accent },
  userName:       { ...Typography.heading, color: Colors.text },
  userRelation:   { ...Typography.caption, color: Colors.textMuted },
  userEmotion:    { ...Typography.caption, color: Colors.accentGreen },
  userHealth:     { ...Typography.caption, color: Colors.accentRed },
  alertBadge: {
    backgroundColor: Colors.accentRed,
    borderRadius:    Radius.full,
    width:           20,
    height:          20,
    alignItems:      'center',
    justifyContent:  'center',
  },
  alertBadgeText: { color: '#fff', fontSize: 11, fontWeight: '700' },
  addPersonBtn: {
    flexDirection:  'row',
    alignItems:     'center',
    justifyContent: 'center',
    gap:            Spacing.sm,
    padding:        Spacing.md,
    borderRadius:   Radius.md,
    borderWidth:    0.5,
    borderColor:    Colors.accent + '40',
    borderStyle:    'dashed',
  },
  addPersonText:  { ...Typography.label, color: Colors.accent },
  alertCard: {
    flexDirection:   'row',
    backgroundColor: Colors.bgCard,
    borderRadius:    Radius.lg,
    padding:         Spacing.lg,
    gap:             Spacing.md,
    borderWidth:     0.5,
    borderColor:     Colors.border,
  },
  alertCardUnread: { borderColor: Colors.accentWarm + '60', backgroundColor: Colors.accentWarm + '08' },
  alertDot:       { width: 8, height: 8, borderRadius: 4, marginTop: 4, flexShrink: 0 },
  alertHeader:    { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  alertType:      { ...Typography.label },
  alertTime:      { ...Typography.caption, color: Colors.textMuted },
  alertUserId:    { ...Typography.caption, color: Colors.textMuted },
  alertMsg:       { ...Typography.body, color: Colors.text, lineHeight: 20 },
  markReadBtn:    { alignSelf: 'flex-start', marginTop: 4 },
  markReadText:   { ...Typography.caption, color: Colors.accent },
  emptyCard: {
    backgroundColor: Colors.bgCard,
    borderRadius:    Radius.lg,
    padding:         Spacing.xl,
    alignItems:      'center',
    gap:             Spacing.sm,
    borderWidth:     0.5,
    borderColor:     Colors.border,
  },
  emptyTitle:      { ...Typography.heading, color: Colors.textMuted },
  emptySub:        { ...Typography.body, color: Colors.textMuted, textAlign: 'center' },
  emptyAction: {
    backgroundColor: Colors.accent,
    borderRadius:    Radius.md,
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.sm,
    marginTop:       Spacing.sm,
  },
  emptyActionText: { ...Typography.label, color: '#fff' },
})

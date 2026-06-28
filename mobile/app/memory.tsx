import React, { useEffect, useState } from 'react'
import {
  View, Text, ScrollView, StyleSheet,
  SafeAreaView, TouchableOpacity, ActivityIndicator,
  RefreshControl
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { Ionicons } from '@expo/vector-icons'
import { Colors, API_BASE } from '../constants'

interface UserMemory {
  user_id:                 string
  summary:                 string | null
  key_facts:               string[]
  dominant_pillars:        string[]
  session_count:           number
  updated_at:              string
  behavioural_fingerprint: any
  pillar_trend:            any
}

interface UserProfile {
  user_id:       string
  name:          string | null
  age_group:     string | null
  location:      string | null
  language_pref: string | null
  family:        { children?: string[]; grandchildren?: string[]; spouse?: string; other?: string[] }
  health:        { conditions?: string[]; concerns?: string[]; medications?: string[] }
  interests:     { sports?: string[]; music?: string[]; entertainment?: string[]; hobbies?: string[] }
  personality:   { traits?: string[]; emotional_state?: string; communication_style?: string }
  life_context:  { occupation?: string; living_situation?: string; notable_events?: string[] }
  updated_at:    string
}

const PILLAR_COLORS: Record<string, string> = {
  HEALTH_WELLNESS: '#e05555',
  SADNESS:         '#7b68ee',
  STRESS:          '#ff8c42',
  FEAR:            '#d4537e',
  FINANCE:         '#3a9bd5',
  JOY:             '#4caf7d',
  LOVE:            '#ff6b9d',
  OPTIMISM:        '#3b6d11',
  ENTERTAINMENT:   '#ba7517',
  GENERAL:         '#888780',
}

export default function MemoryScreen() {
  const [memory,     setMemory]     = useState<UserMemory | null>(null)
  const [profile,    setProfile]    = useState<UserProfile | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [tab,        setTab]        = useState<'memory' | 'profile'>('memory')

  const fetchAll = async () => {
    try {
      const [memRes, profRes] = await Promise.all([
        fetch(`${API_BASE}/memory/user/default`),
        fetch(`${API_BASE}/memory/profile/default`),
      ])
      const memData  = await memRes.json()
      const profData = await profRes.json()
      setMemory(memData)
      setProfile(profData && Object.keys(profData).length > 0 ? profData : null)
    } catch (err) {
      console.error('Failed to fetch:', err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 15000)
    return () => clearInterval(interval)
  }, [])

  const onRefresh = () => { setRefreshing(true); fetchAll() }

  const getFingerprint = () => {
    if (!memory?.behavioural_fingerprint) return null
    const fp = memory.behavioural_fingerprint
    if (typeof fp === 'string') { try { return JSON.parse(fp) } catch { return null } }
    return fp
  }

  const getTrend = () => {
    if (!memory?.pillar_trend) return null
    const t = memory.pillar_trend
    if (typeof t === 'string') { try { return JSON.parse(t) } catch { return null } }
    return t
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

  const fingerprint = getFingerprint()
  const trend       = getTrend()
  const alerts      = fingerprint?.alerts || []

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />

      <View style={styles.header}>
        <Text style={styles.headerTitle}>🧠 Memory Profile</Text>
        <TouchableOpacity onPress={onRefresh}>
          <Ionicons name="refresh-outline" size={20} color={Colors.textMuted} />
        </TouchableOpacity>
      </View>

      <View style={styles.tabs}>
        <TouchableOpacity
          style={[styles.tab, tab === 'memory' && styles.tabActive]}
          onPress={() => setTab('memory')}
        >
          <Text style={[styles.tabText, tab === 'memory' && styles.tabTextActive]}>Memory</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, tab === 'profile' && styles.tabActive]}
          onPress={() => setTab('profile')}
        >
          <Text style={[styles.tabText, tab === 'profile' && styles.tabTextActive]}>Profile</Text>
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.accent} />
        }
      >
        {tab === 'memory' ? (
          <MemoryTab memory={memory} fingerprint={fingerprint} trend={trend} alerts={alerts} />
        ) : (
          <ProfileTab profile={profile} />
        )}
      </ScrollView>
    </SafeAreaView>
  )
}

function MemoryTab({ memory, fingerprint, trend, alerts }: any) {
  if (!memory?.summary) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyIcon}>🧠</Text>
        <Text style={styles.emptyText}>No memory yet</Text>
        <Text style={styles.emptyHint}>Have a few conversations — Nancy will build a memory profile automatically</Text>
      </View>
    )
  }
  return (
    <>
      {alerts.length > 0 && (
        <View style={styles.alertBox}>
          <Text style={styles.alertTitle}>⚠️ Behavioural Alerts</Text>
          {alerts.map((alert: string, i: number) => (
            <Text key={i} style={styles.alertText}>• {alert}</Text>
          ))}
        </View>
      )}
      <View style={styles.statsRow}>
        <StatCard icon="chatbubbles-outline" value={String(memory.session_count)} label="Sessions" />
        <StatCard icon="bulb-outline" value={String(memory.key_facts?.length || 0)} label="Key facts" />
        <StatCard icon="analytics-outline" value={String(memory.dominant_pillars?.length || 0)} label="Pillars" />
      </View>
      {fingerprint && (
        <Section title="Behavioural Pattern">
          <FPRow label="Dominant pattern" value={fingerprint.dominant_pattern || 'Building...'} />
          {fingerprint.emerging_interests?.length > 0 && <FPRow label="📈 Emerging" value={fingerprint.emerging_interests.join(', ')} />}
          {fingerprint.fading_interests?.length > 0 && <FPRow label="📉 Fading" value={fingerprint.fading_interests.join(', ')} />}
          {fingerprint.cycle_detected && <FPRow label="🔄 Cycle" value={`Every ${fingerprint.cycle_length} sessions`} />}
          <FPRow label="Consistency" value={`${Math.round((fingerprint.session_consistency || 0) * 100)}%`} />
        </Section>
      )}
      <Section title="What Nancy knows about you">
        <Text style={styles.summaryText}>{memory.summary}</Text>
      </Section>
      {memory.key_facts?.length > 0 && (
        <Section title="Key Facts">
          {memory.key_facts.map((fact: string, i: number) => (
            <View key={i} style={styles.factRow}>
              <View style={styles.factDot} />
              <Text style={styles.factText}>{fact}</Text>
            </View>
          ))}
        </Section>
      )}
      {memory.dominant_pillars?.length > 0 && (
        <Section title="Your Main Topics">
          <View style={styles.pillarsRow}>
            {memory.dominant_pillars.map((pillar: string, i: number) => (
              <View key={i} style={[styles.pillarChip,
                { backgroundColor: (PILLAR_COLORS[pillar] || '#1a2a3a') + '22',
                  borderColor: (PILLAR_COLORS[pillar] || Colors.accent) + '66' }]}>
                <Text style={[styles.pillarChipText, { color: PILLAR_COLORS[pillar] || Colors.accent }]}>
                  {pillar.replace(/_/g, ' ')}
                </Text>
              </View>
            ))}
          </View>
        </Section>
      )}
      {trend?.pillar_trends && Object.keys(trend.pillar_trends).length > 0 && (
        <Section title="Topic Trends">
          {Object.entries(trend.pillar_trends)
            .filter(([_, t]) => t !== 'stable')
            .map(([pillar, t], i) => (
              <View key={i} style={styles.trendRow}>
                <Text style={styles.trendPillar}>{pillar.replace(/_/g, ' ')}</Text>
                <Text style={[styles.trendDir, { color: t === 'rising' ? '#4caf7d' : '#e05555' }]}>
                  {t === 'rising' ? '📈 Rising' : '📉 Falling'}
                </Text>
              </View>
            ))}
        </Section>
      )}
      {memory.updated_at && (
        <Text style={styles.updatedAt}>Last updated: {new Date(memory.updated_at).toLocaleString()}</Text>
      )}
    </>
  )
}

function ProfileTab({ profile }: { profile: UserProfile | null }) {
  if (!profile) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyIcon}>👤</Text>
        <Text style={styles.emptyText}>No profile yet</Text>
        <Text style={styles.emptyHint}>Nancy builds your profile automatically as you chat</Text>
      </View>
    )
  }
  const hasFamily    = profile.family    && Object.values(profile.family).some(v => v && (Array.isArray(v) ? v.length > 0 : v))
  const hasHealth    = profile.health    && Object.values(profile.health).some(v => Array.isArray(v) && v.length > 0)
  const hasInterests = profile.interests && Object.values(profile.interests).some(v => Array.isArray(v) && v.length > 0)
  const hasLife      = profile.life_context && Object.values(profile.life_context).some(v => v)

  return (
    <>
      <View style={styles.identityCard}>
        <View style={styles.avatarCircle}>
          <Text style={styles.avatarText}>{profile.name ? profile.name[0].toUpperCase() : '?'}</Text>
        </View>
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={styles.profileName}>{profile.name || 'Name not known yet'}</Text>
          {profile.location   && <Text style={styles.profileMeta}>📍 {profile.location}</Text>}
          {profile.age_group  && <Text style={styles.profileMeta}>🎂 {profile.age_group}</Text>}
          {profile.language_pref && <Text style={styles.profileMeta}>💬 {profile.language_pref}</Text>}
        </View>
      </View>
      {profile.personality?.emotional_state && (
        <View style={styles.emotionBadge}>
          <Text style={styles.emotionText}>Current state: {profile.personality.emotional_state}</Text>
        </View>
      )}
      {hasFamily && (
        <Section title="👨‍👩‍👧 Family">
          {profile.family.spouse && <ProfileRow icon="heart-outline" label="Spouse" value={profile.family.spouse} />}
          {profile.family.children?.map((c, i) => <ProfileRow key={i} icon="people-outline" label="Child" value={c} />)}
          {profile.family.grandchildren?.map((g, i) => <ProfileRow key={i} icon="happy-outline" label="Grandchild" value={g} />)}
          {profile.family.other?.filter(o => o !== 'feels lonely').map((o, i) => (
            <ProfileRow key={i} icon="person-outline" label="Other" value={o} />
          ))}
          {profile.family.other?.includes('feels lonely') && (
            <View style={styles.lonelinessTag}>
              <Text style={styles.lonelinessText}>⚠️ Mentions feeling lonely</Text>
            </View>
          )}
        </Section>
      )}
      {hasHealth && (
        <Section title="🏥 Health">
          {profile.health.conditions?.map((c, i) => <ProfileRow key={i} icon="medkit-outline" label="Condition" value={c} color="#e05555" />)}
          {profile.health.concerns?.map((c, i)   => <ProfileRow key={i} icon="warning-outline" label="Concern" value={c} color="#ff8c42" />)}
          {profile.health.medications?.map((m, i) => <ProfileRow key={i} icon="flask-outline" label="Medication" value={m} color="#3a9bd5" />)}
        </Section>
      )}
      {hasInterests && (
        <Section title="⭐ Interests">
          {Object.entries(profile.interests).map(([cat, items]) =>
            Array.isArray(items) && items.length > 0 ? (
              <View key={cat} style={styles.interestRow}>
                <Text style={styles.interestCategory}>{cat}</Text>
                <View style={styles.interestChips}>
                  {items.map((item, i) => (
                    <View key={i} style={styles.interestChip}>
                      <Text style={styles.interestChipText}>{item}</Text>
                    </View>
                  ))}
                </View>
              </View>
            ) : null
          )}
        </Section>
      )}
      {hasLife && (
        <Section title="📖 Life Context">
          {profile.life_context.occupation     && <ProfileRow icon="briefcase-outline" label="Occupation" value={profile.life_context.occupation} />}
          {profile.life_context.living_situation && <ProfileRow icon="home-outline" label="Living" value={profile.life_context.living_situation} />}
          {profile.life_context.notable_events?.map((e, i) => <ProfileRow key={i} icon="flag-outline" label="Goal" value={e} />)}
        </Section>
      )}
      {profile.personality?.communication_style && (
        <Section title="💬 Communication">
          <ProfileRow icon="chatbubble-outline" label="Style" value={profile.personality.communication_style} />
          {profile.personality.traits?.map((t, i) => <ProfileRow key={i} icon="sparkles-outline" label="Trait" value={t} />)}
        </Section>
      )}
      {profile.updated_at && (
        <Text style={styles.updatedAt}>Profile updated: {new Date(profile.updated_at).toLocaleString()}</Text>
      )}
    </>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <View style={styles.sectionContent}>{children}</View>
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

function FPRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.fpRow}>
      <Text style={styles.fpLabel}>{label}</Text>
      <Text style={styles.fpValue}>{value}</Text>
    </View>
  )
}

function ProfileRow({ icon, label, value, color }: { icon: any; label: string; value: string; color?: string }) {
  return (
    <View style={styles.profileRow}>
      <Ionicons name={icon} size={16} color={color || Colors.textMuted} />
      <Text style={styles.profileRowLabel}>{label}</Text>
      <Text style={[styles.profileRowValue, color ? { color } : {}]}>{value}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  safe:        { flex: 1, backgroundColor: Colors.bg },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 14,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
  },
  headerTitle:     { color: Colors.text, fontSize: 17, fontWeight: '600' },
  tabs:            { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: Colors.border },
  tab:             { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabActive:       { borderBottomWidth: 2, borderBottomColor: Colors.accent },
  tabText:         { color: Colors.textMuted, fontSize: 14 },
  tabTextActive:   { color: Colors.accent, fontWeight: '600' },
  scroll:          { padding: 16, gap: 12 },
  alertBox:        { backgroundColor: '#2a1a1a', borderRadius: 12, padding: 14, borderWidth: 1, borderColor: '#5a2e2e', gap: 6 },
  alertTitle:      { color: '#e05555', fontSize: 13, fontWeight: '600' },
  alertText:       { color: '#e88', fontSize: 13 },
  statsRow:        { flexDirection: 'row', gap: 10 },
  statCard:        { flex: 1, backgroundColor: Colors.bgCard, borderRadius: 12, padding: 14, alignItems: 'center', gap: 4, borderWidth: 1, borderColor: Colors.border },
  statValue:       { color: Colors.text, fontSize: 22, fontWeight: '700' },
  statLabel:       { color: Colors.textMuted, fontSize: 11 },
  section:         { backgroundColor: Colors.bgCard, borderRadius: 12, padding: 14, gap: 10, borderWidth: 1, borderColor: Colors.border },
  sectionTitle:    { color: Colors.textMuted, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.8 },
  sectionContent:  { gap: 8 },
  summaryText:     { color: Colors.text, fontSize: 14, lineHeight: 22 },
  factRow:         { flexDirection: 'row', alignItems: 'center', gap: 10 },
  factDot:         { width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.accent },
  factText:        { color: Colors.text, fontSize: 14, flex: 1 },
  pillarsRow:      { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  pillarChip:      { borderRadius: 20, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1 },
  pillarChipText:  { fontSize: 12, fontWeight: '500' },
  fpRow:           { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  fpLabel:         { color: Colors.textMuted, fontSize: 13 },
  fpValue:         { color: Colors.text, fontSize: 13, fontWeight: '500', flex: 1, textAlign: 'right' },
  trendRow:        { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  trendPillar:     { color: Colors.text, fontSize: 13 },
  trendDir:        { fontSize: 13, fontWeight: '500' },
  updatedAt:       { color: Colors.textMuted, fontSize: 11, textAlign: 'center' },
  center:          { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  loadingText:     { color: Colors.textMuted, fontSize: 14 },
  empty:           { alignItems: 'center', paddingTop: 80, gap: 12, paddingHorizontal: 32 },
  emptyIcon:       { fontSize: 48 },
  emptyText:       { color: Colors.textMuted, fontSize: 16, fontWeight: '600' },
  emptyHint:       { color: Colors.textMuted, fontSize: 13, textAlign: 'center', lineHeight: 20 },
  identityCard:    { backgroundColor: Colors.bgCard, borderRadius: 16, padding: 16, flexDirection: 'row', alignItems: 'center', gap: 14, borderWidth: 1, borderColor: Colors.border },
  avatarCircle:    { width: 56, height: 56, borderRadius: 28, backgroundColor: Colors.accent + '22', alignItems: 'center', justifyContent: 'center' },
  avatarText:      { color: Colors.accent, fontSize: 24, fontWeight: '700' },
  profileName:     { color: Colors.text, fontSize: 17, fontWeight: '600' },
  profileMeta:     { color: Colors.textMuted, fontSize: 13 },
  emotionBadge:    { backgroundColor: '#1a2a1a', borderRadius: 10, padding: 10, borderWidth: 1, borderColor: '#2a4a2a' },
  emotionText:     { color: '#4caf7d', fontSize: 13, textAlign: 'center' },
  profileRow:      { flexDirection: 'row', alignItems: 'center', gap: 10 },
  profileRowLabel: { color: Colors.textMuted, fontSize: 13, width: 80 },
  profileRowValue: { color: Colors.text, fontSize: 13, flex: 1 },
  lonelinessTag:   { backgroundColor: '#2a1a1a', borderRadius: 8, padding: 8, borderWidth: 1, borderColor: '#5a2e2e' },
  lonelinessText:  { color: '#e05555', fontSize: 12 },
  interestRow:     { gap: 6 },
  interestCategory: { color: Colors.textMuted, fontSize: 12, textTransform: 'capitalize' },
  interestChips:   { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  interestChip:    { backgroundColor: Colors.accent + '22', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4 },
  interestChipText: { color: Colors.accent, fontSize: 12 },
})

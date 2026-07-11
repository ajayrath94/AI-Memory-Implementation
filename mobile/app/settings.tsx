import React, { useState, useEffect } from 'react'
import {
  View, Text, ScrollView, StyleSheet, SafeAreaView,
  TouchableOpacity, Switch, Alert, ActivityIndicator,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { router } from 'expo-router'
import { useTheme } from '../hooks/useTheme'
import { Colors, Typography, Spacing, Radius, API_BASE, API_KEY, MODELS } from '../constants'
import { useAppStore } from '../store/appStore'

const BACKGROUNDS = [
  { id: 'dark',       label: 'Black',    color: '#0a0a0a' },
  { id: 'charcoal',   label: 'Charcoal', color: '#1a1a1a' },
  { id: 'midnight',   label: 'Midnight', color: '#0d1117' },
  { id: 'navy',       label: 'Navy',     color: '#0a0f1e' },
  { id: 'espresso',   label: 'Espresso', color: '#1a0f08' },
  { id: 'forest',     label: 'Forest',   color: '#0a1208' },
  { id: 'purple',     label: 'Purple',   color: '#120a1a' },
  { id: 'slate',      label: 'Slate',    color: '#0f1419' },
  { id: 'white',      label: 'White',    color: '#ffffff' },
  { id: 'soft',       label: 'Soft',     color: '#f5f5f0' },
  { id: 'warm_light', label: 'Warm',     color: '#fdf6ec' },
  { id: 'sky',        label: 'Sky',      color: '#eef4fb' },
  { id: 'mint',       label: 'Mint',     color: '#eef8f4' },
  { id: 'lavender',   label: 'Lavender', color: '#f3eefb' },
]

export default function SettingsScreen() {
  const theme = useTheme()
  const { model, setModel, userId } = useAppStore()
  const [weights,    setWeights]    = useState<Record<string, number>>({})
  const [loadingW,   setLoadingW]   = useState(true)
  const [savingW,    setSavingW]    = useState(false)
  const [background, setBackground] = useState('dark')
  const [persona,    setPersona]    = useState<any>(null)

  useEffect(() => {
    loadWeights()
    loadPersona()
  }, [userId])

  const loadWeights = async () => {
    try {
      const res  = await fetch(`${API_BASE}/weights/${userId}`, { headers: { 'X-API-Key': API_KEY } })
      const data = await res.json()
      setWeights(data.weights || {})
    } catch (e) {} finally { setLoadingW(false) }
  }

  const loadPersona = async () => {
    try {
      const res  = await fetch(`${API_BASE}/persona/${userId}`, { headers: { 'X-API-Key': API_KEY } })
      const data = await res.json()
      setPersona(data.persona)
    } catch (e) {}
  }

  const saveWeight = async (pillar: string, weight: number) => {
    setSavingW(true)
    try {
      await fetch(`${API_BASE}/weights/${userId}/${pillar}?weight=${weight}`, {
        method: 'PUT', headers: { 'X-API-Key': API_KEY }
      })
      setWeights(w => ({ ...w, [pillar]: weight }))
    } catch (e) {
      Alert.alert('Error', 'Failed to save weight')
    } finally { setSavingW(false) }
  }

  const resetWeights = async () => {
    Alert.alert('Reset weights?', 'All pillar weights will return to default (1.0)', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Reset', style: 'destructive', onPress: async () => {
        await fetch(`${API_BASE}/weights/${userId}`, {
          method: 'DELETE', headers: { 'X-API-Key': API_KEY }
        })
        await loadWeights()
      }}
    ])
  }

  const CORE_PILLARS = [
    { id: 'HEALTH_WELLNESS', label: 'Health & Wellness', emoji: '🏥', color: Colors.accentRed },
    { id: 'SADNESS',         label: 'Emotional Support', emoji: '💙', color: '#534AB7' },
    { id: 'STRESS',          label: 'Stress',            emoji: '😰', color: Colors.accentWarm },
    { id: 'LOVE',            label: 'Family & Love',     emoji: '❤️',  color: '#D4537E' },
    { id: 'ENTERTAINMENT',   label: 'Entertainment',     emoji: '🎵', color: Colors.accentWarm },
    { id: 'FINANCE',         label: 'Finance',           emoji: '💰', color: Colors.accent },
    { id: 'GENERAL',         label: 'General',           emoji: '💬', color: Colors.textMuted },
  ]

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: Colors.bg }]}>
      <View style={[styles.header, { backgroundColor: Colors.bg, borderBottomColor: Colors.border }]}>
        <Text style={[styles.headerTitle, { color: Colors.text }]}>Settings</Text>
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>

        {/* Companion Persona */}
        <SectionHeader title="🤖 Companion" />
        <TouchableOpacity
          style={styles.personaCard}
          onPress={() => router.push('/persona-setup')}
          activeOpacity={0.8}
        >
          <View style={styles.personaAvatar}>
            <Text style={styles.personaAvatarText}>
              {persona?.bot_name?.[0]?.toUpperCase() || 'N'}
            </Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={[styles.personaName, { color: theme.text }]}>{persona?.bot_name || 'Nancy'}</Text>
            <Text style={[styles.personaRole, { color: theme.textMuted }]}>
              {persona?.relationship || 'companion'} · {persona?.voice_id || 'warm_female'}
            </Text>
            {persona?.slangs?.length > 0 && (
              <Text style={styles.personaSlangs}>"{persona.slangs[0]}"</Text>
            )}
          </View>
          <Ionicons name="chevron-forward" size={20} color={Colors.textMuted} />
        </TouchableOpacity>

        {/* AI Model */}
        <SectionHeader title="🧠 AI Model" />
        <View style={[styles.card, { backgroundColor: Colors.bgCard, borderColor: Colors.border }]}>
          <Text style={[styles.cardHint, { color: Colors.textMuted }]}>
            Choose which AI model powers your companion. Haiku is fastest, Sonnet is smarter.
          </Text>
          {MODELS.map(m => (
            <TouchableOpacity
              key={m.value}
              style={[styles.modelRow, { borderColor: Colors.border }, model === m.value && styles.modelRowActive]}
              onPress={() => setModel(m.value)}
            >
              <View style={styles.modelLeft}>
                <View style={[styles.modelDot, model === m.value && styles.modelDotActive]} />
                <View>
                  <Text style={[styles.modelName, { color: Colors.textMuted }, model === m.value && styles.modelNameActive]}>
                    {m.label}
                  </Text>
                  <Text style={[styles.modelProvider, { color: theme.textMuted }]}>{m.provider}</Text>
                </View>
              </View>
              {model === m.value && (
                <Ionicons name="checkmark-circle" size={20} color={Colors.accent} />
              )}
            </TouchableOpacity>
          ))}
        </View>

        {/* Background */}
        <SectionHeader title="🎨 Background" />
        <View style={[styles.card, { backgroundColor: Colors.bgCard, borderColor: Colors.border }]}>
          <View style={styles.bgGrid}>
            {BACKGROUNDS.map(bg => (
              <TouchableOpacity
                key={bg.id}
                style={[styles.bgSwatch, { backgroundColor: bg.color },
                  background === bg.id && styles.bgSwatchActive]}
                onPress={() => setBackground(bg.id)}
              >
                {background === bg.id && (
                  <Ionicons name="checkmark" size={18} color="#fff" />
                )}
                <Text style={styles.bgLabel}>{bg.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Pillar Weights */}
        <SectionHeader
          title="⚖️ Focus Areas"
          action={savingW ? undefined : "Reset"}
          onAction={resetWeights}
        />
        <View style={[styles.card, { backgroundColor: Colors.bgCard, borderColor: Colors.border }]}>
          <Text style={[styles.cardHint, { color: Colors.textMuted }]}>
            Control what Nancy pays most attention to. Higher = more focus.
          </Text>
          {loadingW ? (
            <ActivityIndicator color={Colors.accent} style={{ padding: Spacing.lg }} />
          ) : (
            CORE_PILLARS.map(pillar => (
              <WeightRow
                key={pillar.id}
                pillar={pillar}
                value={weights[pillar.id] || 1.0}
                onChange={(v) => saveWeight(pillar.id, v)}
              />
            ))
          )}
        </View>

        {/* Data & Privacy */}
        <SectionHeader title="🔒 Data & Privacy" />
        <View style={[styles.card, { backgroundColor: Colors.bgCard, borderColor: Colors.border }]}>
          <SettingRow
            icon="download-outline"
            label="Export my data"
            onPress={() => Alert.alert('Coming Soon', 'Data export will be available soon')}
          />
          <SettingRow
            icon="eye-off-outline"
            label="What Nancy knows about me"
            onPress={() => router.push('/profile')}
          />
          <SettingRow
            icon="trash-outline"
            label="Delete all my data"
            color={Colors.accentRed}
            onPress={() => Alert.alert(
              'Delete everything?',
              'This permanently removes all your conversations, memory, and profile. Cannot be undone.',
              [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Delete', style: 'destructive', onPress: () => {} }
              ]
            )}
          />
        </View>

        {/* Caregiver */}
        <SectionHeader title="👥 Caregiver" />
        <View style={[styles.card, { backgroundColor: Colors.bgCard, borderColor: Colors.border }]}>
          <SettingRow
            icon="people-outline"
            label="Caregiver dashboard"
            onPress={() => router.push('/caregiver/login')}
          />
          <SettingRow
            icon="notifications-outline"
            label="Alert preferences"
            onPress={() => Alert.alert('Coming Soon', 'Alert preferences coming soon')}
          />
        </View>

        {/* App info */}
        <View style={styles.appInfo}>
          <Text style={[styles.appInfoText, { color: Colors.textHint }]}>Nancy AI · Built with ❤️</Text>
          <Text style={[styles.appInfoText, { color: Colors.textHint }]}>Memory never forgets</Text>
        </View>

      </ScrollView>
    </SafeAreaView>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function SectionHeader({ title, action, onAction }: {
  title: string; action?: string; onAction?: () => void
}) {
  return (
    <View style={styles.sectionHeader}>
      <Text style={[styles.sectionTitle, { color: Colors.textMuted }]}>{title}</Text>
      {action && (
        <TouchableOpacity onPress={onAction}>
          <Text style={styles.sectionAction}>{action}</Text>
        </TouchableOpacity>
      )}
    </View>
  )
}

function SettingRow({ icon, label, onPress, color }: {
  icon: any; label: string; onPress: () => void; color?: string
}) {
  return (
    <TouchableOpacity style={[styles.settingRow, { borderBottomColor: Colors.border }]} onPress={onPress} activeOpacity={0.7}>
      <Ionicons name={icon} size={20} color={color || Colors.textMuted} />
      <Text style={[styles.settingLabel, color && { color }]}>{label}</Text>
      <Ionicons name="chevron-forward" size={16} color={Colors.textMuted} />
    </TouchableOpacity>
  )
}

function WeightRow({ pillar, value, onChange }: {
  pillar: { id: string; label: string; emoji: string; color: string }
  value:  number
  onChange: (v: number) => void
}) {
  const steps  = [0.1, 0.3, 0.5, 0.7, 1.0, 1.3, 1.5, 1.8, 2.0]
  const label  = value < 0.5 ? 'Low' : value < 1.2 ? 'Normal' : value < 1.6 ? 'High' : 'Max'
  const lcolor = value < 0.5 ? Colors.textMuted : value < 1.2 ? Colors.accentGreen : value < 1.6 ? Colors.accentWarm : Colors.accentRed

  return (
    <View style={styles.weightRow}>
      <Text style={styles.weightEmoji}>{pillar.emoji}</Text>
      <View style={{ flex: 1 }}>
        <View style={styles.weightLabelRow}>
          <Text style={[styles.weightLabel, { color: Colors.text }]}>{pillar.label}</Text>
          <Text style={[styles.weightValue, { color: lcolor }]}>{label}</Text>
        </View>
        <View style={styles.weightDots}>
          {steps.map(v => (
            <TouchableOpacity
              key={v}
              style={[styles.weightDot, { backgroundColor: Colors.bgInput },
                value >= v && { backgroundColor: pillar.color }]}
              onPress={() => onChange(v)}
            />
          ))}
        </View>
      </View>
    </View>
  )
}

// ── Styles ─────────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: Colors.bg },
  header: { padding: Spacing.lg, borderBottomWidth: 0.5, borderBottomColor: Colors.border },
  headerTitle: { ...Typography.heading, color: Colors.text },
  scroll: { padding: Spacing.lg, gap: Spacing.md, paddingBottom: 40 },

  sectionHeader: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginTop: Spacing.sm,
  },
  sectionTitle:  { ...Typography.label, color: Colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.8 },
  sectionAction: { ...Typography.caption, color: Colors.accent },

  card: {
    backgroundColor: Colors.bgCard, borderRadius: Radius.lg,
    padding: Spacing.lg, borderWidth: 0.5, borderColor: Colors.border,
    gap: Spacing.md,
  },
  cardHint: { ...Typography.caption, color: Colors.textMuted },

  // Persona
  personaCard: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
    backgroundColor: Colors.bgCard, borderRadius: Radius.lg,
    padding: Spacing.lg, borderWidth: 0.5, borderColor: Colors.border,
  },
  personaAvatar: {
    width: 48, height: 48, borderRadius: 24,
    backgroundColor: Colors.accent + '22', borderWidth: 1.5, borderColor: Colors.accent + '44',
    alignItems: 'center', justifyContent: 'center',
  },
  personaAvatarText: { fontSize: 20, fontWeight: '700', color: Colors.accent },
  personaName:       { ...Typography.heading, color: Colors.text },
  personaRole:       { ...Typography.caption, color: Colors.textMuted, marginTop: 2 },
  personaSlangs:     { ...Typography.caption, color: Colors.accent, fontStyle: 'italic', marginTop: 2 },

  // Model
  modelRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    padding: Spacing.md, borderRadius: Radius.md,
    borderWidth: 0.5, borderColor: Colors.border,
  },
  modelRowActive: { borderColor: Colors.accent, backgroundColor: Colors.accent + '10' },
  modelLeft:      { flexDirection: 'row', alignItems: 'center', gap: Spacing.md },
  modelDot:       { width: 10, height: 10, borderRadius: 5, backgroundColor: Colors.border },
  modelDotActive: { backgroundColor: Colors.accent },
  modelName:      { ...Typography.label, color: Colors.textMuted },
  modelNameActive:{ color: Colors.text, fontWeight: '600' },
  modelProvider:  { ...Typography.caption, color: Colors.textMuted },

  // Background
  bgGrid:       { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  bgSwatch: {
    width: '30%', aspectRatio: 1.5, borderRadius: Radius.md,
    alignItems: 'center', justifyContent: 'center', gap: 4,
    borderWidth: 2, borderColor: 'transparent',
  },
  bgSwatchActive: { borderColor: Colors.accent },
  bgLabel:        { ...Typography.caption, color: '#ffffff88', fontSize: 10 },

  // Weights
  weightRow:     { flexDirection: 'row', alignItems: 'center', gap: Spacing.md, paddingVertical: 4 },
  weightEmoji:   { fontSize: 20, width: 28 },
  weightLabelRow:{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  weightLabel:   { ...Typography.label, color: Colors.text },
  weightValue:   { ...Typography.caption, fontWeight: '600' },
  weightDots:    { flexDirection: 'row', gap: 4 },
  weightDot:     { flex: 1, height: 6, borderRadius: 3, backgroundColor: Colors.bgInput },

  // Settings rows
  settingRow: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
    paddingVertical: Spacing.sm,
    borderBottomWidth: 0.5, borderBottomColor: Colors.border,
  },
  settingLabel: { ...Typography.body, color: Colors.text, flex: 1 },

  appInfo:     { alignItems: 'center', paddingVertical: Spacing.xl, gap: 4 },
  appInfoText: { ...Typography.caption, color: Colors.textHint },
})

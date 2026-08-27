/**
 * ROUTINE — the anchor everything else is measured against.
 *
 * Two design decisions worth keeping:
 *
 * Everything is pre-filled. Tapping through six empty time pickers is what an
 * elderly user will not do, so the fast path is confirming plausible defaults
 * rather than entering anything. Existing values win over the defaults —
 * whatever a caregiver already entered in care_schedule shows up here rather
 * than being asked for twice.
 *
 * Skipping is easy and prominent. A form that traps someone on first launch is
 * worse than no form; anything left blank simply gets asked in conversation
 * later, and the companion is better at asking than a screen is.
 */
import React, { useEffect, useState } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  SafeAreaView, ScrollView, ActivityIndicator, Platform,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { router } from 'expo-router'
import { Colors, Spacing, Radius, API_BASE, API_KEY } from '../../constants'
import { useAppStore } from '../../store/appStore'
import { useT } from '../../hooks/useT'

type Routine = { label: string; at: string }

const DEFAULTS = {
  wake: '06:30', sleep: '22:00',
  breakfast: '08:30', lunch: '13:00', dinner: '19:30',
}

function hhmm(t?: string | null) {
  return t ? String(t).slice(0, 5) : ''
}

/** A plain HH:MM input.
 *
 * The native wheel picker would be better — typing "06:30" on a phone keyboard
 * is harder than spinning a dial, and that matters for the intended user. It
 * needs a native module and therefore a fresh dev build, which iOS cannot have
 * without a developer account; this works today and should be swapped when an
 * Android build happens anyway.
 */
function TimeField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <TextInput
      style={styles.time}
      value={value}
      onChangeText={t => {
        const digits = t.replace(/[^0-9]/g, "").slice(0, 4)
        onChange(digits.length > 2 ? `${digits.slice(0, 2)}:${digits.slice(2)}` : digits)
      }}
      placeholder="--:--"
      placeholderTextColor={Colors.textHint}
      keyboardType="number-pad"
      maxLength={5}
    />
  )
}

export default function RoutineScreen() {
  const { userId } = useAppStore()
  const t = useT()
  const [loading, setLoading] = useState(true)
  const [saving,  setSaving]  = useState(false)

  const [wake,   setWake]   = useState(DEFAULTS.wake)
  const [sleep,  setSleep]  = useState(DEFAULTS.sleep)
  const [meals,  setMeals]  = useState<Record<string, string>>({
    breakfast: DEFAULTS.breakfast, lunch: DEFAULTS.lunch, dinner: DEFAULTS.dinner,
  })
  const [routines, setRoutines] = useState<Routine[]>([{ label: '', at: '' }])

  // Pre-fill from what is already known. A caregiver may have entered all of
  // this already, and asking again is how a form starts feeling like paperwork.
  useEffect(() => {
    (async () => {
      try {
        const res  = await fetch(`${API_BASE}/care/patterns/${userId}`, {
          headers: { 'X-API-Key': API_KEY },
        })
        const data = await res.json()
        if (data?.wake?.declared_at)  setWake(hhmm(data.wake.declared_at))
        if (data?.sleep?.declared_at) setSleep(hhmm(data.sleep.declared_at))

        const m: Record<string, string> = { ...meals }
        for (const item of data?.meals || []) {
          if (item.label && item.declared_at) m[item.label] = hhmm(item.declared_at)
        }
        setMeals(m)

        const r = (data?.routines || [])
          .filter((x: any) => x.declared_at)
          .map((x: any) => ({ label: x.label_native || x.label || '', at: hhmm(x.declared_at) }))
        if (r.length) setRoutines([...r, { label: '', at: '' }])
      } catch (e) {
        console.log('[routine] prefill failed', e)
      }
      setLoading(false)
    })()
  }, [userId])

  const save = async () => {
    setSaving(true)
    try {
      await fetch(`${API_BASE}/care/patterns/${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body: JSON.stringify({
          wake, sleep, meals,
          // Blank rows are the "add another" affordance, not data.
          routines: routines.filter(r => r.label.trim() && r.at),
        }),
      })
    } catch (e) {
      console.log('[routine] save failed', e)
    }
    setSaving(false)
    router.push('/setup/interests')
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.safe, { justifyContent: 'center' }]}>
        <ActivityIndicator color={Colors.accent} />
      </SafeAreaView>
    )
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <Text style={styles.step}>{t('setup.step', { n: 2, total: 3 })}</Text>
        <Text style={styles.title}>{t('setup.routine.title')}</Text>
        <Text style={styles.sub}>
          {t('setup.routine.sub')}
        </Text>

        <View style={styles.card}>
          <View style={styles.row}>
            <Text style={styles.label}>{t('setup.routine.wake')}</Text>
            <TimeField value={wake} onChange={setWake} />
          </View>
          <View style={styles.divider} />
          <View style={styles.row}>
            <Text style={styles.label}>{t('setup.routine.sleep')}</Text>
            <TimeField value={sleep} onChange={setSleep} />
          </View>
        </View>

        <Text style={styles.section}>{t('setup.routine.meals')}</Text>
        <View style={styles.card}>
          {(['breakfast', 'lunch', 'dinner'] as const).map((key, i) => (
            <View key={key}>
              {i > 0 && <View style={styles.divider} />}
              <View style={styles.row}>
                <Text style={styles.label}>{t(`setup.routine.${key}`)}</Text>
                <TimeField
                  value={meals[key] || ''}
                  onChange={v => setMeals({ ...meals, [key]: v })}
                />
              </View>
            </View>
          ))}
        </View>

        <Text style={styles.section}>{t('setup.routine.daily')}</Text>
        <View style={styles.card}>
          {routines.map((r, i) => (
            <View key={i}>
              {i > 0 && <View style={styles.divider} />}
              <View style={styles.row}>
                <TextInput
                  style={styles.input}
                  value={r.label}
                  placeholder={t('setup.routine.example')}
                  placeholderTextColor={Colors.textHint}
                  onChangeText={v => {
                    const next = [...routines]
                    next[i] = { ...next[i], label: v }
                    setRoutines(next)
                  }}
                />
                <TimeField
                  value={r.at}
                  onChange={v => {
                    const next = [...routines]
                    next[i] = { ...next[i], at: v }
                    setRoutines(next)
                  }}
                />
              </View>
            </View>
          ))}
        </View>
        <TouchableOpacity
          style={styles.add}
          onPress={() => setRoutines([...routines, { label: '', at: '' }])}
        >
          <Ionicons name="add" size={18} color={Colors.accent} />
          <Text style={styles.addText}>{t('common.add')}</Text>
        </TouchableOpacity>

        <View style={styles.actions}>
          <TouchableOpacity
            style={styles.skip}
            onPress={() => router.push('/setup/interests')}
          >
            <Text style={styles.skipText}>{t('common.skip')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.btn, saving && { opacity: 0.6 }]}
            onPress={save}
            disabled={saving}
          >
            {saving
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.btnText}>{t('common.next')}</Text>}
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe:     { flex: 1, backgroundColor: Colors.bg },
  scroll:   { padding: Spacing.lg, paddingBottom: Spacing.xl },
  step:     { fontSize: 12, color: Colors.textMuted, marginBottom: 4 },
  title:    { fontSize: 24, color: Colors.text, fontWeight: '600' },
  sub:      { fontSize: 14, color: Colors.textSecond, marginTop: 6,
              marginBottom: Spacing.lg, lineHeight: 20 },
  section:  { fontSize: 13, color: Colors.textMuted, marginTop: Spacing.lg,
              marginBottom: 8 },
  card:     { backgroundColor: Colors.bgCard, borderRadius: Radius.md,
              borderWidth: 1, borderColor: Colors.border },
  row:      { flexDirection: 'row', alignItems: 'center',
              paddingVertical: 14, paddingHorizontal: 16 },
  divider:  { height: 1, backgroundColor: Colors.border, marginHorizontal: 16 },
  // 16px, not 14: this is read by someone who may not see well.
  label:    { flex: 1, fontSize: 16, color: Colors.text },
  input:    { flex: 1, fontSize: 16, color: Colors.text, padding: 0 },
  time:     { paddingHorizontal: 14, paddingVertical: 8, borderRadius: Radius.sm,
              backgroundColor: Colors.bgInput, minWidth: 86, fontSize: 17,
              color: Colors.text, textAlign: 'center' },
  add:      { flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
              paddingVertical: 12, marginTop: 8 },
  addText:  { fontSize: 14, color: Colors.accent, marginLeft: 6 },
  actions:  { flexDirection: 'row', gap: 10, marginTop: Spacing.lg },
  skip:     { flex: 1, height: 52, borderRadius: Radius.md,
              alignItems: 'center', justifyContent: 'center' },
  skipText: { fontSize: 15, color: Colors.textSecond },
  btn:      { flex: 2, height: 52, borderRadius: Radius.md,
              alignItems: 'center', justifyContent: 'center',
              backgroundColor: Colors.accent },
  btnText:  { fontSize: 16, color: '#fff', fontWeight: '600' },
})

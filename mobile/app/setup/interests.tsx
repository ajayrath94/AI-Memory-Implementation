/**
 * INTERESTS — the last setup screen.
 *
 * Categories rather than a blank box. "What do you enjoy?" asked cold gets
 * "nothing much" from someone with plenty to say; the same question under a
 * heading that says Music gets "Kishore Kumar, Lata". The headings come from
 * the string file, so they render in whatever language was chosen two screens
 * ago.
 *
 * Every field is optional and the skip is prominent. Anything left blank gets
 * asked in conversation later, and the companion is better at asking than a
 * form is — it can wait for the right moment and follow up on the answer.
 *
 * Voice matters more here than on the routine screen. Typing artist names on a
 * phone keyboard is exactly what the intended user will not do, and for someone
 * who reads Gurmukhi or Tamil it is worse still.
 */
import React, { useEffect, useState } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  SafeAreaView, ScrollView, ActivityIndicator,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { router } from 'expo-router'
import { Colors, Spacing, Radius, API_BASE, API_KEY } from '../../constants'
import { useAppStore } from '../../store/appStore'
import { useT } from '../../hooks/useT'
import { useVoice } from '../../hooks/useVoice'

// Keys the backend knows, paired with the string key that names them on screen.
// The backend never sees a translated name and the screen never sees a raw key.
const CATEGORIES = [
  { key: 'sangeet', label: 'setup.interests.music', icon: 'musical-notes-outline' },
  { key: 'khana',   label: 'setup.interests.food',  icon: 'restaurant-outline' },
  { key: 'dekhna',  label: 'setup.interests.watch', icon: 'tv-outline' },
  { key: 'bhakti',  label: 'setup.interests.faith', icon: 'flower-outline' },
  { key: 'shauk',   label: 'setup.interests.hobby', icon: 'leaf-outline' },
] as const

export default function InterestsScreen() {
  const { userId } = useAppStore()
  const t = useT()
  const [vals, setVals]       = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving]   = useState(false)
  // Which field the microphone is filling. useVoice hands back a transcript
  // through a callback rather than a promise, so the target has to be held
  // somewhere the callback can see — a ref, because a stale closure would
  // otherwise send every transcript to whichever field was active on mount.
  const target = React.useRef<string | null>(null)
  const [listening, setListening] = useState<string | null>(null)

  const voice = useVoice((text: string) => {
    console.log('[interests] transcript arrived:', JSON.stringify(text),
                'target:', target.current)
    const cat = target.current
    if (!cat || !text) return
    // Append rather than replace: naming a second thing should not lose the
    // first.
    setVals(v => ({ ...v, [cat]: [v[cat], text].filter(Boolean).join(', ') }))
    target.current = null
    setListening(null)
  })

  // Pre-fill anything already declared, so returning to this screen from
  // settings shows what is there rather than an empty form.
  useEffect(() => {
    (async () => {
      try {
        const res  = await fetch(`${API_BASE}/care/interests/${userId}`, {
          headers: { 'X-API-Key': API_KEY },
        })
        const data = await res.json()
        const next: Record<string, string> = {}
        for (const [cat, items] of Object.entries(data?.interests || {})) {
          if (Array.isArray(items) && items.length) next[cat] = items.join(', ')
        }
        setVals(next)
      } catch (e) {
        console.log('[interests] prefill failed', e)
      }
      setLoading(false)
    })()
  }, [userId])

  const speak = (cat: string) => {
    // Track the target off our own state, not voice.isListening — that is the
    // previous render's value and toggle() is async, so reading it here set the
    // ref from a stale flag and the transcript arrived with nowhere to go.
    console.log('[interests] mic', cat, 'listening:', listening,
                'voice.isListening:', voice.isListening)
    const stopping = listening === cat
    // Only set on the starting tap, never cleared here: the transcript arrives
    // AFTER the stopping tap, and clearing the target first left it with
    // nowhere to go. The callback clears it once it has written.
    if (!stopping) target.current = cat
    setListening(stopping ? null : cat)
    voice.toggle()
  }

  const save = async () => {
    setSaving(true)
    // Split on commas here rather than server-side: "Lata, Rafi" is two
    // interests, and each has to be canonicalised separately or it becomes one
    // cluster with a comma in its name.
    const interests: Record<string, string[]> = {}
    for (const [cat, text] of Object.entries(vals)) {
      const items = (text || '').split(',').map(s => s.trim()).filter(Boolean)
      if (items.length) interests[cat] = items
    }
    try {
      await fetch(`${API_BASE}/care/interests/${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body: JSON.stringify({ interests }),
      })
    } catch (e) {
      console.log('[interests] save failed', e)
    }
    setSaving(false)
    router.replace('/')
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
        <Text style={styles.step}>{t('setup.step', { n: 3, total: 3 })}</Text>
        <Text style={styles.title}>{t('setup.interests.title')}</Text>
        <Text style={styles.sub}>{t('setup.interests.sub')}</Text>

        {CATEGORIES.map(cat => (
          <View key={cat.key} style={styles.card}>
            <View style={styles.head}>
              <Ionicons name={cat.icon as any} size={18} color={Colors.textMuted} />
              <Text style={styles.label}>{t(cat.label)}</Text>
            </View>
            <View style={styles.inputRow}>
              <TextInput
                style={styles.input}
                value={vals[cat.key] || ''}
                onChangeText={v => setVals(s => ({ ...s, [cat.key]: v }))}
                placeholder="…"
                placeholderTextColor={Colors.textHint}
                multiline
              />
              <TouchableOpacity
                style={[styles.mic, listening === cat.key && styles.micOn]}
                onPress={() => speak(cat.key)}
              >
                <Ionicons
                  name={listening === cat.key && voice.isListening ? 'stop' : 'mic-outline'}
                  size={20}
                  color={listening === cat.key ? '#fff' : Colors.accent}
                />
              </TouchableOpacity>
            </View>
          </View>
        ))}

        <View style={styles.actions}>
          <TouchableOpacity style={styles.skip} onPress={() => router.replace('/')}>
            <Text style={styles.skipText}>{t('common.skip')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.btn, saving && { opacity: 0.6 }]}
            onPress={save}
            disabled={saving}
          >
            {saving
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.btnText}>{t('common.done')}</Text>}
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
  card:     { backgroundColor: Colors.bgCard, borderRadius: Radius.md,
              borderWidth: 1, borderColor: Colors.border,
              padding: 14, marginBottom: 10 },
  head:     { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  label:    { fontSize: 15, color: Colors.text, marginLeft: 8 },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end' },
  // 16px and multiline: names run long, and this is read by someone who may
  // not see well.
  input:    { flex: 1, fontSize: 16, color: Colors.text, padding: 0,
              minHeight: 24, maxHeight: 90 },
  mic:      { width: 40, height: 40, borderRadius: 20, marginLeft: 10,
              alignItems: 'center', justifyContent: 'center',
              backgroundColor: Colors.bgInput },
  micOn:    { backgroundColor: Colors.accentRed },
  actions:  { flexDirection: 'row', gap: 10, marginTop: Spacing.lg },
  skip:     { flex: 1, height: 52, borderRadius: Radius.md,
              alignItems: 'center', justifyContent: 'center' },
  skipText: { fontSize: 15, color: Colors.textSecond },
  btn:      { flex: 2, height: 52, borderRadius: Radius.md,
              alignItems: 'center', justifyContent: 'center',
              backgroundColor: Colors.accent },
  btnText:  { fontSize: 16, color: '#fff', fontWeight: '600' },
})

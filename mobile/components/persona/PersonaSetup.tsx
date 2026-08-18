import React, { useState, useEffect } from 'react'
import {
  View, Text, TextInput, TouchableOpacity, ScrollView,
  StyleSheet, SafeAreaView, ActivityIndicator, Alert,
  Switch,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { Colors, Typography, Spacing, Radius, API_BASE, API_KEY } from '../../constants'

// ── Types ──────────────────────────────────────────────────────────────────────
interface Persona {
  bot_name:     string
  relationship: string
  voice_id:     string
  voice_type:   string
  slangs:       string[]
  personality:  { warmth: number; humor: number }
  language_mix: Record<string, number>
}

const DEFAULT_PERSONA: Persona = {
  bot_name:     'Nancy',
  relationship: 'companion',
  voice_id:     'warm_female',
  voice_type:   'preset',
  slangs:       [],
  personality:  { warmth: 0.9, humor: 0.6 },
  language_mix: { hindi: 0.7, english: 0.3 },
}

const RELATIONSHIPS = [
  { id: 'son',       label: 'Beta',      emoji: '👦' },
  { id: 'daughter',  label: 'Beti',      emoji: '👧' },
  { id: 'friend',    label: 'Dost',      emoji: '🤝' },
  { id: 'companion', label: 'Saathi',    emoji: '💙' },
  { id: 'caretaker', label: 'Caretaker', emoji: '🏥' },
]

const VOICE_PRESETS = [
  { id: 'warm_female',   label: 'Warm Female',   desc: 'Caring, motherly',   emoji: '👩' },
  { id: 'friendly_male', label: 'Friendly Male',  desc: 'Warm, brotherly',    emoji: '👨' },
  { id: 'young_female',  label: 'Young Female',   desc: 'Energetic, cheerful', emoji: '👱‍♀️' },
  { id: 'elder_male',    label: 'Elder Male',     desc: 'Wise, grandfatherly', emoji: '👴' },
]

const SUGGESTED_SLANGS: Record<string, string[]> = {
  hindi:    ['arre yaar', 'kya baat hai', 'bilkul sahi', 'bas kar', 'wah wah'],
  gujarati: ['kem cho', 'maja ma', 'shu thayu', 'arre bhai'],
  punjabi:  ['kiddan', 'ki haal', 'chak de', 'sat sri akal'],
  marathi:  ['aho', 'kai zala', 'khup chan', 'arre baba'],
}

const LANGUAGES = ['hindi', 'english', 'tamil', 'telugu', 'kannada', 'malayalam', 'gujarati', 'bengali', 'punjabi', 'marathi', 'odia', 'urdu', 'arabic', 'spanish', 'german', 'french', 'chinese']

// ── Main Component ─────────────────────────────────────────────────────────────
interface Props {
  userId:      string
  caregiverId?: string
  onSaved?:   () => void
}

export default function PersonaSetup({ userId, caregiverId, onSaved }: Props) {
  const [persona,   setPersona]   = useState<Persona>(DEFAULT_PERSONA)
  const [loading,   setLoading]   = useState(true)
  const [saving,    setSaving]    = useState(false)
  const [newSlang,  setNewSlang]  = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)

  useEffect(() => { loadPersona() }, [userId])

  const loadPersona = async () => {
    try {
      const res  = await fetch(`${API_BASE}/persona/${userId}`, {
        headers: { 'X-API-Key': API_KEY }
      })
      const data = await res.json()
      if (data.persona) setPersona({ ...DEFAULT_PERSONA, ...data.persona })
    } catch (e) {
      console.error('Load persona failed:', e)
    } finally {
      setLoading(false)
    }
  }

  // The companion's name is reserved in the memory system — anything the user
  // says with that name is treated as being about the companion, not a person.
  // If they already have a relative with the same name, that relative stops
  // being recordable. Worth warning about, not worth blocking: naming a
  // companion after someone you miss is a reasonable thing to want.
  const findFamilyClash = async (name: string): Promise<string | null> => {
    try {
      const res  = await fetch(`${API_BASE}/memory/profile/${userId}`, {
        headers: { 'X-API-Key': API_KEY },
      })
      const data = await res.json()
      const fam  = data?.family || {}
      const all: string[] = []
      Object.values(fam).forEach((v: any) => {
        if (Array.isArray(v)) all.push(...v.filter((x: any) => typeof x === 'string'))
        else if (typeof v === 'string' && v) all.push(v)
      })
      const wanted = name.trim().toLowerCase()
      return all.find(m => m.trim().toLowerCase() === wanted) || null
    } catch (e) {
      return null   // never block saving on a failed check
    }
  }

  const save = async () => {
    if (!persona.bot_name.trim()) {
      Alert.alert('Name required', 'Please give your companion a name')
      return
    }

    const clash = await findFamilyClash(persona.bot_name)
    if (clash) {
      const proceed = await new Promise<boolean>(resolve => {
        Alert.alert(
          'That name is already in the family',
          `You have a family member called ${clash}. If your companion shares ` +
          `that name, mentions of ${clash} will be treated as the companion — ` +
          `so their details may not be remembered separately.`,
          [
            { text: 'Pick another', style: 'cancel', onPress: () => resolve(false) },
            { text: 'Use it anyway', onPress: () => resolve(true) },
          ]
        )
      })
      if (!proceed) return
    }

    setSaving(true)
    try {
      const res = await fetch(`${API_BASE}/persona/${userId}`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body:    JSON.stringify({ ...persona, caregiver_id: caregiverId }),
      })
      const data = await res.json()
      if (data.status === 'ok') {
        Alert.alert('Saved!', `${persona.bot_name} is ready to chat`, [
          { text: 'Great!', onPress: onSaved }
        ])
      }
    } catch (e) {
      Alert.alert('Error', 'Failed to save persona')
    } finally {
      setSaving(false)
    }
  }

  const addSlang = () => {
    if (!newSlang.trim()) return
    if (persona.slangs.includes(newSlang.trim())) return
    setPersona(p => ({ ...p, slangs: [...p.slangs, newSlang.trim()] }))
    setNewSlang('')
  }

  const removeSlang = (slang: string) => {
    setPersona(p => ({ ...p, slangs: p.slangs.filter(s => s !== slang) }))
  }

  const addSuggestedSlang = (slang: string) => {
    if (persona.slangs.includes(slang)) return
    setPersona(p => ({ ...p, slangs: [...p.slangs, slang] }))
  }

  const updateLanguage = (lang: string, value: number) => {
    setPersona(p => ({ ...p, language_mix: { ...p.language_mix, [lang]: value } }))
  }

  const removeLanguage = (lang: string) => {
    const mix = { ...persona.language_mix }
    delete mix[lang]
    setPersona(p => ({ ...p, language_mix: mix }))
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={Colors.accent} />
      </View>
    )
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Personalize Companion</Text>
        <Text style={styles.headerSub}>Make it feel like someone they know</Text>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >

        {/* Preview card */}
        <View style={styles.previewCard}>
          <View style={styles.previewAvatar}>
            <Text style={styles.previewAvatarText}>
              {persona.bot_name ? persona.bot_name[0].toUpperCase() : 'N'}
            </Text>
          </View>
          <View>
            <Text style={styles.previewName}>{persona.bot_name || 'Nancy'}</Text>
            <Text style={styles.previewRole}>
              {RELATIONSHIPS.find(r => r.id === persona.relationship)?.emoji}{' '}
              {RELATIONSHIPS.find(r => r.id === persona.relationship)?.label || 'Companion'}
            </Text>
            {persona.slangs.length > 0 && (
              <Text style={styles.previewSlangs}>
                "{persona.slangs[0]}" • "{persona.slangs[1] || '...'}"
              </Text>
            )}
          </View>
        </View>

        {/* Name */}
        <Section title="🏷 Name">
          <TextInput
            style={styles.input}
            value={persona.bot_name}
            onChangeText={v => setPersona(p => ({ ...p, bot_name: v }))}
            placeholder="e.g. Shubham, Priya, Nancy..."
            placeholderTextColor={Colors.textHint}
          />
        </Section>

        {/* Relationship */}
        <Section title="❤️ Relationship to user">
          <View style={styles.chipRow}>
            {RELATIONSHIPS.map(r => (
              <TouchableOpacity
                key={r.id}
                style={[styles.chip, persona.relationship === r.id && styles.chipActive]}
                onPress={() => setPersona(p => ({ ...p, relationship: r.id }))}
              >
                <Text style={styles.chipEmoji}>{r.emoji}</Text>
                <Text style={[styles.chipText, persona.relationship === r.id && styles.chipTextActive]}>
                  {r.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </Section>

        {/* Voice */}
        <Section title="🎙 Voice style">
          <View style={styles.voiceGrid}>
            {VOICE_PRESETS.map(v => (
              <TouchableOpacity
                key={v.id}
                style={[styles.voiceCard, persona.voice_id === v.id && styles.voiceCardActive]}
                onPress={() => setPersona(p => ({ ...p, voice_id: v.id, voice_type: 'preset' }))}
              >
                <Text style={styles.voiceEmoji}>{v.emoji}</Text>
                <Text style={[styles.voiceLabel, persona.voice_id === v.id && styles.voiceLabelActive]}>
                  {v.label}
                </Text>
                <Text style={styles.voiceDesc}>{v.desc}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Voice clone placeholder */}
          <TouchableOpacity style={styles.cloneBtn} onPress={() =>
            Alert.alert('Coming Soon', 'Record a 30-second voice sample to clone it for your companion')
          }>
            <Ionicons name="mic-outline" size={20} color={Colors.accent} />
            <View style={{ flex: 1 }}>
              <Text style={styles.cloneBtnText}>Record custom voice</Text>
              <Text style={styles.cloneBtnSub}>Clone a family member's voice (Coming soon)</Text>
            </View>
            <View style={styles.comingSoonBadge}>
              <Text style={styles.comingSoonText}>Soon</Text>
            </View>
          </TouchableOpacity>
        </Section>

        {/* Personality sliders */}
        <Section title="✨ Personality">
          <PersonalitySlider
            label="Warmth"
            emoji="🤗"
            value={persona.personality.warmth}
            onChange={v => setPersona(p => ({ ...p, personality: { ...p.personality, warmth: v } }))}
          />
          <PersonalitySlider
            label="Humor"
            emoji="😄"
            value={persona.personality.humor}
            onChange={v => setPersona(p => ({ ...p, personality: { ...p.personality, humor: v } }))}
          />
        </Section>

        {/* Slangs */}
        <Section title="💬 Catchphrases & Slangs">
          <Text style={styles.sectionHint}>
            Phrases this person naturally uses in conversation
          </Text>

          {/* Current slangs */}
          <View style={styles.slangList}>
            {persona.slangs.map((slang, i) => (
              <View key={i} style={styles.slangTag}>
                <Text style={styles.slangText}>"{slang}"</Text>
                <TouchableOpacity onPress={() => removeSlang(slang)}>
                  <Ionicons name="close" size={14} color={Colors.textMuted} />
                </TouchableOpacity>
              </View>
            ))}
          </View>

          {/* Add slang */}
          <View style={styles.addSlangRow}>
            <TextInput
              style={[styles.input, { flex: 1 }]}
              value={newSlang}
              onChangeText={setNewSlang}
              placeholder="Add a phrase..."
              placeholderTextColor={Colors.textHint}
              onSubmitEditing={addSlang}
            />
            <TouchableOpacity style={styles.addBtn} onPress={addSlang}>
              <Ionicons name="add" size={20} color="#fff" />
            </TouchableOpacity>
          </View>

          {/* Suggestions */}
          <TouchableOpacity
            style={styles.suggestBtn}
            onPress={() => setShowSuggestions(!showSuggestions)}
          >
            <Text style={styles.suggestBtnText}>
              {showSuggestions ? 'Hide' : 'Show'} suggestions by language
            </Text>
            <Ionicons
              name={showSuggestions ? 'chevron-up' : 'chevron-down'}
              size={16}
              color={Colors.accent}
            />
          </TouchableOpacity>

          {showSuggestions && (
            <View style={styles.suggestions}>
              {Object.entries(SUGGESTED_SLANGS).map(([lang, slangs]) => (
                <View key={lang} style={styles.suggestionGroup}>
                  <Text style={styles.suggestionLang}>{lang}</Text>
                  <View style={styles.chipRow}>
                    {slangs.map(slang => (
                      <TouchableOpacity
                        key={slang}
                        style={[
                          styles.suggestionChip,
                          persona.slangs.includes(slang) && styles.suggestionChipAdded
                        ]}
                        onPress={() => addSuggestedSlang(slang)}
                      >
                        <Text style={styles.suggestionChipText}>
                          {persona.slangs.includes(slang) ? '✓ ' : '+ '}{slang}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              ))}
            </View>
          )}
        </Section>

        {/* Language mix */}
        <Section title="🌐 Language mix">
          <Text style={styles.sectionHint}>How should they mix languages?</Text>
          {Object.entries(persona.language_mix).map(([lang, pct]) => (
            <View key={lang} style={styles.langRow}>
              <Text style={styles.langName}>{lang}</Text>
              <View style={styles.langSliderRow}>
                {[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0].map(v => (
                  <TouchableOpacity
                    key={v}
                    style={[styles.langDot, pct >= v && styles.langDotActive]}
                    onPress={() => updateLanguage(lang, v)}
                  />
                ))}
                <Text style={styles.langPct}>{Math.round(pct * 100)}%</Text>
              </View>
              <TouchableOpacity onPress={() => removeLanguage(lang)}>
                <Ionicons name="close" size={16} color={Colors.textMuted} />
              </TouchableOpacity>
            </View>
          ))}

          {/* Add language */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={styles.chipRow}>
              {LANGUAGES.filter(l => !persona.language_mix[l]).map(lang => (
                <TouchableOpacity
                  key={lang}
                  style={styles.chip}
                  onPress={() => updateLanguage(lang, 0.3)}
                >
                  <Text style={styles.chipText}>+ {lang}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>
        </Section>

        {/* Save button */}
        <TouchableOpacity
          style={[styles.saveBtn, saving && { opacity: 0.7 }]}
          onPress={save}
          disabled={saving}
        >
          {saving
            ? <ActivityIndicator color="#fff" />
            : <>
                <Ionicons name="checkmark-circle" size={22} color="#fff" />
                <Text style={styles.saveBtnText}>Save & Apply</Text>
              </>
          }
        </TouchableOpacity>

        {/* Reset */}
        <TouchableOpacity
          style={styles.resetBtn}
          onPress={() => {
            Alert.alert('Reset to Nancy?', 'This will remove all customizations', [
              { text: 'Cancel', style: 'cancel' },
              { text: 'Reset', style: 'destructive', onPress: async () => {
                await fetch(`${API_BASE}/persona/${userId}`, {
                  method: 'DELETE', headers: { 'X-API-Key': API_KEY }
                })
                setPersona(DEFAULT_PERSONA)
                onSaved?.()
              }}
            ])
          }}
        >
          <Text style={styles.resetBtnText}>Reset to default Nancy</Text>
        </TouchableOpacity>

      </ScrollView>
    </SafeAreaView>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  )
}

function PersonalitySlider({ label, emoji, value, onChange }: {
  label: string; emoji: string; value: number; onChange: (v: number) => void
}) {
  const steps = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
  return (
    <View style={styles.sliderRow}>
      <Text style={styles.sliderLabel}>{emoji} {label}</Text>
      <View style={styles.sliderDots}>
        {steps.map(v => (
          <TouchableOpacity
            key={v}
            style={[styles.sliderDot, value >= v && styles.sliderDotActive]}
            onPress={() => onChange(v)}
          />
        ))}
      </View>
      <Text style={styles.sliderValue}>{Math.round(value * 100)}%</Text>
    </View>
  )
}

// ── Styles ─────────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: Colors.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: { padding: Spacing.lg, borderBottomWidth: 0.5, borderBottomColor: Colors.border },
  headerTitle: { ...Typography.heading, color: Colors.text },
  headerSub:   { ...Typography.caption, color: Colors.textMuted, marginTop: 4 },
  scroll: { padding: Spacing.lg, gap: Spacing.lg },

  previewCard: {
    flexDirection:   'row',
    alignItems:      'center',
    gap:             Spacing.lg,
    backgroundColor: Colors.accent + '15',
    borderRadius:    Radius.xl,
    padding:         Spacing.lg,
    borderWidth:     0.5,
    borderColor:     Colors.accent + '40',
  },
  previewAvatar: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: Colors.accent,
    alignItems: 'center', justifyContent: 'center',
  },
  previewAvatarText: { fontSize: 24, fontWeight: '700', color: '#fff' },
  previewName:       { ...Typography.heading, color: Colors.text },
  previewRole:       { ...Typography.label, color: Colors.textMuted, marginTop: 2 },
  previewSlangs:     { ...Typography.caption, color: Colors.accent, marginTop: 4, fontStyle: 'italic' },

  section:      { gap: Spacing.md },
  sectionTitle: { ...Typography.label, color: Colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.8 },
  sectionHint:  { ...Typography.caption, color: Colors.textMuted },

  input: {
    backgroundColor: Colors.bgCard,
    color:           Colors.text,
    borderWidth:     0.5,
    borderColor:     Colors.border,
    borderRadius:    Radius.md,
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.md,
    fontSize:        16,
  },

  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm,
    borderRadius: Radius.full, borderWidth: 0.5, borderColor: Colors.border,
    backgroundColor: Colors.bgCard,
  },
  chipActive:     { backgroundColor: Colors.accent + '20', borderColor: Colors.accent },
  chipEmoji:      { fontSize: 16 },
  chipText:       { ...Typography.label, color: Colors.textMuted },
  chipTextActive: { color: Colors.accent },

  voiceGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  voiceCard: {
    width: '47%', padding: Spacing.md, borderRadius: Radius.lg,
    borderWidth: 0.5, borderColor: Colors.border, backgroundColor: Colors.bgCard,
    alignItems: 'center', gap: 4,
  },
  voiceCardActive: { borderColor: Colors.accent, backgroundColor: Colors.accent + '15' },
  voiceEmoji:      { fontSize: 24 },
  voiceLabel:      { ...Typography.label, color: Colors.textMuted, textAlign: 'center' },
  voiceLabelActive:{ color: Colors.accent },
  voiceDesc:       { ...Typography.caption, color: Colors.textMuted, textAlign: 'center' },

  cloneBtn: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.md,
    padding: Spacing.md, borderRadius: Radius.lg,
    borderWidth: 0.5, borderColor: Colors.accent + '40',
    backgroundColor: Colors.accent + '08',
  },
  cloneBtnText:    { ...Typography.label, color: Colors.accent },
  cloneBtnSub:     { ...Typography.caption, color: Colors.textMuted },
  comingSoonBadge: { backgroundColor: Colors.accentWarm + '30', borderRadius: Radius.full, paddingHorizontal: 8, paddingVertical: 3 },
  comingSoonText:  { ...Typography.caption, color: Colors.accentWarm, fontWeight: '600' },

  sliderRow:       { flexDirection: 'row', alignItems: 'center', gap: Spacing.md, paddingVertical: 4 },
  sliderLabel:     { ...Typography.label, color: Colors.text, width: 100 },
  sliderDots:      { flex: 1, flexDirection: 'row', gap: 4 },
  sliderDot:       { flex: 1, height: 8, borderRadius: 4, backgroundColor: Colors.bgInput },
  sliderDotActive: { backgroundColor: Colors.accent },
  sliderValue:     { ...Typography.caption, color: Colors.textMuted, width: 35, textAlign: 'right' },

  slangList:  { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },
  slangTag: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.xs,
    backgroundColor: Colors.accent + '15', borderRadius: Radius.full,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.xs,
    borderWidth: 0.5, borderColor: Colors.accent + '30',
  },
  slangText: { ...Typography.label, color: Colors.accent },
  addSlangRow: { flexDirection: 'row', gap: Spacing.sm },
  addBtn: {
    backgroundColor: Colors.accent, borderRadius: Radius.md,
    padding: Spacing.md, alignItems: 'center', justifyContent: 'center',
  },
  suggestBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingVertical: Spacing.sm,
  },
  suggestBtnText: { ...Typography.label, color: Colors.accent },
  suggestions:    { gap: Spacing.md },
  suggestionGroup:{ gap: Spacing.xs },
  suggestionLang: { ...Typography.caption, color: Colors.textMuted, textTransform: 'capitalize' },
  suggestionChip: {
    paddingHorizontal: Spacing.sm, paddingVertical: 4,
    borderRadius: Radius.full, borderWidth: 0.5, borderColor: Colors.border,
    backgroundColor: Colors.bgCard,
  },
  suggestionChipAdded: { borderColor: Colors.accentGreen, backgroundColor: Colors.accentGreen + '15' },
  suggestionChipText:  { ...Typography.caption, color: Colors.textMuted },

  langRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, paddingVertical: 4 },
  langName: { ...Typography.label, color: Colors.text, width: 80, textTransform: 'capitalize' },
  langSliderRow: { flex: 1, flexDirection: 'row', gap: 3, alignItems: 'center' },
  langDot: { flex: 1, height: 6, borderRadius: 3, backgroundColor: Colors.bgInput },
  langDotActive: { backgroundColor: Colors.accentGreen },
  langPct: { ...Typography.caption, color: Colors.textMuted, width: 32, textAlign: 'right' },

  saveBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm, backgroundColor: Colors.accent,
    borderRadius: Radius.lg, paddingVertical: Spacing.lg,
    marginTop: Spacing.sm,
  },
  saveBtnText: { ...Typography.heading, color: '#fff' },
  resetBtn:    { alignItems: 'center', paddingVertical: Spacing.md },
  resetBtnText:{ ...Typography.label, color: Colors.textMuted },
})

/**
 * LANGUAGE — the first thing asked, before anything else.
 *
 * Every screen after this one is written in whatever is chosen here, so it
 * cannot itself rely on being read. Each language appears in its own script
 * with the English name beside it: someone who cannot read Devanagari finds
 * their language by the Latin label, and someone who reads only Devanagari
 * finds it by the script. The only text at the top is the same phrase twice,
 * because an instruction sentence would have to be in a language they might
 * not read.
 *
 * The device locale is a poor default here. An elderly Gujarati speaker often
 * has an English-locale phone that a son set up, so the choice is asked rather
 * than assumed.
 */
import React, { useState } from 'react'
import {
  View, Text, TouchableOpacity, StyleSheet,
  SafeAreaView, ScrollView, ActivityIndicator,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { router } from 'expo-router'
import { Colors, Typography, Spacing, Radius, API_BASE, API_KEY } from '../../constants'
import { useAppStore } from '../../store/appStore'
import { setLanguage } from '../../hooks/useT'
import { Lang as AppLang } from '../../i18n/strings'

type Lang = {
  code:    string       // stored as language_pref, and read into a prompt
  native:  string       // in its own script
  english: string
}

// One row per language, one tap, no follow-up question.
//
// There used to be a toggle asking whether English words were acceptable —
// which requires someone to reason about code-mixing before they have seen the
// app. It is gone because register is no longer declared: the composer sees
// their recent messages and mirrors how they actually write, so someone who
// mixes gets mixing back without anyone asking.
//
// Hinglish keeps its own row even though Hindi would converge there anyway.
// It is a word people recognise as their language, and picking it says
// something Hindi-plus-drift does not.
const LANGUAGES: Lang[] = [
  { code: 'hinglish', native: 'Hinglish',  english: 'हिंदी + English' },
  { code: 'hindi',    native: 'हिन्दी',     english: 'Hindi' },
  { code: 'punjabi',  native: 'ਪੰਜਾਬੀ',     english: 'Punjabi' },
  { code: 'gujarati', native: 'ગુજરાતી',    english: 'Gujarati' },
  { code: 'marathi',  native: 'मराठी',      english: 'Marathi' },
  { code: 'bengali',  native: 'বাংলা',       english: 'Bengali' },
  { code: 'tamil',    native: 'தமிழ்',      english: 'Tamil' },
  { code: 'telugu',   native: 'తెలుగు',      english: 'Telugu' },
  { code: 'english',  native: 'English',   english: '' },
]

// What the composer puts in a sentence. Naming the script matters: "Punjabi
// mixed with English" came back as Hinglish, because an ambiguous instruction
// resolves toward whichever mixed register the model knows best.
const PREF: Record<string, string> = {
  hinglish: 'hinglish',
  hindi:    'Hindi, written in Devanagari',
  punjabi:  'Punjabi, written in Gurmukhi script',
  gujarati: 'Gujarati, written in the Gujarati script',
  marathi:  'Marathi, written in Devanagari',
  bengali:  'Bengali, written in the Bengali script',
  tamil:    'Tamil, written in the Tamil script',
  telugu:   'Telugu, written in the Telugu script',
  english:  'english',
}

export default function LanguageScreen() {
  const { userId } = useAppStore()
  const [selected, setSelected] = useState<Lang | null>(null)
  const [saving, setSaving]     = useState(false)

  const save = async () => {
    if (!selected) return
    setSaving(true)
    try {
      // Locally first: the next screen renders before any network call
      // returns, and it should already be in their language.
      await setLanguage(selected.code as AppLang)

      await fetch(`${API_BASE}/memory/profile/${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body: JSON.stringify({ language_pref: PREF[selected.code] || selected.code }),
      })
    } catch (e) {
      // Not worth blocking setup over. The companion falls back to Hinglish
      // and the choice can be made again from settings.
      console.log('[language] save failed', e)
    }
    setSaving(false)
    router.push('/setup/routine')
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.header}>
          <View style={styles.icon}>
            <Ionicons name="chatbubble-ellipses-outline" size={26} color={Colors.accent} />
          </View>
          <Text style={styles.prompt}>आपकी भाषा · Your language</Text>
        </View>

        {LANGUAGES.map(lang => {
          const on = selected?.code === lang.code
          return (
            <TouchableOpacity
              key={lang.code}
              style={[styles.row, on && styles.rowOn]}
              onPress={() => setSelected(lang)}
            >
              <Text style={[styles.native, on && styles.nativeOn]}>{lang.native}</Text>
              {!!lang.english && (
                <Text style={[styles.english, on && styles.englishOn]}>{lang.english}</Text>
              )}
            </TouchableOpacity>
          )
        })}

        <TouchableOpacity
          style={[styles.btn, (!selected || saving) && { opacity: 0.5 }]}
          onPress={save}
          disabled={!selected || saving}
        >
          {saving
            ? <ActivityIndicator color="#fff" />
            : <Ionicons name="arrow-forward" size={22} color="#fff" />}
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe:      { flex: 1, backgroundColor: Colors.bg },
  scroll:    { padding: Spacing.lg, paddingBottom: Spacing.xl },
  header:    { alignItems: 'center', marginBottom: Spacing.lg },
  icon:      { width: 52, height: 52, borderRadius: 26, marginBottom: Spacing.sm,
               alignItems: 'center', justifyContent: 'center',
               backgroundColor: Colors.bgCard },
  prompt:    { fontSize: 15, color: Colors.textMuted },

  row:       { flexDirection: 'row', alignItems: 'center',
               paddingVertical: 14, paddingHorizontal: 16,
               borderRadius: Radius.md, borderWidth: 1,
               borderColor: Colors.border, backgroundColor: Colors.bgCard,
               marginBottom: 8 },
  rowOn:     { borderColor: Colors.accent, backgroundColor: Colors.bgInput },
  // Deliberately large: this is read by someone who may not see well, and
  // scripts like Gurmukhi and Bengali need the height to stay legible.
  native:    { fontSize: 19, color: Colors.text, flex: 1 },
  nativeOn:  { color: Colors.accent },
  english:   { fontSize: 13, color: Colors.textMuted },
  englishOn: { color: Colors.accent },


  btn:       { marginTop: Spacing.lg, height: 52, borderRadius: Radius.md,
               alignItems: 'center', justifyContent: 'center',
               backgroundColor: Colors.accent },
})

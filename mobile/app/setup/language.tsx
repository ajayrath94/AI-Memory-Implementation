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
  SafeAreaView, ScrollView, ActivityIndicator, Switch,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { router } from 'expo-router'
import { Colors, Typography, Spacing, Radius, API_BASE, API_KEY } from '../../constants'
import { useAppStore } from '../../store/appStore'

type Lang = {
  code: string          // what the backend stores as language_pref
  native: string        // in its own script
  english: string
  mixLabel: string      // the code-mixing question, in that language
  mixHint: string
}

// Punjabi is included because it was asked for, and because it is the language
// where the microphone matters most — a large share of older Punjabi speakers
// read Shahmukhi or do not read the script at all.
const LANGUAGES: Lang[] = [
  { code: 'hindi',     native: 'हिन्दी',   english: 'Hindi',
    mixLabel: 'अंग्रेज़ी शब्द ठीक हैं',
    mixHint:  '"डॉक्टर", "टैबलेट" जैसे शब्द वैसे ही रहेंगे' },
  { code: 'punjabi',   native: 'ਪੰਜਾਬੀ',   english: 'Punjabi',
    mixLabel: 'ਅੰਗਰੇਜ਼ੀ ਸ਼ਬਦ ਠੀਕ ਹਨ',
    mixHint:  '"ਡਾਕਟਰ", "ਟੈਬਲੇਟ" ਵਰਗੇ ਸ਼ਬਦ ਉਵੇਂ ਹੀ ਰਹਿਣਗੇ' },
  { code: 'gujarati',  native: 'ગુજરાતી',  english: 'Gujarati',
    mixLabel: 'અંગ્રેજી શબ્દો ઠીક છે',
    mixHint:  '"ડૉક્ટર", "ટેબ્લેટ" જેવા શબ્દો એમ જ રહેશે' },
  { code: 'marathi',   native: 'मराठी',    english: 'Marathi',
    mixLabel: 'इंग्रजी शब्द ठीक आहेत',
    mixHint:  '"डॉक्टर", "टॅब्लेट" सारखे शब्द तसेच राहतील' },
  { code: 'bengali',   native: 'বাংলা',     english: 'Bengali',
    mixLabel: 'ইংরেজি শব্দ ঠিক আছে',
    mixHint:  '"ডাক্তার", "ট্যাবলেট" এমন শব্দ একই থাকবে' },
  { code: 'tamil',     native: 'தமிழ்',    english: 'Tamil',
    mixLabel: 'ஆங்கில வார்த்தைகள் சரி',
    mixHint:  '"டாக்டர்", "டேப்லெட்" போன்ற வார்த்தைகள் அப்படியே இருக்கும்' },
  { code: 'telugu',    native: 'తెలుగు',    english: 'Telugu',
    mixLabel: 'ఇంగ్లీష్ పదాలు సరే',
    mixHint:  '"డాక్టర్", "టాబ్లెట్" లాంటి పదాలు అలాగే ఉంటాయి' },
  { code: 'english',   native: 'English',  english: '',
    mixLabel: '', mixHint: '' },
]

export default function LanguageScreen() {
  const { userId } = useAppStore()
  const [selected, setSelected] = useState<Lang | null>(null)
  const [allowMix, setAllowMix] = useState(true)
  const [saving, setSaving]     = useState(false)

  const save = async () => {
    if (!selected) return
    setSaving(true)
    try {
      // language and register are different questions. Someone may want pure
      // Gujarati while their daughter's generation mixes freely, and storing
      // one value for both loses that.
      // The composer interpolates this into a sentence — "They speak
      // {pref}. Write in {pref}." — so it has to read as a language name.
      // "hindi-mixed" does not; "hinglish" does, and it is what all 81
      // existing profiles already say.
      const MIXED: Record<string, string> = {
        hindi:    'hinglish',
        // Naming the script matters. "Punjabi mixed with English" came out as
        // Hinglish — an ambiguous instruction resolves toward the mixed
        // register the model knows best. "Punjabi (Gurmukhi script)" does not
        // leave that room.
        punjabi:  'Punjabi, written in Gurmukhi script, with English words where natural',
        gujarati: 'Gujarati script, with English words where natural',
        marathi:  'Marathi in Devanagari, with English words where natural',
        bengali:  'Bengali script, with English words where natural',
        tamil:    'Tamil script, with English words where natural',
        telugu:   'Telugu script, with English words where natural',
      }
      const pref = selected.code === 'english'
        ? 'english'
        : (allowMix ? (MIXED[selected.code] || selected.code) : selected.code)

      await fetch(`${API_BASE}/memory/profile/${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body: JSON.stringify({ language_pref: pref }),
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

        {/* Asked in the language just chosen — a question about English words
            written in English would be self-defeating. */}
        {!!selected && !!selected.mixLabel && (
          <View style={styles.mixBox}>
            <View style={styles.mixRow}>
              <Text style={styles.mixLabel}>{selected.mixLabel}</Text>
              <Switch value={allowMix} onValueChange={setAllowMix} />
            </View>
            <Text style={styles.mixHint}>{selected.mixHint}</Text>
          </View>
        )}

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

  mixBox:    { marginTop: Spacing.md, padding: 14, borderRadius: Radius.md,
               backgroundColor: Colors.bgCard },
  mixRow:    { flexDirection: 'row', alignItems: 'center',
               justifyContent: 'space-between' },
  mixLabel:  { fontSize: 15, color: Colors.text, flex: 1, marginRight: 12 },
  mixHint:   { fontSize: 12, color: Colors.textMuted, marginTop: 6 },

  btn:       { marginTop: Spacing.lg, height: 52, borderRadius: Radius.md,
               alignItems: 'center', justifyContent: 'center',
               backgroundColor: Colors.accent },
})

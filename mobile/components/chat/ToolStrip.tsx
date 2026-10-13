import React from 'react'
import { ScrollView, TouchableOpacity, Text, StyleSheet, View } from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { useRouter } from 'expo-router'
import { Colors } from '../../constants'
import { useT } from '../../hooks/useT'

// What Nancy can do, as buttons above the text box.
//
// Every tool used to be reachable only by asking in words, which works if you
// know it is there. Someone who does not type much, or did not know Nancy can
// check the weather, never finds it. One tap sends the same words she would
// have said — so Nancy answers exactly as if she had typed them — or, for
// lists, opens the screen where they are.

type Tool = {
  id: string
  icon: string
  label: string          // translation key
  fallback: string       // shown when the key has no translation yet
  say?: string           // translation key for the message sent to Nancy
  sayFallback?: string
  open?: string          // a screen instead of a message
}

const TOOLS: Tool[] = [
  { id: 'lists',   icon: 'list-outline',          label: 'tools.lists',   fallback: 'Listein',   open: '/lists' },
  { id: 'weather', icon: 'partly-sunny-outline',  label: 'tools.weather', fallback: 'Mausam',
    say: 'tools.weather.say', sayFallback: 'Aaj mausam kaisa hai?' },
  { id: 'music',   icon: 'musical-notes-outline', label: 'tools.music',   fallback: 'Gaane',
    say: 'tools.music.say',   sayFallback: 'Koi achha gaana sunao' },
  { id: 'news',    icon: 'newspaper-outline',     label: 'tools.news',    fallback: 'Khabar',
    say: 'tools.news.say',    sayFallback: 'Aaj ki khabar kya hai?' },
  { id: 'food',    icon: 'restaurant-outline',    label: 'tools.food',    fallback: 'Khana',
    say: 'tools.food.say',    sayFallback: 'Aaj kya banaun?' },
  { id: 'places',  icon: 'location-outline',      label: 'tools.places',  fallback: 'Paas mein',
    say: 'tools.places.say',  sayFallback: 'Paas mein kya kya hai?' },
  { id: 'day',     icon: 'calendar-outline',      label: 'tools.day',     fallback: 'Aaj ka din',
    say: 'tools.day.say',     sayFallback: 'Aaj mere din mein kya hai?' },
]

export function ToolStrip({ onSend, disabled }: {
  onSend: (text: string) => void
  disabled?: boolean
}) {
  const router = useRouter()
  const t = useT()

  // A key with no translation yet comes back as itself.
  const tr = (key: string, fb: string) => {
    const s = t(key)
    return !s || s === key ? fb : s
  }

  const press = (tool: Tool) => {
    if (tool.open) { router.push(tool.open as any); return }
    // While Nancy is still answering, a second tap would send a second
    // message on top of the first.
    if (disabled) return
    onSend(tr(tool.say!, tool.sayFallback!))
  }

  return (
    <View style={styles.wrap}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.row}
        keyboardShouldPersistTaps="handled"
      >
        {TOOLS.map(tool => {
          const off = disabled && !tool.open
          return (
            <TouchableOpacity
              key={tool.id}
              style={[styles.chip, off && styles.chipOff]}
              onPress={() => press(tool)}
              activeOpacity={0.7}
              disabled={off}
              accessibilityRole="button"
              accessibilityLabel={tr(tool.label, tool.fallback)}
            >
              <Ionicons name={tool.icon as any} size={20} color={Colors.accent} />
              <Text style={styles.label}>{tr(tool.label, tool.fallback)}</Text>
            </TouchableOpacity>
          )
        })}
      </ScrollView>
    </View>
  )
}

const styles = StyleSheet.create({
  wrap: { paddingTop: 6, paddingBottom: 2 },
  row:  { paddingHorizontal: 12, gap: 8 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    minHeight: 44, paddingHorizontal: 14, borderRadius: 22,
    borderWidth: 1, borderColor: Colors.accent + '44',
    backgroundColor: Colors.accent + '14',
  },
  chipOff: { opacity: 0.45 },
  label: { fontSize: 15, fontWeight: '600', color: Colors.text },
})

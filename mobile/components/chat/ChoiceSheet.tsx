import React from 'react'
import { Modal, View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native'
import { Colors } from '../../constants'
import { Sheet, Choice, pick } from './shortcuts'

// A sheet of big tiles, from the bottom of the screen: what kind of news,
// what to look for nearby, which part of her day. Two tiles a row, each a
// picture and two words, so it can be read without glasses and tapped with a
// thumb. Tapping outside, or "Band karo", closes it.

const CLOSE = { en: 'Close', hl: 'Band karo', hi: 'बंद करो', pa: 'ਬੰਦ ਕਰੋ', gu: 'બંધ કરો', mr: 'बंद करा',
                bn: 'বন্ধ করুন', ta: 'மூடு', te: 'మూసేయండి' }

export function ChoiceSheet({ sheet, lang, onPick, onClose, busy }: {
  sheet: Sheet | null
  lang: string
  busy?: boolean          // Nancy is still answering: sentences wait
  onPick: (c: Choice) => void
  onClose: () => void
}) {
  if (!sheet) return null
  // India time, the way the calendar works it out (fixed +5:30).
  const hour = new Date(Date.now() + 330 * 60000).getUTCHours()
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <TouchableOpacity style={styles.dim} activeOpacity={1} onPress={onClose} />
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <Text style={styles.title}>{pick(sheet.title, lang)}</Text>
        <ScrollView contentContainerStyle={styles.grid}>
          {sheet.choices.map(c => {
            const now = !!c.now?.(hour)
            const label = pick(c.label, lang)
            const off = !!busy && !c.open
            return (
              <TouchableOpacity key={c.id} activeOpacity={0.75} disabled={off}
                style={[styles.tile, now && styles.tileNow, off && { opacity: 0.45 }]}
                onPress={() => onPick(c)}
                accessibilityRole="button" accessibilityLabel={label}>
                <Text style={styles.emoji}>{c.emoji}</Text>
                <Text style={styles.label} numberOfLines={2}>{label}</Text>
              </TouchableOpacity>
            )
          })}
        </ScrollView>
        <TouchableOpacity style={styles.close} onPress={onClose} accessibilityRole="button">
          <Text style={styles.closeText}>{pick(CLOSE, lang)}</Text>
        </TouchableOpacity>
      </View>
    </Modal>
  )
}

const styles = StyleSheet.create({
  dim:    { flex: 1, backgroundColor: '#00000088' },
  sheet:  { backgroundColor: Colors.bgCard, borderTopLeftRadius: 22, borderTopRightRadius: 22,
            paddingHorizontal: 16, paddingTop: 8, paddingBottom: 24, maxHeight: '75%',
            borderTopWidth: 0.5, borderColor: Colors.border },
  handle: { alignSelf: 'center', width: 44, height: 5, borderRadius: 3,
            backgroundColor: Colors.textMuted, marginBottom: 12 },
  title:  { fontSize: 20, fontWeight: '700', color: Colors.text, marginBottom: 14, marginLeft: 4 },
  grid:   { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 12 },
  tile:   { width: '48.5%', minHeight: 96, borderRadius: 16, paddingVertical: 14, paddingHorizontal: 10,
            alignItems: 'center', justifyContent: 'center', gap: 6,
            borderWidth: 1, borderColor: Colors.accent + '44', backgroundColor: Colors.accent + '14' },
  tileNow:{ borderColor: Colors.accent, borderWidth: 2, backgroundColor: Colors.accent + '26' },
  emoji:  { fontSize: 32 },
  label:  { fontSize: 17, fontWeight: '600', color: Colors.text, textAlign: 'center' },
  close:  { marginTop: 16, minHeight: 50, borderRadius: 14, alignItems: 'center', justifyContent: 'center',
            borderWidth: 1, borderColor: Colors.border },
  closeText: { fontSize: 17, fontWeight: '600', color: Colors.textSecond },
})

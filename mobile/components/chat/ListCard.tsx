import React, { useCallback, useEffect, useRef, useState } from 'react'
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { useRouter } from 'expo-router'
import { Colors, API_BASE, API_KEY } from '../../constants'
import { useAppStore } from '../../store/appStore'
import { CARD, pick } from '../../i18n/words'
import { speak, getPreference } from '../../services/voiceService'

// A list, live, inside the chat.
//
// Going through her Grocery list in a shop took 24 messages for 12 things
// (17 Oct): Nancy asked about each, she answered each. Now Nancy's reply
// carries this card. Every item has a big tick. In a shop, "Dukaan mein? Ek
// ek karke" highlights one item with Mil gaya / Baad mein under it; a tap
// ticks it (or leaves it), the next is highlighted and said aloud, and no
// message is added. At the end, what is left and what to do with the list.
//
// It reads the list itself (every few seconds while open), so an answer
// given in words — "haan mil gaya" — shows here too, and an old card scrolled
// back to shows the list as it is now.

interface Item { id: string; fields: Record<string, string>; done: boolean }
interface Detail {
  id: string; name: string; closed_at: string | null
  total: number; left: number; items: Item[]; cursor: string | null
}

const H = { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' }
const POLL_MS = 6000

export function ListCard({ listId }: { listId: string }) {
  const router = useRouter()
  const { userId } = useAppStore()
  const lang = useAppStore(s => s.language)
  const [d, setD] = useState<Detail | null>(null)
  const [missing, setMissing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [roundOver, setRoundOver] = useState(false)
  const [askClose, setAskClose] = useState(false)
  const voiceOn = useRef(true)

  useEffect(() => {
    getPreference(userId).then(p => { voiceOn.current = (p as any)?.playback !== 'off' }).catch(() => {})
  }, [userId])

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/lists/${userId}/${listId}`, { headers: H })
      if (r.status === 404) { setMissing(true); return }
      if (r.ok) setD(await r.json())
    } catch {}
  }, [userId, listId])

  useEffect(() => {
    load()
    const iv = setInterval(() => { if (!d?.closed_at) load() }, POLL_MS)
    return () => clearInterval(iv)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, d?.closed_at])

  const say = (text: string) => { if (voiceOn.current && text) speak(text, { userId }).catch(() => {}) }

  const step = async (action: 'start' | 'got' | 'skip' | 'stop') => {
    if (busy) return
    setBusy(true)
    try {
      const r = await fetch(`${API_BASE}/lists/${userId}/${listId}/walk`, {
        method: 'POST', headers: H, body: JSON.stringify({ action }),
      })
      const j = await r.json()
      if (action === 'start') { setRoundOver(false); setAskClose(false) }
      if (j?.item?.what) say(j.item.what)
      if (j?.done && action !== 'stop') setRoundOver(true)
      await load()
    } catch {} finally { setBusy(false) }
  }

  const toggle = async (it: Item) => {
    if (!d || d.closed_at) return
    setD({ ...d, items: d.items.map(x => x.id === it.id ? { ...x, done: !x.done } : x) })
    try {
      await fetch(`${API_BASE}/lists/${userId}/${listId}/items/${it.id}/tick`, {
        method: 'POST', headers: H, body: JSON.stringify({ done: !it.done }),
      })
    } catch {}
    load()
  }

  const close = async (keep: boolean) => {
    setBusy(true)
    try {
      await fetch(`${API_BASE}/lists/${userId}/${listId}/close`, {
        method: 'POST', headers: H, body: JSON.stringify({ keep }),
      })
    } catch {} finally { setBusy(false); setAskClose(false) }
    if (!keep) { setMissing(true); return }
    load()
  }

  if (missing) return <View style={styles.card}><Text style={styles.muted}>{pick(CARD.gone, lang)}</Text></View>
  if (!d) return <View style={styles.card}><ActivityIndicator color={Colors.accent} /></View>

  const closed = !!d.closed_at
  const items = d.items || []
  const doneN = items.filter(i => i.done).length
  const left = items.filter(i => !i.done)
  const here = d.cursor ? items.find(i => i.id === d.cursor) : undefined
  const walking = !!here && !closed
  const showEnd = !closed && !walking && items.length > 0 && (roundOver || left.length === 0)

  return (
    <View style={styles.card}>
      <View style={styles.head}>
        <Text style={styles.title} numberOfLines={1}>🛒 {d.name}</Text>
        <Text style={styles.count}>{pick(CARD.count, lang, { done: doneN, total: items.length })}</Text>
      </View>

      {items.map(it => {
        const now = walking && it.id === here?.id
        return (
          <TouchableOpacity key={it.id} activeOpacity={0.7} disabled={closed}
            onPress={() => toggle(it)}
            style={[styles.row, now && styles.rowNow]}
            accessibilityRole="checkbox" accessibilityState={{ checked: it.done }}>
            <Ionicons name={it.done ? 'checkmark-circle' : now ? 'arrow-forward-circle' : 'ellipse-outline'}
              size={28} color={it.done ? Colors.accentGreen : now ? Colors.accent : Colors.textMuted} />
            <Text style={[styles.what, it.done && styles.whatDone, now && styles.whatNow]} numberOfLines={2}>
              {it.fields?.what}
            </Text>
          </TouchableOpacity>
        )
      })}

      {walking && (
        <View style={styles.walk}>
          <Text style={styles.nowText}>{pick(CARD.now, lang, { what: here?.fields?.what || '' })}</Text>
          <View style={styles.btnRow}>
            <TouchableOpacity style={[styles.btn, styles.btnGot]} disabled={busy} onPress={() => step('got')}>
              <Text style={styles.btnText}>{pick(CARD.got, lang)}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.btn, styles.btnSkip]} disabled={busy} onPress={() => step('skip')}>
              <Text style={[styles.btnText, { color: Colors.text }]}>{pick(CARD.skip, lang)}</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity onPress={() => step('stop')} disabled={busy} style={styles.stop}>
            <Text style={styles.link}>{pick(CARD.stop, lang)}</Text>
          </TouchableOpacity>
        </View>
      )}

      {!closed && !walking && !showEnd && left.length > 0 && (
        <TouchableOpacity style={styles.startBtn} disabled={busy} onPress={() => step('start')}>
          <Text style={styles.startText}>{pick(CARD.start, lang)}</Text>
        </TouchableOpacity>
      )}

      {showEnd && (
        <View style={styles.end}>
          <Text style={styles.endText}>
            {left.length === 0 ? pick(CARD.allDone, lang)
              : pick(CARD.left, lang, { n: left.length, items: left.map(i => i.fields?.what).join(', ') })}
          </Text>
          {!askClose ? (
            <View style={styles.btnRow}>
              {left.length > 0 && (
                <TouchableOpacity style={[styles.btn, styles.btnSkip]} onPress={() => setRoundOver(false)}>
                  <Text style={[styles.btnText, { color: Colors.text }]}>{pick(CARD.later, lang)}</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity style={[styles.btn, styles.btnSkip]} onPress={() => setAskClose(true)}>
                <Text style={[styles.btnText, { color: Colors.text }]}>{pick(CARD.close, lang)}</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <View style={styles.btnRow}>
              <TouchableOpacity style={[styles.btn, styles.btnGot]} disabled={busy} onPress={() => close(true)}>
                <Text style={styles.btnText}>{pick(CARD.keepNext, lang)}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.btn, styles.btnDrop]} disabled={busy} onPress={() => close(false)}>
                <Text style={styles.btnText}>{pick(CARD.drop, lang)}</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}

      {closed && <Text style={styles.muted}>{pick(CARD.closed, lang)}</Text>}

      {!closed && left.length > 0 && (
        <TouchableOpacity onPress={() => router.push(`/lists?shops=1&id=${listId}` as any)} style={styles.where}>
          <Text style={styles.link}>{pick(CARD.where, lang)}</Text>
        </TouchableOpacity>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  card:     { marginTop: 10, borderRadius: 16, borderWidth: 1, borderColor: Colors.accent + '55',
              backgroundColor: Colors.bgInput, padding: 12, gap: 6 },
  head:     { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', gap: 8, marginBottom: 2 },
  title:    { flex: 1, fontSize: 17, fontWeight: '700', color: Colors.text },
  count:    { fontSize: 14, color: Colors.textSecond, fontVariant: ['tabular-nums'] },
  row:      { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 46, paddingHorizontal: 8,
              borderRadius: 10 },
  rowNow:   { backgroundColor: Colors.accent + '22', borderWidth: 1, borderColor: Colors.accent },
  what:     { flex: 1, fontSize: 17, color: Colors.text },
  whatDone: { color: Colors.textMuted, textDecorationLine: 'line-through' },
  whatNow:  { fontWeight: '700' },
  walk:     { marginTop: 6, gap: 8 },
  nowText:  { fontSize: 16, fontWeight: '700', color: Colors.accent },
  btnRow:   { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  btn:      { flexGrow: 1, flexBasis: 120, minHeight: 52, borderRadius: 12, alignItems: 'center', justifyContent: 'center',
              paddingHorizontal: 10 },
  btnGot:   { backgroundColor: Colors.accentGreen },
  btnSkip:  { borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgCard },
  btnDrop:  { backgroundColor: Colors.accentRed },
  btnText:  { fontSize: 16, fontWeight: '700', color: '#fff', textAlign: 'center' },
  stop:     { alignSelf: 'center', padding: 6 },
  link:     { fontSize: 15, fontWeight: '600', color: Colors.accent },
  startBtn: { marginTop: 6, minHeight: 50, borderRadius: 12, alignItems: 'center', justifyContent: 'center',
              backgroundColor: Colors.accent },
  startText:{ fontSize: 16, fontWeight: '700', color: '#fff' },
  end:      { marginTop: 6, gap: 8, padding: 10, borderRadius: 12, backgroundColor: Colors.accentGreen + '18' },
  endText:  { fontSize: 16, fontWeight: '600', color: Colors.text },
  where:    { alignSelf: 'flex-start', paddingVertical: 6 },
  muted:    { fontSize: 15, color: Colors.textMuted },
})

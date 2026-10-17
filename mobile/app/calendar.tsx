/**
 * MERI CALENDAR — her days, one at a time, and the months beyond.
 *
 *   day view    a slider of the next 14 days (a dot where something is
 *               planned); the chosen day in four parts — Subah, Dopahar,
 *               Shaam, Raat — her plans and her routine in order, and a
 *               "+ jodo" row in each part to add something there.
 *   sheet       one sheet to add or change a plan: what, which day, what
 *               time, what kind. Every plan is reminded — a heads-up that
 *               morning, about an hour before, just before — so there is
 *               no switch to forget.
 *   months      the 📅 button: month after month, back a year and on two
 *               more, a dot on each day with a plan; tap a day to open it.
 *
 * Everything saved goes through the same server path as Nancy's own
 * calendar tool (POST/PUT/DELETE /calendar), so the alerts are planned,
 * moved or cancelled there, and the phone then resyncs its alerts and tells
 * the server which it holds — one ring per alert.
 *
 * Times: the server sends UTC; shown in India time with a fixed +5:30
 * (Hermes has no time-zone data).
 */
import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import {
  View, Text, ScrollView, StyleSheet, SafeAreaView, TouchableOpacity,
  ActivityIndicator, RefreshControl, Modal, TextInput, Alert, FlatList,
  Platform, KeyboardAvoidingView,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { useLocalSearchParams } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import DateTimePicker from '@react-native-community/datetimepicker'
import { useTheme } from '../hooks/useTheme'
import { useT } from '../hooks/useT'
import { Colors, Typography, Spacing, Radius, API_BASE, API_KEY } from '../constants'
import { useAppStore } from '../store/appStore'
import { syncReminderNotifications } from '../services/notificationService'
import { CAL, pick, pickList, codeOf, WEEKDAY_SHORT, WEEKDAY_FULL, WEEKDAY_HEAD, MONTH_NAMES } from '../i18n/words'

// Every label here follows her language (i18n/words.ts).
const BOT = 'Nancy'

interface CalItem {
  kind:      string          // event | reminder | routine
  id:        string
  title:     string
  at:        string          // ISO timestamp (UTC)
  category?: string
  location?: string | null
  dose?:     string | null
  status?:   string | null
  reminder?: boolean
}

// ── category → color + icon ──────────────────────────────────────────────
const CATEGORY: Record<string, { color: string; icon: string }> = {
  medical:   { color: '#4a90d9', icon: 'medkit-outline' },
  social:    { color: '#3dba7a', icon: 'people-outline' },
  festival:  { color: '#e8875a', icon: 'star-outline' },
  routine:   { color: '#7a5ad9', icon: 'time-outline' },
  medication:{ color: '#7a5ad9', icon: 'medical-outline' },
  reminder:  { color: '#e8a23a', icon: 'notifications-outline' },
  personal:  { color: '#888888', icon: 'calendar-outline' },
}
const KINDS = [
  { key: 'medical',  emoji: '🩺', word: CAL.kDoctor },
  { key: 'social',   emoji: '👥', word: CAL.kSocial },
  { key: 'festival', emoji: '🪔', word: CAL.kFestival },
  { key: 'personal', emoji: '📅', word: CAL.kPersonal },
]
function catStyle(item: CalItem) {
  const key = (item.kind === 'reminder' ? 'reminder'
             : item.kind === 'routine'  ? (item.category || 'routine')
             : item.category || 'personal').toLowerCase()
  return CATEGORY[key] || CATEGORY.personal
}

// ── India time, by a fixed offset ────────────────────────────────────────
const IST = 5.5 * 60 * 60 * 1000
const DAY = 86400000
// Hinglish keeps English day and month names in headings, as before.
const days = (lang: string) => pickList(WEEKDAY_FULL, codeOf(lang) === 'hl' ? 'english' : lang)
const monthsOf = (lang: string) => pickList(MONTH_NAMES, codeOf(lang) === 'hl' ? 'english' : lang)
/** A short month: three letters in English and Hinglish, the whole name otherwise. */
const shortMonth = (lang: string, m: number) => {
  const name = monthsOf(lang)[m]
  return ['en', 'hl'].includes(codeOf(lang)) ? name.slice(0, 3) : name
}

/** A Date whose UTC getters read as India time. */
function ist(iso: string | number): Date {
  return new Date(new Date(iso).getTime() + IST)
}
const pad = (n: number) => String(n).padStart(2, '0')
function keyOf(d: Date): string {           // d from ist()
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`
}
const todayKey = () => keyOf(ist(Date.now()))
function addDays(key: string, n: number): string {
  return keyOf(new Date(Date.parse(`${key}T00:00:00Z`) + n * DAY))
}
/** Midnight of a day in India, as an ISO string the server reads. */
const midnight = (key: string) => `${key}T00:00:00+05:30`
function keyDate(key: string): Date { return new Date(Date.parse(`${key}T00:00:00Z`)) }

function timeText(iso: string): string {
  const d = ist(iso)
  if (isNaN(d.getTime())) return '—'
  let h = d.getUTCHours(); const m = d.getUTCMinutes()
  const ap = h >= 12 ? 'PM' : 'AM'; h = h % 12 || 12
  return `${h}:${pad(m)} ${ap}`
}
function dayTitle(key: string, lang: string): string {
  const d = keyDate(key)
  const s = `${days(lang)[d.getUTCDay()]}, ${d.getUTCDate()} ${monthsOf(lang)[d.getUTCMonth()]}`
  if (key === todayKey()) return `${pick(CAL.today, lang)} · ${s}`
  if (key === addDays(todayKey(), 1)) return `${pick(CAL.tomorrow, lang)} · ${s}`
  return s
}

// The four parts of her day, and the time a "+ jodo" in each starts at.
const PARTS = [
  { key: 'subah',   word: CAL.morning,   from: 0,  to: 12, start: 9 },
  { key: 'dopahar', word: CAL.afternoon, from: 12, to: 16, start: 14 },
  { key: 'shaam',   word: CAL.evening,   from: 16, to: 20, start: 17 },
  { key: 'raat',    word: CAL.night,     from: 20, to: 24, start: 20 },
]

// ── the sheet's draft ────────────────────────────────────────────────────
interface Draft {
  id?:       string           // set when changing an existing plan
  kind:      string           // event | reminder
  title:     string
  dayKey:    string
  hour:      number
  minute:    number
  category:  string
  heading:   string
}

export default function CalendarScreen() {
  const theme = useTheme()
  const t = useT()
  const { userId } = useAppStore()
  const lang = useAppStore(s => s.language)

  const [items, setItems]       = useState<Record<string, CalItem[]>>({})   // by day
  const [loading, setLoading]   = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [selected, setSelected] = useState<string>(todayKey())
  const [months, setMonths]     = useState(false)
  const [draft, setDraft]       = useState<Draft | null>(null)
  const [saving, setSaving]     = useState(false)

  const strip = useMemo(() => Array.from({ length: 14 }, (_, i) => addDays(todayKey(), i)), [])

  // "Kuch jodo" on the Aaj ka din sheet opens this screen with ?add=1: the
  // add sheet straight away, for today, at the next hour.
  const { add } = useLocalSearchParams<{ add?: string }>()
  const added = useRef(false)
  useEffect(() => {
    if (add !== '1' || added.current) return
    added.current = true
    const h = Math.min(23, new Date(Date.now() + 330 * 60000).getUTCHours() + 1)
    setDraft({
      kind: 'event', title: '', dayKey: todayKey(), hour: h, minute: 0,
      category: 'personal', heading: pick(CAL.addHead, lang),
    })
  }, [add])

  // One read of a span of days: her plans and her routine, grouped by day.
  const load = useCallback(async (fromKey: string, days: number) => {
    try {
      const url = `${API_BASE}/calendar/${userId}?start=${encodeURIComponent(midnight(fromKey))}` +
                  `&days=${days}&routine_days=${days}`
      const res = await fetch(url, { headers: { 'X-API-Key': API_KEY } })
      const json = await res.json()
      const by: Record<string, CalItem[]> = {}
      for (let i = 0; i < days; i++) by[addDays(fromKey, i)] = []
      for (const it of (json?.items || []) as CalItem[]) {
        const d = ist(it.at)
        if (isNaN(d.getTime())) continue          // never a "NaN" day
        const k = keyOf(d)
        if (by[k]) by[k].push(it)
      }
      setItems(prev => ({ ...prev, ...by }))
    } catch (err) {
      console.error('Failed to fetch calendar:', err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [userId])

  const reload = useCallback(() => {
    load(todayKey(), 14)
    if (!strip.includes(selected)) load(selected, 1)
  }, [load, selected, strip])

  useEffect(() => {
    reload()
    const iv = setInterval(reload, 60000)
    return () => clearInterval(iv)
  }, [reload])

  const openDay = (key: string) => {
    setSelected(key)
    setMonths(false)
    if (!items[key]) load(key, 1)
  }

  // ── sheet ──────────────────────────────────────────────────────────────
  const newIn = (part: typeof PARTS[number]) => setDraft({
    kind: 'event', title: '', dayKey: selected, hour: part.start, minute: 0,
    category: 'personal', heading: pick(CAL.partHead, lang, { part: pick(part.word, lang) }),
  })
  const edit = (it: CalItem) => {
    const d = ist(it.at)
    setDraft({
      id: it.id, kind: it.kind, title: it.title || '', dayKey: keyOf(d),
      hour: d.getUTCHours(), minute: d.getUTCMinutes(),
      category: it.category && CATEGORY[it.category] ? it.category : 'personal',
      heading: it.kind === 'reminder' ? pick(CAL.reminderHead, lang, { bot: BOT }) : pick(CAL.changeHead, lang),
    })
  }

  const after = async (key: string) => {
    setDraft(null)
    await load(todayKey(), 14)
    if (!strip.includes(key)) await load(key, 1)
    // The phone's alerts follow the server: added, moved or gone.
    syncReminderNotifications(userId, API_BASE, API_KEY).catch(e => console.error('[notif]', e))
  }

  const save = async () => {
    if (!draft) return
    const title = draft.title.trim()
    if (!title) { Alert.alert(pick(CAL.whatQ, lang), pick(CAL.whatBody, lang)); return }
    const at = `${draft.dayKey}T${pad(draft.hour)}:${pad(draft.minute)}:00+05:30`
    if (Date.parse(at) < Date.now() - 60000) {
      Alert.alert(pick(CAL.pastQ, lang), pick(CAL.pastBody, lang)); return
    }
    setSaving(true)
    try {
      const headers = { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' }
      const res = draft.id
        ? await fetch(`${API_BASE}/calendar/${draft.id}`, {
            method: 'PUT', headers,
            body: JSON.stringify({ title, event_at: at, category: draft.category }),
          })
        : await fetch(`${API_BASE}/calendar`, {
            method: 'POST', headers,
            body: JSON.stringify({ user_id: userId, title, event_at: at,
                                   category: draft.category, created_by: 'elder',
                                   reminder_enabled: true }),
          })
      const json = await res.json()
      if (!res.ok) throw new Error(json?.detail || 'save failed')
      if (json?.status === 'already there') {
        Alert.alert(pick(CAL.thereQ, lang), pick(CAL.thereBody, lang, { title: json?.event?.title || title }))
      }
      await after(draft.dayKey)
    } catch (e: any) {
      Alert.alert(pick(CAL.failQ, lang), pick(CAL.failBody, lang))
      console.error('[calendar] save', e)
    } finally {
      setSaving(false)
    }
  }

  const remove = () => {
    if (!draft?.id) return
    Alert.alert(pick(CAL.removeQ, lang), pick(CAL.removeBody, lang, { title: draft.title }), [
      { text: pick(CAL.keep, lang), style: 'cancel' },
      { text: pick(CAL.remove, lang), style: 'destructive', onPress: async () => {
          try {
            const url = draft.kind === 'reminder'
              ? `${API_BASE}/reminders/${draft.id}/cancel`
              : `${API_BASE}/calendar/${draft.id}`
            await fetch(url, { method: draft.kind === 'reminder' ? 'POST' : 'DELETE',
                               headers: { 'X-API-Key': API_KEY } })
            await after(draft.dayKey)
          } catch (e) { console.error('[calendar] delete', e) }
        } },
    ])
  }

  // ── day view ───────────────────────────────────────────────────────────
  const dayItems = items[selected] || []
  const hasPlans = (k: string) => (items[k] || []).some(i => i.kind !== 'routine')

  const renderDay = () => (
    <>
      {PARTS.map(part => {
        const inPart = dayItems.filter(it => {
          const h = ist(it.at).getUTCHours()
          return h >= part.from && h < part.to
        }).sort((a, b) => a.at.localeCompare(b.at))
        return (
          <View key={part.key} style={styles.part}>
            <Text style={[styles.partLabel, { color: theme.textMuted }]}>{pick(part.word, lang)}</Text>
            {inPart.map(it => it.kind === 'routine' ? (
              <View key={`r-${it.id}-${it.at}`} style={styles.routineRow}>
                <Text style={[styles.routineTime, { color: catStyle(it).color }]}>{timeText(it.at)}</Text>
                <Text style={[styles.routineTitle, { color: theme.textSecond }]}>
                  {it.title}{it.dose ? <Text style={{ color: theme.textMuted }}>{`  ·  ${it.dose}`}</Text> : null}
                </Text>
              </View>
            ) : (
              <TouchableOpacity key={`${it.kind}-${it.id}`} activeOpacity={0.7} onPress={() => edit(it)}
                style={[styles.card, { backgroundColor: theme.bgCard, borderColor: theme.border }]}>
                <View style={[styles.stripe, { backgroundColor: catStyle(it).color }]} />
                <Text style={[styles.cardTime, { color: catStyle(it).color }]}>{timeText(it.at)}</Text>
                <View style={styles.cardBody}>
                  <Text style={[styles.cardTitle, { color: theme.text }]}>{it.title}</Text>
                  {it.location ? <Text style={[styles.meta, { color: theme.textMuted }]}>📍 {it.location}</Text> : null}
                  <View style={styles.bellRow}>
                    <Ionicons name="notifications-outline" size={14} color={CATEGORY.reminder.color} />
                    <Text style={[styles.meta, { color: CATEGORY.reminder.color, marginTop: 0, marginLeft: 4 }]}>
                      {pick(CAL.remindTag, lang)}
                    </Text>
                  </View>
                </View>
                <Ionicons name="create-outline" size={20} color={theme.textMuted} />
              </TouchableOpacity>
            ))}
            <TouchableOpacity activeOpacity={0.7} onPress={() => newIn(part)}
              style={[styles.addRow, { borderColor: Colors.accent + '55' }]}>
              <Text style={styles.addText}>{pick(CAL.addRow, lang, { part: pick(part.word, lang) })}</Text>
            </TouchableOpacity>
          </View>
        )
      })}
    </>
  )

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: theme.bg }]}>
      <StatusBar style="light" />

      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={[styles.title, { color: theme.text }]}>{t('calendar.title')}</Text>
          <Text style={[styles.subtitle, { color: theme.textMuted }]}>{dayTitle(selected, lang)}</Text>
        </View>
        <TouchableOpacity onPress={() => setMonths(true)} activeOpacity={0.7}
          style={[styles.headerIcon, { backgroundColor: Colors.accent + '22', borderColor: Colors.accent }]}>
          <Ionicons name="calendar" size={24} color={Colors.accent} />
        </TouchableOpacity>
      </View>

      {/* The next two weeks */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.strip}>
        {strip.map((k, i) => {
          const on = k === selected
          const d = keyDate(k)
          const label = i === 0 ? pick(CAL.today, lang) : i === 1 ? pick(CAL.tomorrow, lang)
                      : pickList(WEEKDAY_SHORT, lang)[d.getUTCDay()]
          return (
            <TouchableOpacity key={k} activeOpacity={0.7} onPress={() => openDay(k)}
              style={[styles.chip, { backgroundColor: on ? Colors.accent : theme.bgCard,
                                     borderColor: on ? Colors.accent : theme.border }]}>
              <Text style={[styles.chipDay, { color: on ? '#fff' : theme.textMuted }]}>{label.toUpperCase()}</Text>
              <Text style={[styles.chipNum, { color: on ? '#fff' : theme.text }]}>{d.getUTCDate()}</Text>
              <View style={[styles.chipDot, { backgroundColor: hasPlans(k) ? (on ? '#fff' : CATEGORY.festival.color) : 'transparent' }]} />
            </TouchableOpacity>
          )
        })}
      </ScrollView>

      {loading ? (
        <View style={styles.center}><ActivityIndicator size="large" color={Colors.accent} /></View>
      ) : (
        <ScrollView contentContainerStyle={styles.scroll}
          refreshControl={<RefreshControl refreshing={refreshing}
            onRefresh={() => { setRefreshing(true); reload() }} tintColor={Colors.accent} />}>
          {renderDay()}
          <View style={{ height: 40 }} />
        </ScrollView>
      )}

      <MonthView visible={months} onClose={() => setMonths(false)} onPick={openDay}
                 userId={userId} selected={selected} theme={theme} />

      <PlanSheet draft={draft} setDraft={setDraft} onSave={save} onDelete={remove}
                 saving={saving} theme={theme} />
    </SafeAreaView>
  )
}

// ── the add / change sheet ───────────────────────────────────────────────
function PlanSheet({ draft, setDraft, onSave, onDelete, saving, theme }: {
  draft: Draft | null; setDraft: (d: Draft | null) => void
  onSave: () => void; onDelete: () => void; saving: boolean; theme: any
}) {
  const lang = useAppStore(s => s.language)
  const [picker, setPicker] = useState<'date' | 'time' | null>(null)
  if (!draft) return null
  const fromReminder = draft.kind === 'reminder'
  const pickerValue = new Date(Date.parse(`${draft.dayKey}T${pad(draft.hour)}:${pad(draft.minute)}:00+05:30`))
  const d = keyDate(draft.dayKey)
  const h12 = draft.hour % 12 || 12

  return (
    <Modal visible transparent animationType="slide" onRequestClose={() => setDraft(null)}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <TouchableOpacity style={styles.dim} activeOpacity={1} onPress={() => setDraft(null)} />
        <View style={[styles.sheet, { backgroundColor: theme.bgCard, borderColor: theme.border }]}>
          <View style={styles.grab} />
          <Text style={[styles.sheetTitle, { color: theme.text }]}>{draft.heading}</Text>

          <Text style={[styles.lbl, { color: theme.textMuted }]}>{pick(CAL.whatLbl, lang)}</Text>
          <TextInput value={draft.title} editable={!fromReminder}
            onChangeText={v => setDraft({ ...draft, title: v })}
            placeholder={pick(CAL.example, lang)}
            placeholderTextColor={theme.textHint}
            style={[styles.input, { color: theme.text, backgroundColor: theme.bgInput, borderColor: theme.border }]} />

          <Text style={[styles.lbl, { color: theme.textMuted }]}>{pick(CAL.whenLbl, lang)}</Text>
          <View style={styles.row}>
            <TouchableOpacity disabled={fromReminder} onPress={() => setPicker('date')}
              style={[styles.big, { backgroundColor: theme.bgInput, borderColor: theme.border }]}>
              <Text style={[styles.bigText, { color: theme.text }]}>
                {`${pickList(WEEKDAY_SHORT, codeOf(lang) === 'hl' ? 'english' : lang)[d.getUTCDay()]}, ${d.getUTCDate()} ${shortMonth(lang, d.getUTCMonth())}`}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity disabled={fromReminder} onPress={() => setPicker('time')}
              style={[styles.big, { backgroundColor: theme.bgInput, borderColor: theme.border }]}>
              <Text style={[styles.bigText, { color: theme.text }]}>
                {`${h12}:${pad(draft.minute)} ${draft.hour >= 12 ? 'PM' : 'AM'}`}
              </Text>
            </TouchableOpacity>
          </View>

          {!fromReminder ? (
            <>
              <Text style={[styles.lbl, { color: theme.textMuted }]}>{pick(CAL.kindLbl, lang)}</Text>
              <View style={styles.kinds}>
                {KINDS.map(k => {
                  const on = draft.category === k.key
                  return (
                    <TouchableOpacity key={k.key} onPress={() => setDraft({ ...draft, category: k.key })}
                      style={[styles.kind, { borderColor: on ? Colors.accent : theme.border,
                                             backgroundColor: on ? Colors.accent + '22' : 'transparent' }]}>
                      <Text style={{ color: on ? theme.text : theme.textSecond, fontSize: 15 }}>{`${k.emoji} ${pick(k.word, lang)}`}</Text>
                    </TouchableOpacity>
                  )
                })}
              </View>
              <Text style={[styles.note, { color: theme.textMuted }]}>
                {pick(CAL.note, lang, { bot: BOT })}
              </Text>
              <TouchableOpacity onPress={onSave} disabled={saving} activeOpacity={0.8} style={styles.save}>
                {saving ? <ActivityIndicator color="#fff" />
                        : <Text style={styles.saveText}>{pick(draft.id ? CAL.saveChange : CAL.saveNew, lang)}</Text>}
              </TouchableOpacity>
            </>
          ) : (
            <Text style={[styles.note, { color: theme.textMuted }]}>
              {pick(CAL.fromChat, lang, { bot: BOT })}
            </Text>
          )}
          {draft.id ? (
            <TouchableOpacity onPress={onDelete} style={styles.del}>
              <Text style={styles.delText}>{pick(CAL.remove, lang)}</Text>
            </TouchableOpacity>
          ) : null}

          {picker ? (
            <DateTimePicker value={pickerValue} mode={picker} is24Hour={false}
              minimumDate={picker === 'date' ? new Date() : undefined}
              onChange={(e: any, v?: Date) => {
                setPicker(null)
                if (e?.type !== 'set' || !v) return
                const x = ist(v.getTime())
                setDraft(picker === 'date'
                  ? { ...draft, dayKey: keyOf(x) }
                  : { ...draft, hour: x.getUTCHours(), minute: x.getUTCMinutes() })
              }} />
          ) : null}
        </View>
      </KeyboardAvoidingView>
    </Modal>
  )
}

// ── months, a year back and two on ───────────────────────────────────────
function MonthView({ visible, onClose, onPick, userId, selected, theme }: {
  visible: boolean; onClose: () => void; onPick: (k: string) => void
  userId: string; selected: string; theme: any
}) {
  const lang = useAppStore(s => s.language)
  const now = keyDate(todayKey())
  const list = useMemo(() => {
    const out: { y: number; m: number }[] = []
    for (let i = -12; i <= 24; i++) {
      const t = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + i, 1))
      out.push({ y: t.getUTCFullYear(), m: t.getUTCMonth() })
    }
    return out
  }, [visible])
  const ref = useRef<FlatList>(null)
  const ITEM = 400
  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={[styles.safe, { backgroundColor: theme.bg }]}>
        <View style={styles.monthHeader}>
          <Text style={[styles.title, { color: theme.text, fontSize: 24 }]}>{pick(CAL.months, lang)}</Text>
          <View style={{ flexDirection: 'row', gap: 18, alignItems: 'center' }}>
            <TouchableOpacity onPress={() => onPick(todayKey())}>
              <Text style={styles.link}>{pick(CAL.goToday, lang)}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={28} color={theme.text} />
            </TouchableOpacity>
          </View>
        </View>
        <FlatList ref={ref} data={list} keyExtractor={i => `${i.y}-${i.m}`}
          initialScrollIndex={12}
          getItemLayout={(_, i) => ({ length: ITEM, offset: ITEM * i, index: i })}
          renderItem={({ item }) => (
            <MonthGrid y={item.y} m={item.m} userId={userId} selected={selected}
                       onPick={onPick} theme={theme} height={ITEM} />
          )} />
      </SafeAreaView>
    </Modal>
  )
}

function MonthGrid({ y, m, userId, selected, onPick, theme, height }: {
  y: number; m: number; userId: string; selected: string
  onPick: (k: string) => void; theme: any; height: number
}) {
  const lang = useAppStore(s => s.language)
  const [dots, setDots] = useState<Record<string, number>>({})
  const first = `${y}-${pad(m + 1)}-01`
  const daysIn = new Date(Date.UTC(y, m + 1, 0)).getUTCDate()
  const lead = keyDate(first).getUTCDay()
  const today = todayKey()

  useEffect(() => {
    let live = true
    fetch(`${API_BASE}/calendar/${userId}/days?start=${first}&days=${daysIn}`,
          { headers: { 'X-API-Key': API_KEY } })
      .then(r => r.json()).then(j => { if (live) setDots(j?.days || {}) })
      .catch(() => {})
    return () => { live = false }
  }, [first, userId])

  const cells: (string | null)[] = []
  for (let i = 0; i < lead; i++) cells.push(null)
  for (let dd = 1; dd <= daysIn; dd++) cells.push(`${y}-${pad(m + 1)}-${pad(dd)}`)
  while (cells.length % 7) cells.push(null)

  return (
    <View style={{ height, paddingHorizontal: Spacing.lg }}>
      <Text style={[styles.monthName, { color: theme.textSecond }]}>{`${monthsOf(lang)[m]} ${y}`}</Text>
      <View style={styles.weekRow}>
        {pickList(WEEKDAY_HEAD, lang).map((w, i) => (
          <Text key={i} style={[styles.weekDay, { color: theme.textMuted }]}>{w}</Text>
        ))}
      </View>
      <View style={styles.grid}>
        {cells.map((k, i) => k ? (
          <TouchableOpacity key={k} onPress={() => onPick(k)} activeOpacity={0.7}
            style={[styles.cell, k === today && { borderColor: Colors.accent, borderWidth: 2 },
                    k === selected && k !== today && { backgroundColor: Colors.accent + '33' }]}>
            <Text style={[styles.cellNum, { color: k < today ? theme.textMuted : theme.text }]}>
              {Number(k.slice(8))}
            </Text>
            <View style={[styles.cellDot, { backgroundColor: dots[k] ? CATEGORY.festival.color : 'transparent' }]} />
          </TouchableOpacity>
        ) : <View key={`e${i}`} style={styles.cell} />)}
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  safe:   { flex: 1 },
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: Spacing.xl, paddingTop: Spacing.lg, paddingBottom: Spacing.sm,
  },
  title:    { ...Typography.display },
  subtitle: { ...Typography.label, marginTop: 2, fontSize: 14 },
  headerIcon: {
    width: 52, height: 52, borderRadius: Radius.full, borderWidth: 2,
    alignItems: 'center', justifyContent: 'center',
  },
  center:   { flex: 1, alignItems: 'center', justifyContent: 'center' },

  strip: { paddingHorizontal: Spacing.lg, paddingBottom: Spacing.md, gap: 8 },
  chip: {
    width: 60, height: 76, borderRadius: Radius.md, borderWidth: 1,
    alignItems: 'center', justifyContent: 'center',
  },
  chipDay: { fontSize: 11, fontWeight: '700', letterSpacing: 0.3 },
  chipNum: { fontSize: 22, fontWeight: '700', marginTop: 1 },
  chipDot: { width: 6, height: 6, borderRadius: 3, marginTop: 3 },

  scroll:   { paddingHorizontal: Spacing.lg },
  part:     { marginBottom: Spacing.md },
  partLabel:{ ...Typography.label, textTransform: 'uppercase', letterSpacing: 1,
              marginTop: Spacing.sm, marginBottom: 6, marginLeft: Spacing.xs },
  card: {
    flexDirection: 'row', alignItems: 'flex-start',
    borderRadius: Radius.lg, borderWidth: 1,
    paddingVertical: Spacing.md, paddingRight: Spacing.md, paddingLeft: Spacing.md,
    marginBottom: 6, overflow: 'hidden',
  },
  stripe:   { position: 'absolute', left: 0, top: 0, bottom: 0, width: 5 },
  cardTime: { ...Typography.heading, fontWeight: '700', width: 84, marginLeft: Spacing.xs },
  cardBody: { flex: 1, marginLeft: Spacing.sm },
  cardTitle:{ ...Typography.bodyLg, fontWeight: '600', lineHeight: 25 },
  meta:     { ...Typography.label, marginTop: 4 },
  bellRow:  { flexDirection: 'row', alignItems: 'center', marginTop: 5 },
  routineRow:   { flexDirection: 'row', alignItems: 'flex-start', paddingVertical: 6,
                  paddingLeft: Spacing.md + Spacing.xs },
  routineTime:  { ...Typography.body, fontWeight: '600', width: 84 },
  routineTitle: { ...Typography.body, flex: 1, marginLeft: Spacing.sm },
  addRow:   { borderWidth: 1, borderStyle: 'dashed', borderRadius: Radius.md,
              paddingVertical: 10, paddingHorizontal: Spacing.lg, marginTop: 4 },
  addText:  { color: Colors.accent, fontSize: 16, fontWeight: '600' },

  dim:   { flex: 1, backgroundColor: '#000a' },
  sheet: {
    borderTopLeftRadius: 24, borderTopRightRadius: 24, borderTopWidth: 1,
    paddingHorizontal: Spacing.xl, paddingTop: Spacing.md, paddingBottom: Spacing.xl,
  },
  grab:       { width: 44, height: 5, borderRadius: 3, backgroundColor: '#444', alignSelf: 'center', marginBottom: Spacing.md },
  sheetTitle: { fontSize: 22, fontWeight: '700', marginBottom: Spacing.sm },
  lbl:        { fontSize: 13, fontWeight: '600', marginTop: Spacing.md, marginBottom: 6 },
  input:      { borderWidth: 1, borderRadius: Radius.md, padding: 14, fontSize: 18 },
  row:        { flexDirection: 'row', gap: 10 },
  big:        { flex: 1, borderWidth: 1, borderRadius: Radius.md, paddingVertical: 14, alignItems: 'center' },
  bigText:    { fontSize: 18, fontWeight: '600' },
  kinds:      { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  kind:       { borderWidth: 1, borderRadius: 20, paddingVertical: 8, paddingHorizontal: 12 },
  note:       { fontSize: 13, marginTop: Spacing.md, lineHeight: 18 },
  save:       { marginTop: Spacing.lg, backgroundColor: Colors.accent, borderRadius: Radius.lg,
                paddingVertical: 16, alignItems: 'center' },
  saveText:   { color: '#fff', fontSize: 18, fontWeight: '700' },
  del:        { marginTop: Spacing.md, alignItems: 'center', paddingVertical: 6 },
  delText:    { color: Colors.accentRed, fontSize: 16, fontWeight: '600' },

  monthHeader:{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
                paddingHorizontal: Spacing.xl, paddingVertical: Spacing.md },
  link:       { color: Colors.accent, fontSize: 16, fontWeight: '600' },
  monthName:  { fontSize: 19, fontWeight: '700', marginTop: Spacing.md, marginBottom: Spacing.sm, marginLeft: 4 },
  weekRow:    { flexDirection: 'row', marginBottom: 4 },
  weekDay:    { flex: 1, textAlign: 'center', fontSize: 12, fontWeight: '600' },
  grid:       { flexDirection: 'row', flexWrap: 'wrap' },
  cell:       { width: `${100 / 7}%`, height: 48, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  cellNum:    { fontSize: 17, fontWeight: '600' },
  cellDot:    { width: 5, height: 5, borderRadius: 3, marginTop: 2 },
})

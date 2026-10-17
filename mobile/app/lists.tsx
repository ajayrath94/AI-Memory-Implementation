import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  View, Text, ScrollView, StyleSheet, SafeAreaView, TouchableOpacity,
  ActivityIndicator, RefreshControl, Alert, TextInput, Linking,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { useLocalSearchParams } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import { useTheme } from '../hooks/useTheme'
import { useT } from '../hooks/useT'
import { Colors, API_BASE, API_KEY } from '../constants'
import { useAppStore } from '../store/appStore'
import { pick } from '../components/chat/shortcuts'

// Her lists. Things go on them in chat ("sabudana bhi likh lena"); this is
// where she looks before leaving the house, and ticks things off in the shop.
// Big rows and big ticks — the phone is in one hand and a bag in the other.

interface ListCard {
  id: string
  key: string
  name: string
  purpose: string
  created_at: string
  expires_on: string | null
  closed_at: string | null
  total: number
  left: number
}
interface Item {
  id: string
  fields: Record<string, string>
  done: boolean
  created_at: string
}
// "Kahan milega?" — where the things still to get can be bought.
interface Shop {
  name: string
  address?: string
  distance_km?: number | null
  walk_min?: number | null
  open?: boolean | null
  rating?: number | null
  reviews?: number | null
  map_url?: string
}
interface ShopGroup { search: string; label: string; items: string[]; shops?: Shop[] }
interface OneStop { shop: Shop; covers: string[]; missing: string[] }
interface ShopPlan { buying: boolean; groups: ShopGroup[]; one_stop?: OneStop | null }
type Mode = 'nearest' | 'best'

const W = {
  where:   { en: 'Where can I get these?', hl: 'Kahan milega?', hi: 'कहाँ मिलेगा?', pa: 'ਕਿੱਥੋਂ ਮਿਲੇਗਾ?', gu: 'ક્યાં મળશે?',
             mr: 'कुठे मिळेल?', bn: 'কোথায় পাব?', ta: 'எங்கே கிடைக்கும்?', te: 'ఎక్కడ దొరుకుతుంది?' },
  hide:    { en: 'Hide shops', hl: 'Dukaanein chhupao', hi: 'दुकानें छुपाओ', pa: 'ਦੁਕਾਨਾਂ ਲੁਕਾਓ', gu: 'દુકાનો છુપાવો',
             mr: 'दुकानं लपवा', bn: 'দোকান লুকাও', ta: 'கடைகளை மறை', te: 'షాపులు దాచండి' },
  looking: { en: 'Looking for shops near you…', hl: 'Paas ki dukaanein dekh rahi hoon…', hi: 'पास की दुकानें देख रही हूँ…',
             pa: 'ਨੇੜੇ ਦੀਆਂ ਦੁਕਾਨਾਂ ਲੱਭ ਰਹੀ ਹਾਂ…', gu: 'નજીકની દુકાનો શોધી રહી છું…', mr: 'जवळची दुकानं शोधते आहे…',
             bn: 'কাছের দোকান খুঁজছি…', ta: 'அருகிலுள்ள கடைகளைத் தேடுகிறேன்…', te: 'దగ్గరి షాపులు వెతుకుతున్నాను…' },
  none:    { en: 'No shop found nearby', hl: 'Paas mein koi dukaan nahi mili', hi: 'पास में कोई दुकान नहीं मिली',
             pa: 'ਨੇੜੇ ਕੋਈ ਦੁਕਾਨ ਨਹੀਂ ਮਿਲੀ', gu: 'નજીકમાં કોઈ દુકાન ન મળી', mr: 'जवळ कुठलंही दुकान मिळालं नाही',
             bn: 'কাছে কোনো দোকান পাওয়া গেল না', ta: 'அருகில் கடை எதுவும் கிடைக்கவில்லை', te: 'దగ్గరలో ఏ షాపూ దొరకలేదు' },
  walk:    { en: 'min walk', hl: 'min paidal', hi: 'मिनट पैदल', pa: 'ਮਿੰਟ ਪੈਦਲ', gu: 'મિનિટ ચાલીને', mr: 'मिनिटं चालत',
             bn: 'মিনিট হাঁটা', ta: 'நிமிட நடை', te: 'నిమిషాల నడక' },
  open:    { en: 'Open now', hl: 'Abhi khuli hai', hi: 'अभी खुली है', pa: 'ਹੁਣ ਖੁੱਲ੍ਹੀ ਹੈ', gu: 'અત્યારે ખુલ્લી છે',
             mr: 'आत्ता उघडं आहे', bn: 'এখন খোলা', ta: 'இப்போது திறந்துள்ளது', te: 'ఇప్పుడు తెరిచి ఉంది' },
  shut:    { en: 'Closed now', hl: 'Abhi band hai', hi: 'अभी बंद है', pa: 'ਹੁਣ ਬੰਦ ਹੈ', gu: 'અત્યારે બંધ છે',
             mr: 'आत्ता बंद आहे', bn: 'এখন বন্ধ', ta: 'இப்போது மூடியுள்ளது', te: 'ఇప్పుడు మూసి ఉంది' },
  map:     { en: 'Map', hl: 'Naksha', hi: 'नक्शा', pa: 'ਨਕਸ਼ਾ', gu: 'નકશો', mr: 'नकाशा', bn: 'ম্যাপ', ta: 'வரைபடம்', te: 'మ్యాప్' },
  nearest: { en: 'Nearest', hl: 'Sabse paas', hi: 'सबसे पास', pa: 'ਸਭ ਤੋਂ ਨੇੜੇ', gu: 'સૌથી નજીક', mr: 'सर्वात जवळ',
             bn: 'সবচেয়ে কাছে', ta: 'மிக அருகில்', te: 'అతి దగ్గర' },
  best:    { en: 'Best', hl: 'Sabse achha', hi: 'सबसे अच्छा', pa: 'ਸਭ ਤੋਂ ਵਧੀਆ', gu: 'સૌથી સારું', mr: 'सर्वात चांगलं',
             bn: 'সবচেয়ে ভালো', ta: 'சிறந்தது', te: 'అత్యుత్తమం' },
  oneStop: { en: 'Everything in one place', hl: 'Ek hi jagah sab', hi: 'एक ही जगह सब', pa: 'ਇੱਕੋ ਥਾਂ ਸਭ',
             gu: 'એક જ જગ્યાએ બધું', mr: 'एकाच ठिकाणी सगळं', bn: 'এক জায়গায় সব', ta: 'ஒரே இடத்தில் எல்லாம்', te: 'ఒకే చోట అన్నీ' },
  except:  { en: 'except', hl: 'chhodkar', hi: 'छोड़कर', pa: 'ਛੱਡ ਕੇ', gu: 'સિવાય', mr: 'सोडून', bn: 'ছাড়া', ta: 'தவிர', te: 'తప్ప' },
  people:  { en: 'ratings', hl: 'log', hi: 'लोग', pa: 'ਲੋਕ', gu: 'લોકો', mr: 'लोक', bn: 'জন', ta: 'பேர்', te: 'మంది' },
  noShop:  { en: 'None of your open lists has things to buy.',
             hl: 'Abhi kisi list mein khareedne ki cheezein nahi hain.',
             hi: 'अभी किसी सूची में ख़रीदने की चीज़ें नहीं हैं।', pa: 'ਹਾਲੇ ਕਿਸੇ ਸੂਚੀ ਵਿੱਚ ਖ਼ਰੀਦਣ ਵਾਲੀਆਂ ਚੀਜ਼ਾਂ ਨਹੀਂ ਹਨ।',
             gu: 'હજી કોઈ યાદીમાં ખરીદવાની વસ્તુઓ નથી.', mr: 'अजून कुठल्याही यादीत खरेदीच्या वस्तू नाहीत.',
             bn: 'এখনও কোনো তালিকায় কেনার জিনিস নেই।', ta: 'எந்தப் பட்டியலிலும் வாங்க வேண்டிய பொருட்கள் இல்லை.',
             te: 'ఇంకా ఏ జాబితాలోనూ కొనాల్సిన వస్తువులు లేవు.' },
  finding: { en: 'Finding your shopping list…', hl: 'Aapki khareedne ki list dhoondh rahi hoon…',
             hi: 'आपकी ख़रीदने की सूची ढूँढ रही हूँ…', pa: 'ਤੁਹਾਡੀ ਖ਼ਰੀਦਦਾਰੀ ਵਾਲੀ ਸੂਚੀ ਲੱਭ ਰਹੀ ਹਾਂ…',
             gu: 'તમારી ખરીદીની યાદી શોધી રહી છું…', mr: 'तुमची खरेदीची यादी शोधते आहे…',
             bn: 'আপনার কেনাকাটার তালিকা খুঁজছি…', ta: 'உங்கள் வாங்கும் பட்டியலைத் தேடுகிறேன்…',
             te: 'మీ కొనుగోలు జాబితా వెతుకుతున్నాను…' },
}

function shopMeta(sh: Shop, lang: string, withRating: boolean): string {
  return [
    withRating && sh.rating != null
      ? `${sh.rating}★${sh.reviews ? ` (${sh.reviews} ${pick(W.people, lang)})` : ''}` : '',
    sh.walk_min != null ? `~${sh.walk_min} ${pick(W.walk, lang)}` : '',
    sh.distance_km != null ? `${sh.distance_km} km` : '',
    sh.open === true ? pick(W.open, lang) : sh.open === false ? pick(W.shut, lang) : '',
  ].filter(Boolean).join(' · ')
}

interface ListDetail extends ListCard {
  columns: string[]
  items: Item[]
}

const H = { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' }

function niceDate(d: string | null) {
  if (!d) return ''
  try {
    return new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
  } catch { return d }
}

export default function ListsScreen() {
  const theme = useTheme()
  const t = useT()
  const { userId } = useAppStore()
  const lang = useAppStore(s => s.language)
  const [openLists, setOpenLists] = useState<ListCard[]>([])
  const [keptLists, setKeptLists] = useState<ListCard[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [current, setCurrent] = useState<ListDetail | null>(null)
  const [newItem, setNewItem] = useState('')
  const [busy, setBusy] = useState(false)
  const [plan, setPlan] = useState<ShopPlan | null>(null)
  const [shops, setShops] = useState<ShopPlan | null>(null)
  const [mode, setMode] = useState<Mode>('nearest')
  const [shopsOpen, setShopsOpen] = useState(false)
  const [shopsLoading, setShopsLoading] = useState(false)

  const fetchAll = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/lists/${userId}`, { headers: H })
      const json = await res.json()
      setOpenLists(json.open || [])
      setKeptLists(json.kept || [])
    } catch (err) {
      console.error('Failed to fetch lists:', err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [userId])

  const fetchOne = useCallback(async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/lists/${userId}/${id}`, { headers: H })
      if (!res.ok) { setCurrent(null); return }
      setCurrent(await res.json())
    } catch (err) {
      console.error('Failed to fetch list:', err)
    } finally {
      setRefreshing(false)
    }
  }, [userId])

  // Refresh every 15s, like reminders — she may be adding things in chat.
  useEffect(() => {
    fetchAll()
    const t = setInterval(() => {
      if (current) fetchOne(current.id)
      else fetchAll()
    }, 15000)
    return () => clearInterval(t)
  }, [fetchAll, fetchOne, current?.id])

  const onRefresh = () => {
    setRefreshing(true)
    if (current) fetchOne(current.id)
    else fetchAll()
  }

  const back = () => { setCurrent(null); setNewItem(''); fetchAll() }

  // Whether this list is shopping, read again only when what is left on it
  // changes (the server keeps the answer too). Ticking something off in the
  // shop keeps the panel open; it is refreshed for what is left.
  const planKey = current && !current.closed_at
    ? current.id + '|' + current.items.filter(i => !i.done).map(i => i.fields.what).join('|')
    : ''
  const listId = current?.id

  const loadShops = useCallback(async (id: string, m: Mode) => {
    setShopsLoading(true)
    try {
      const res = await fetch(`${API_BASE}/lists/${userId}/${id}/shops?places=true&mode=${m}`, { headers: H })
      const j: ShopPlan = await res.json()
      setShops({ buying: !!j.buying, groups: j.groups || [], one_stop: j.one_stop || null })
    } catch (err) {
      console.error('Shops failed:', err)
      setShops({ buying: false, groups: [] })
    } finally {
      setShopsLoading(false)
    }
  }, [userId])

  const switchMode = (m: Mode) => {
    if (m === mode || !current) return
    setMode(m)
    setShops(null)
    loadShops(current.id, m)
  }

  // Another list: start closed.
  useEffect(() => { setPlan(null); setShops(null); setShopsOpen(false); setMode('nearest') }, [listId])

  useEffect(() => {
    if (!planKey || !listId) { setPlan(null); return }
    let live = true
    fetch(`${API_BASE}/lists/${userId}/${listId}/shops`, { headers: H })
      .then(r => r.json()).then(j => { if (live) setPlan(j) })
      .catch(err => console.error('Shop plan failed:', err))
    setShops(null)
    if (shopsOpen) loadShops(listId, mode)
    return () => { live = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planKey, userId])

  // "Kahan milega?" from the Listein sheet (?shops=1): her latest open list
  // that has things to buy, opened with the shops already showing.
  // From a list card in the chat, ?id= names the list: that one first.
  const { shops: wantShops, id: wantId } = useLocalSearchParams<{ shops?: string; id?: string }>()
  const askedShops = useRef(false)
  const pendingShops = useRef<string | null>(null)
  const [notice, setNotice] = useState('')
  useEffect(() => {
    if (wantShops !== '1' || askedShops.current || loading) return
    askedShops.current = true
    ;(async () => {
      setNotice(pick(W.finding, lang))
      const order = wantId
        ? [...openLists.filter(l => l.id === wantId), ...openLists.filter(l => l.id !== wantId)]
        : openLists
      for (const l of order) {
        try {
          const r = await fetch(`${API_BASE}/lists/${userId}/${l.id}/shops`, { headers: H })
          const j: ShopPlan = await r.json()
          if (j?.buying) {
            setNotice('')
            pendingShops.current = l.id
            fetchOne(l.id)
            return
          }
        } catch (err) { console.error('Shop plan failed:', err) }
      }
      setNotice(pick(W.noShop, lang))
    })()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantShops, loading, openLists])

  useEffect(() => {
    if (!current || pendingShops.current !== current.id || !plan?.buying) return
    pendingShops.current = null
    setShopsOpen(true)
    loadShops(current.id, mode)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan, current?.id])

  const toggleShops = () => {
    if (!current) return
    if (shopsOpen) { setShopsOpen(false); return }
    setShopsOpen(true)
    if (!shops) loadShops(current.id, mode)
  }

  // ── item actions ──────────────────────────────────────────────────────────

  const toggle = async (it: Item) => {
    if (!current) return
    const done = !it.done
    // Optimistic: the tick shows at once, and goes back if the save fails.
    setCurrent({ ...current, items: current.items.map(x => x.id === it.id ? { ...x, done } : x) })
    try {
      const res = await fetch(`${API_BASE}/lists/${userId}/${current.id}/items/${it.id}/tick`, {
        method: 'POST', headers: H, body: JSON.stringify({ done }),
      })
      if (!res.ok) throw new Error(String(res.status))
    } catch (err) {
      console.error('Tick failed:', err)
      setCurrent(c => c ? { ...c, items: c.items.map(x => x.id === it.id ? { ...x, done: !done } : x) } : c)
    }
  }

  const addItem = async () => {
    const what = newItem.trim()
    if (!what || !current || busy) return
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/lists/${userId}/${current.id}/items`, {
        method: 'POST', headers: H, body: JSON.stringify({ what }),
      })
      if (res.ok) {
        setNewItem('')
        fetchOne(current.id)
      }
    } catch (err) {
      console.error('Add failed:', err)
    } finally {
      setBusy(false)
    }
  }

  const removeItem = (it: Item) => {
    if (!current) return
    Alert.alert(
      t('lists.removeTitle'),
      t('lists.removeBody', { what: it.fields.what }),
      [
        { text: t('lists.leaveIt'), style: 'cancel' },
        {
          text: t('lists.remove'), style: 'destructive',
          onPress: async () => {
            try {
              await fetch(`${API_BASE}/lists/${userId}/${current.id}/items/${it.id}`, {
                method: 'DELETE', headers: H,
              })
              fetchOne(current.id)
            } catch (err) { console.error('Remove failed:', err) }
          },
        },
      ],
    )
  }

  // ── list actions ──────────────────────────────────────────────────────────

  const closeList = (l: ListCard) => {
    Alert.alert(
      t('lists.closeTitle'),
      t('lists.closeBody', { name: l.name }),
      [
        { text: t('lists.notNow'), style: 'cancel' },
        { text: t('lists.keep'), onPress: () => doClose(l, true) },
        { text: t('lists.delete'), style: 'destructive', onPress: () => doClose(l, false) },
      ],
    )
  }

  const deleteKept = (l: ListCard) => {
    Alert.alert(
      t('lists.deleteForeverTitle'),
      t('lists.deleteForeverBody', { name: l.name, date: niceDate(l.created_at) }),
      [
        { text: t('lists.leaveIt'), style: 'cancel' },
        { text: t('lists.delete'), style: 'destructive', onPress: () => doClose(l, false) },
      ],
    )
  }

  const doClose = async (l: ListCard, keep: boolean) => {
    try {
      await fetch(`${API_BASE}/lists/${userId}/${l.id}/close`, {
        method: 'POST', headers: H, body: JSON.stringify({ keep }),
      })
    } catch (err) { console.error('Close failed:', err) }
    back()
  }

  const reuse = async (l: ListCard) => {
    try {
      const res = await fetch(`${API_BASE}/lists/${userId}/${l.id}/reuse`, {
        method: 'POST', headers: H,
      })
      const json = await res.json()
      if (json.id) { fetchOne(json.id); return }
    } catch (err) { console.error('Reuse failed:', err) }
    fetchAll()
  }

  // ── render ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <SafeAreaView style={[styles.safe, { backgroundColor: theme.bg }]}>
        <View style={styles.center}>
          <ActivityIndicator color={Colors.accent} size="large" />
        </View>
      </SafeAreaView>
    )
  }

  if (current) {
    const isKept = !!current.closed_at
    const left = current.items.filter(i => !i.done)
    const done = current.items.filter(i => i.done)
    const extra = current.columns.filter(c => c !== 'what')

    const row = (it: Item) => (
      <TouchableOpacity
        key={it.id}
        style={[styles.itemRow, { borderColor: theme.border }, it.done && styles.itemRowDone]}
        onPress={() => !isKept && toggle(it)}
        onLongPress={() => !isKept && removeItem(it)}
        activeOpacity={0.7}
        disabled={isKept}
      >
        <Ionicons
          name={it.done ? 'checkmark-circle' : 'ellipse-outline'}
          size={32}
          color={it.done ? Colors.accentGreen : Colors.textMuted}
        />
        <View style={styles.itemBody}>
          <Text style={[styles.itemWhat, it.done && styles.itemWhatDone]}>{it.fields.what}</Text>
          {extra.some(k => it.fields[k]) && (
            <View style={styles.chips}>
              {extra.filter(k => it.fields[k]).map(k => (
                <Text key={k} style={styles.chip}>{k}: {it.fields[k]}</Text>
              ))}
            </View>
          )}
        </View>
      </TouchableOpacity>
    )

    return (
      <SafeAreaView style={[styles.safe, { backgroundColor: theme.bg }]}>
        <StatusBar style="light" />
        <View style={[styles.header, styles.headerRow, { borderBottomColor: theme.border }]}>
          <TouchableOpacity onPress={back} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
            <Ionicons name="chevron-back" size={28} color={Colors.text} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={styles.headerTitle} numberOfLines={1}>{current.name}</Text>
            <Text style={styles.headerSub}>
              {niceDate(current.created_at)}
              {isKept ? ` · ${t('lists.kept')}` : ` · ${t('lists.left', { n: left.length })}`}
              {current.expires_on && !isKept ? ` · ${t('lists.until', { date: niceDate(current.expires_on) })}` : ''}
            </Text>
          </View>
          {!isKept && (
            <TouchableOpacity onPress={() => closeList(current)} style={styles.headerAction}>
              <Text style={styles.headerActionText}>{t('lists.close')}</Text>
            </TouchableOpacity>
          )}
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.accent} />}
        >
          {isKept ? (
            <TouchableOpacity style={styles.bigButton} onPress={() => reuse(current)}>
              <Ionicons name="refresh" size={20} color="#fff" />
              <Text style={styles.bigButtonText}>{t('lists.reuse')}</Text>
            </TouchableOpacity>
          ) : (
            <View style={[styles.addRow, { borderColor: theme.border }]}>
              <TextInput
                value={newItem}
                onChangeText={setNewItem}
                placeholder={t('lists.addPlaceholder')}
                placeholderTextColor={Colors.textMuted}
                style={styles.addInput}
                onSubmitEditing={addItem}
                returnKeyType="done"
              />
              <TouchableOpacity onPress={addItem} disabled={!newItem.trim() || busy}>
                <Ionicons name="add-circle" size={36}
                  color={newItem.trim() ? Colors.accent : Colors.textMuted} />
              </TouchableOpacity>
            </View>
          )}

          {current.items.length === 0 && (
            <Text style={styles.emptyText}>{t('lists.emptyList')}</Text>
          )}

          {!isKept && plan?.buying && (
            <TouchableOpacity style={styles.whereBtn} onPress={toggleShops} activeOpacity={0.8}>
              <Ionicons name={shopsOpen ? 'chevron-up' : 'storefront-outline'} size={22} color="#fff" />
              <Text style={styles.bigButtonText}>{pick(shopsOpen ? W.hide : W.where, lang)}</Text>
            </TouchableOpacity>
          )}
          {!isKept && plan?.buying && shopsOpen && (
            <View style={[styles.shopsBox, { borderColor: theme.border }]}>
              <View style={styles.modeRow}>
                {(['nearest', 'best'] as Mode[]).map(m => (
                  <TouchableOpacity key={m} activeOpacity={0.8} onPress={() => switchMode(m)}
                    style={[styles.modeBtn, mode === m && styles.modeBtnOn]}>
                    <Text style={[styles.modeText, mode === m && styles.modeTextOn]}>
                      {m === 'nearest' ? '📍 ' : '⭐ '}{pick(m === 'nearest' ? W.nearest : W.best, lang)}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              {shopsLoading && (
                <View style={styles.shopsLoading}>
                  <ActivityIndicator color={Colors.accent} />
                  <Text style={styles.shopMeta}>{pick(W.looking, lang)}</Text>
                </View>
              )}
              {!shopsLoading && mode === 'best' && shops?.one_stop && (
                <TouchableOpacity style={styles.oneStop} activeOpacity={0.8}
                  disabled={!shops.one_stop.shop.map_url}
                  onPress={() => shops.one_stop?.shop.map_url && Linking.openURL(shops.one_stop.shop.map_url).catch(() => {})}>
                  <Text style={styles.oneStopTitle}>🛍️ {pick(W.oneStop, lang)}</Text>
                  <Text style={styles.shopName}>{shops.one_stop.shop.name}</Text>
                  <Text style={styles.shopMeta}>{shopMeta(shops.one_stop.shop, lang, true)}</Text>
                  <Text style={styles.shopItems}>
                    {shops.one_stop.covers.join(', ')}
                    {shops.one_stop.missing.length > 0
                      ? ` — ${shops.one_stop.missing.join(', ')} ${pick(W.except, lang)}` : ''}
                  </Text>
                  <View style={[styles.mapPill, { alignSelf: 'flex-start', marginTop: 6 }]}>
                    <Text style={styles.mapPillText}>📍 {pick(W.map, lang)}</Text>
                  </View>
                </TouchableOpacity>
              )}
              {!shopsLoading && (shops?.groups || []).map(g => (
                <View key={g.search + g.label} style={styles.shopGroup}>
                  <Text style={styles.shopGroupTitle}>{g.label}</Text>
                  <Text style={styles.shopItems}>{g.items.join(', ')}</Text>
                  {(g.shops || []).length === 0 && (
                    <Text style={styles.shopMeta}>{pick(W.none, lang)}</Text>
                  )}
                  {(g.shops || []).map(sh => (
                    <TouchableOpacity key={sh.name + (sh.map_url || '')} style={styles.shopRow}
                      activeOpacity={0.75} disabled={!sh.map_url}
                      onPress={() => sh.map_url && Linking.openURL(sh.map_url).catch(() => {})}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.shopName} numberOfLines={2}>{sh.name}</Text>
                        <Text style={styles.shopMeta}>{shopMeta(sh, lang, mode === 'best')}</Text>
                      </View>
                      {sh.map_url && (
                        <View style={styles.mapPill}>
                          <Text style={styles.mapPillText}>📍 {pick(W.map, lang)}</Text>
                        </View>
                      )}
                    </TouchableOpacity>
                  ))}
                </View>
              ))}
            </View>
          )}

          {left.map(row)}
          {done.length > 0 && (
            <>
              <Text style={[styles.sectionLabel, { marginTop: 18 }]}>
                {isKept ? t('lists.lastTime') : t('lists.gotHeading', { n: done.length })}
              </Text>
              {done.map(row)}
            </>
          )}
          {!isKept && current.items.length > 0 && (
            <Text style={styles.tip}>{t('lists.tip')}</Text>
          )}
        </ScrollView>
      </SafeAreaView>
    )
  }

  const card = (l: ListCard, kept: boolean) => (
    <TouchableOpacity
      key={l.id}
      style={[styles.card, { borderColor: theme.border }, kept && styles.cardKept]}
      onPress={() => fetchOne(l.id)}
      onLongPress={() => kept ? deleteKept(l) : closeList(l)}
      activeOpacity={0.7}
    >
      <View style={styles.cardIcon}>
        <Ionicons name={kept ? 'archive-outline' : 'list'} size={22} color={kept ? Colors.textMuted : Colors.accent} />
      </View>
      <View style={styles.cardBody}>
        <Text style={styles.cardName} numberOfLines={1}>{l.name}</Text>
        <Text style={styles.cardMeta}>
          {niceDate(l.created_at)}
          {kept ? ` · ${t('lists.items', { n: l.total })}` : ` · ${t('lists.leftOf', { left: l.left, total: l.total })}`}
          {!kept && l.expires_on ? ` · ${t('lists.until', { date: niceDate(l.expires_on) })}` : ''}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={22} color={Colors.textMuted} />
    </TouchableOpacity>
  )

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: theme.bg }]}>
      <StatusBar style="light" />
      <View style={[styles.header, { borderBottomColor: theme.border }]}>
        <Text style={styles.headerTitle}>📝 {t('lists.title')}</Text>
        <Text style={styles.headerSub}>
          {openLists.length > 0 ? t('lists.openCount', { n: openLists.length }) : t('lists.noneOpen')}
        </Text>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.accent} />}
      >
        {!!notice && (
          <View style={[styles.shopsBox, { borderColor: Colors.accent + '55', marginBottom: 14 }]}>
            <Text style={[styles.shopName, { textAlign: 'center' }]}>🛍️ {notice}</Text>
          </View>
        )}
        {openLists.length === 0 && keptLists.length === 0 && (
          <View style={styles.empty}>
            <Ionicons name="list-outline" size={48} color={Colors.textMuted} />
            <Text style={styles.emptyTitle}>{t('lists.emptyTitle')}</Text>
            <Text style={styles.emptyText}>{t('lists.emptyText')}</Text>
          </View>
        )}

        {openLists.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionLabel}>{t('lists.sectionOpen')}</Text>
            {openLists.map(l => card(l, false))}
          </View>
        )}

        {keptLists.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionLabel}>{t('lists.sectionKept')}</Text>
            {keptLists.map(l => card(l, true))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  header: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 14, borderBottomWidth: 0.5 },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 12 },
  headerTitle: { fontSize: 22, fontWeight: '700', color: Colors.text },
  headerSub: { fontSize: 13, color: Colors.textMuted, marginTop: 2 },
  headerAction: {
    paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10,
    backgroundColor: Colors.textMuted + '22',
  },
  headerActionText: { fontSize: 14, fontWeight: '600', color: Colors.text },

  scroll: { flex: 1 },
  scrollContent: { padding: 16, paddingBottom: 60 },

  section: { marginBottom: 24 },
  sectionLabel: {
    fontSize: 12, fontWeight: '700', color: Colors.textMuted,
    letterSpacing: 1, marginBottom: 10, marginLeft: 4,
  },

  card: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    borderWidth: 0.5, borderRadius: 14, minHeight: 64,
    paddingVertical: 12, paddingHorizontal: 14, marginBottom: 10,
    backgroundColor: '#ffffff08',
  },
  cardKept: { opacity: 0.7 },
  cardIcon: {
    width: 40, height: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center',
    backgroundColor: Colors.accent + '18',
  },
  cardBody: { flex: 1 },
  cardName: { fontSize: 18, fontWeight: '600', color: Colors.text, textTransform: 'capitalize' },
  cardMeta: { fontSize: 13, color: Colors.textMuted, marginTop: 2 },

  addRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    borderWidth: 0.5, borderRadius: 14, paddingLeft: 14, paddingRight: 8,
    minHeight: 56, marginBottom: 14, backgroundColor: '#ffffff08',
  },
  addInput: { flex: 1, fontSize: 17, color: Colors.text, paddingVertical: 10 },

  itemRow: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    minHeight: 56, borderWidth: 0.5, borderRadius: 14,
    paddingVertical: 10, paddingHorizontal: 14, marginBottom: 8,
    backgroundColor: '#ffffff08',
  },
  itemRowDone: { opacity: 0.55 },
  itemBody: { flex: 1 },
  itemWhat: { fontSize: 18, fontWeight: '600', color: Colors.text },
  itemWhatDone: { textDecorationLine: 'line-through' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 6 },
  chip: {
    fontSize: 13, color: Colors.text, overflow: 'hidden',
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8,
    backgroundColor: Colors.accent + '22',
  },

  bigButton: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    minHeight: 56, borderRadius: 14, marginBottom: 16, backgroundColor: Colors.accent,
  },
  bigButtonText: { fontSize: 17, fontWeight: '700', color: '#fff' },

  tip: { fontSize: 13, color: Colors.textMuted, textAlign: 'center', marginTop: 16 },
  whereBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
    minHeight: 54, borderRadius: 14, backgroundColor: Colors.accentGreen, marginBottom: 14,
  },
  shopsBox: { borderWidth: 1, borderRadius: 14, padding: 12, marginBottom: 16, gap: 14 },
  shopsLoading: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 8 },
  shopGroup: { gap: 6 },
  shopGroupTitle: { fontSize: 18, fontWeight: '700', color: Colors.text },
  shopItems: { fontSize: 15, color: Colors.textSecond, marginBottom: 2 },
  shopRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 56,
    paddingVertical: 8, paddingHorizontal: 10, borderRadius: 12,
    backgroundColor: Colors.accent + '14', borderWidth: 1, borderColor: Colors.accent + '44',
  },
  shopName: { fontSize: 16, fontWeight: '600', color: Colors.text },
  shopMeta: { fontSize: 14, color: Colors.textSecond, marginTop: 2 },
  mapPill: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 20, backgroundColor: Colors.accent },
  mapPillText: { fontSize: 15, fontWeight: '700', color: '#fff' },
  modeRow: { flexDirection: 'row', gap: 8 },
  modeBtn: { flex: 1, minHeight: 48, borderRadius: 12, alignItems: 'center', justifyContent: 'center',
             borderWidth: 1, borderColor: Colors.accent + '55' },
  modeBtnOn: { backgroundColor: Colors.accent, borderColor: Colors.accent },
  modeText: { fontSize: 16, fontWeight: '600', color: Colors.textSecond },
  modeTextOn: { color: '#fff', fontWeight: '700' },
  oneStop: { borderRadius: 14, padding: 12, gap: 2, borderWidth: 2, borderColor: Colors.accentGreen,
             backgroundColor: Colors.accentGreen + '18' },
  oneStopTitle: { fontSize: 16, fontWeight: '700', color: Colors.accentGreen, marginBottom: 2 },

  empty: { alignItems: 'center', paddingTop: 80, paddingHorizontal: 32, gap: 10 },
  emptyTitle: { fontSize: 17, fontWeight: '600', color: Colors.text },
  emptyText: { fontSize: 14, color: Colors.textMuted, textAlign: 'center', lineHeight: 20 },
})

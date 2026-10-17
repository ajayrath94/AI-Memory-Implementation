/**
 * HEARING THE MESSAGE.
 *
 * She is seventy and reads on a phone. Hearing is easier, and for anyone
 * whose eyes are going it is the difference between using this and not.
 *
 * TWO RULES THIS FILE EXISTS TO KEEP
 *
 *   one voice at a time   two messages speaking over each other is worse
 *                         than silence, and happens the moment a reply
 *                         arrives while the last one is still playing.
 *
 *   never block the text  if audio fails — no network, no key, a provider
 *                         down — the message is on screen as it always was.
 *                         Voice is an addition, never a dependency.
 *
 * The audio comes from the backend, which picks Sarvam or Google and decides
 * the tone from the intent and how her day is going. Nothing here chooses a
 * voice; it plays what it is given.
 */
import { Audio } from 'expo-av'
import * as FileSystem from 'expo-file-system'
import { API_BASE } from '../constants'
import { getAuthHeaders } from './authService'

export type Playback = 'auto' | 'tap' | 'off'

// The one sound that may be playing. Everything here goes through it.
let current: Audio.Sound | null = null
let currentId: string | null = null
const listeners = new Set<(id: string | null) => void>()

// Every playback takes a turn number; anything newer cancels it.
//
// speak() used to stop what was playing and THEN spend seconds downloading.
// A second message arriving in those seconds found nothing playing yet,
// stopped nothing, and both played over each other — the first one
// unstoppable, because `current` now pointed at the second.
let turn = 0

// Messages waiting to be read, in order: two arriving together are read one
// after the other, never on top of each other.
const queue: { text: string; opts: SpeakOpts }[] = []
let draining = false
let inFlight: string | null = null      // the words being fetched or played now

// What was spoken lately, so the same words are not read twice — a reminder
// spoken on her tap, then again when the same reminder appears in the chat.
const recent = new Map<string, number>()
const norm = (t: string) => (t || '').toLowerCase().replace(/\s+/g, ' ').trim()

export type SpeakOpts = { id?: string; intent?: string; valence?: number; userId?: string }

function announce(id: string | null) {
  currentId = id
  listeners.forEach((fn) => fn(id))
}

/** Which message is speaking, so a bubble can show it. */
export function onPlayingChange(fn: (id: string | null) => void) {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}

export function playingId(): string | null {
  return currentId
}

/** Were these words spoken in the last two minutes? */
export function wasJustSpoken(text: string, withinMs = 120000): boolean {
  const at = recent.get(norm(text))
  return !!at && Date.now() - at < withinMs
}

/** Stop whatever is speaking and drop what was waiting. Called before
 *  anything new, and when she sends a message — a voice still talking about
 *  the last thing while she is writing the next is the worst of it. */
export async function stop() {
  turn++
  queue.length = 0
  const sound = current
  current = null
  announce(null)
  if (!sound) return
  try {
    await sound.stopAsync()
    await sound.unloadAsync()
  } catch {
    // already gone
  }
}

let configured = false
async function configureAudio() {
  if (configured) return
  try {
    await Audio.setAudioModeAsync({
      // So it is heard even if her phone is on silent — a medication
      // reminder she cannot hear is not a reminder. iOS only; harmless
      // elsewhere.
      playsInSilentModeIOS: true,
      staysActiveInBackground: false,
      shouldDuckAndroid: true,
    })
    configured = true
  } catch (e) {
    console.log('[voice] audio mode failed', e)
  }
}

// ── voices kept on the phone, for when there is no internet ─────────────
//
// A reminder's words are known when it is scheduled, so its voice is fetched
// then, while she is online, and kept. When it rings and she taps it — on a
// bus, in the village, with no signal — it plays from here.
const CACHE = `${FileSystem.documentDirectory}voice/`

function hashOf(text: string): string {
  let h = 5381
  const s = norm(text)
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0
  return (h >>> 0).toString(16)
}

async function cachedFile(text: string): Promise<string | null> {
  const base = `${CACHE}${hashOf(text)}`
  for (const ext of ['.wav', '.mp3']) {
    try {
      const info = await FileSystem.getInfoAsync(base + ext)
      if (info.exists) return base + ext
    } catch {}
  }
  return null
}

function voiceUrl(text: string, opts: SpeakOpts): string {
  // encodeURIComponent, not URLSearchParams — another browser global that
  // may not be in this runtime, and the last one cost a day.
  return `${API_BASE}/voice/speak`
    + `?text=${encodeURIComponent(text.slice(0, 1500))}`
    + `&user_id=${encodeURIComponent(opts.userId || 'default')}`
    + `&intent=${encodeURIComponent(opts.intent || '')}`
}

/** Download a voice to `uri`; returns where it ended up (.wav or .mp3), or
 *  null. Sarvam sends WAV, Google (the fallback) MP3, and iOS goes by the
 *  file name — an MP3 saved as .wav would not play. */
async function download(text: string, opts: SpeakOpts, uri: string): Promise<string | null> {
  // expo-file-system downloads straight to a file: fetch + btoa and
  // res.blob() + FileReader both failed in this runtime.
  const result = await FileSystem.downloadAsync(voiceUrl(text, opts), uri,
                                                { headers: await getAuthHeaders() })
  if (result.status !== 200) {
    console.log('[voice] no audio', result.status)
    FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {})
    return null
  }
  const ctype = String(
    (result.headers as any)?.['Content-Type'] ?? (result.headers as any)?.['content-type'] ?? '',
  ).toLowerCase()
  if (ctype.includes('mpeg') || ctype.includes('mp3')) {
    const mp3 = uri.replace(/\.wav$/, '.mp3')
    await FileSystem.moveAsync({ from: uri, to: mp3 })
    return mp3
  }
  return uri
}

/** Fetch and keep the voice for these words, if not kept already. */
export async function prefetch(text: string, opts: SpeakOpts = {}): Promise<boolean> {
  const body = (text || '').trim()
  if (body.length < 2) return false
  try {
    if (await cachedFile(body)) return true
    await FileSystem.makeDirectoryAsync(CACHE, { intermediates: true }).catch(() => {})
    return !!(await download(body, { intent: 'reminder', ...opts }, `${CACHE}${hashOf(body)}.wav`))
  } catch (e) {
    console.log('[voice] prefetch failed', e)
    return false
  }
}

/** Remove kept voices that no upcoming reminder needs any more. */
export async function pruneVoices(keep: string[]): Promise<void> {
  try {
    const want = new Set(keep.map(hashOf))
    const files = await FileSystem.readDirectoryAsync(CACHE)
    for (const f of files) {
      if (!want.has(f.replace(/\.(wav|mp3)$/, ''))) {
        FileSystem.deleteAsync(CACHE + f, { idempotent: true }).catch(() => {})
      }
    }
  } catch {}
}

/**
 * Play one message, unless a newer turn has begun by the time it is ready.
 * Kept voice first (works offline), else downloaded now.
 */
async function play(text: string, opts: SpeakOpts, mine: number): Promise<boolean> {
  inFlight = norm(text)
  try { return await playInner(text, opts, mine) } finally {
    if (inFlight === norm(text)) inFlight = null
  }
}

async function playInner(text: string, opts: SpeakOpts, mine: number): Promise<boolean> {
  try { await configureAudio() } catch (e) { console.log('[voice] audio mode', e) }
  let uri: string | null = null
  let temp = false
  try {
    uri = await cachedFile(text)
    if (!uri) {
      uri = await download(text, opts, `${FileSystem.cacheDirectory}voice_${Date.now()}.wav`)
      temp = true
    }
    if (!uri) return false
    if (mine !== turn) {                       // overtaken while downloading
      if (temp) FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {})
      return false
    }
    const { sound } = await Audio.Sound.createAsync({ uri }, { shouldPlay: false })
    if (mine !== turn) {                       // overtaken while loading
      sound.unloadAsync().catch(() => {})
      if (temp) FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {})
      return false
    }
    current = sound
    announce(opts.id || null)
    recent.set(norm(text), Date.now())
    const done = new Promise<void>((resolve) => {
      sound.setOnPlaybackStatusUpdate((status) => {
        if (!status.isLoaded) { resolve(); return }
        if (status.didJustFinish) {
          if (current === sound) { current = null; announce(null) }
          sound.unloadAsync().catch(() => {})
          if (temp && uri) FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {})
          resolve()
        }
      })
    })
    await sound.playAsync()
    await done
    return true
  } catch (e) {
    // Quiet: the text is on screen, and that is the fallback. This used to
    // put a stack trace in front of her whenever the voice could not come —
    // which, without internet, would be every time.
    console.log('[voice] speak failed', e)
    if (temp && uri) FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {})
    if (mine === turn) announce(null)
    return false
  }
}

/**
 * Speak one message now — her tap, or a reminder she opened. Stops
 * whatever was speaking and drops what was waiting.
 *
 * Returns true if it played. False means the text stands on its own, which
 * is the normal fallback and not an error worth showing her.
 */
export async function speak(text: string, opts: SpeakOpts = {}): Promise<boolean> {
  const body = (text || '').trim()
  if (body.length < 2) return false
  await stop()
  return play(body, opts, turn)
}

/**
 * Read a new arrival after whatever is already being read — two messages
 * that come together are heard one after the other.
 */
export function enqueue(text: string, opts: SpeakOpts = {}) {
  const body = (text || '').trim()
  if (body.length < 2) return
  // Not twice: the chat reloading from the server gives the same message a
  // new id, and it looked new — queued again while its first reading was
  // still downloading.
  const k = norm(body)
  if (k === inFlight || queue.some(q => norm(q.text) === k) || wasJustSpoken(body)) return
  queue.push({ text: body, opts })
  if (!draining) drain()
}

async function drain() {
  draining = true
  try {
    while (queue.length) {
      if (current) { await new Promise(r => setTimeout(r, 300)); continue }
      const mine = turn
      const next = queue.shift()!
      await play(next.text, next.opts, mine)
      if (mine !== turn) break                 // she tapped or sent: stop reading
    }
  } finally {
    draining = false
  }
}

/** auto | tap | off, and which voice she would hear. */
export async function getPreference(userId = 'default'): Promise<{
  playback: Playback; voice: string; language: string
}> {
  try {
    const res = await fetch(`${API_BASE}/voice/preference/${userId}`, {
      headers: { ...(await getAuthHeaders()) },
    })
    if (res.ok) return await res.json()
  } catch (e) {
    console.log('[voice] preference failed', e)
  }
  // tap, because audio starting on its own in a room she is not alone in is
  // the worse mistake.
  return { playback: 'tap', voice: '', language: '' }
}

export async function setPreference(
  playback: Playback, userId = 'default', speakOffers = false,
): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/voice/preference`, {
      method: 'POST',
      headers: { ...(await getAuthHeaders()) },
      body: JSON.stringify({ user_id: userId, playback, speak_offers: speakOffers }),
    })
    return res.ok
  } catch {
    return false
  }
}

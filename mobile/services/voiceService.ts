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

/** Stop whatever is speaking. Called before anything new, and when she
 *  sends a message — a voice still talking about the last thing while she
 *  is writing the next is the worst of it. */
export async function stop() {
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

/**
 * Speak one message.
 *
 * Returns true if it played. False means the text stands on its own, which
 * is the normal fallback and not an error worth showing her.
 */
export async function speak(
  text: string,
  opts: { id?: string; intent?: string; valence?: number; userId?: string } = {},
): Promise<boolean> {
  const body = (text || '').trim()
  if (body.length < 2) return false

  await stop()
  await configureAudio()

  try {
    const res = await fetch(`${API_BASE}/voice/speak`, {
      method: 'POST',
      headers: { ...(await getAuthHeaders()) },
      body: JSON.stringify({
        text: body,
        user_id: opts.userId || 'default',
        intent: opts.intent || '',
        valence: opts.valence ?? 0,
      }),
      // Generous: synthesis is a second or two, and a message that arrives
      // late is better than one that never speaks.
      signal: AbortSignal.timeout(25000),
    })

    // 204 means the backend could not synthesise. The text is on screen.
    if (res.status === 204 || !res.ok) return false

    const type = res.headers.get('content-type') || ''
    const ext = type.includes('wav') ? 'wav' : 'mp3'

    // expo-av wants a URI, so the bytes go to the cache first.
    const buf = await res.arrayBuffer()
    const b64 = arrayBufferToBase64(buf)
    const uri = `${FileSystem.cacheDirectory}voice_${Date.now()}.${ext}`
    await FileSystem.writeAsStringAsync(uri, b64, {
      encoding: FileSystem.EncodingType.Base64,
    })

    const { sound } = await Audio.Sound.createAsync({ uri }, { shouldPlay: true })
    current = sound
    announce(opts.id || null)

    sound.setOnPlaybackStatusUpdate((status) => {
      if (!status.isLoaded) return
      if (status.didJustFinish) {
        announce(null)
        current = null
        sound.unloadAsync().catch(() => {})
        FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {})
      }
    })
    return true
  } catch (e) {
    console.log('[voice] speak failed', e)
    announce(null)
    return false
  }
}

/** auto | tap | off, and which voice she would hear. */
export async function getPreference(userId = 'default'): Promise<{
  playback: Playback; voice: string; language: string
}> {
  try {
    const res = await fetch(`${API_BASE}/voice/preference/${userId}`, {
      headers: { ...(await getAuthHeaders()) },
      signal: AbortSignal.timeout(8000),
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
      signal: AbortSignal.timeout(8000),
    })
    return res.ok
  } catch {
    return false
  }
}

// Chunked, because a long message's audio is a few hundred kilobytes and
// String.fromCharCode over the whole array blows the stack.
function arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let binary = ''
  const chunk = 8192
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(
      null, Array.from(bytes.subarray(i, i + chunk)) as any,
    )
  }
  return global.btoa ? global.btoa(binary) : btoa(binary)
}

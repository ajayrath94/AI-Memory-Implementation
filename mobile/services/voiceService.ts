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
  // configureAudio has been a suspect: setAudioModeAsync's options changed
  // between expo-av versions, and an unknown key throws. Guarded rather than
  // awaited, because audio that plays through the ringer switch is better
  // than audio that does not play at all.
  try { await configureAudio() } catch (e) { console.log('[voice] audio mode', e) }

  try {
    // expo-file-system downloads it straight to a file.
    //
    // Two earlier attempts went through fetch: the first base64'd the body
    // by hand with btoa, which does not exist in this runtime, and the
    // second used res.blob() with FileReader, whose polyfill is incomplete
    // here. Both threw and the catch swallowed it, so the speaker did
    // nothing and said nothing.
    const uri = `${FileSystem.cacheDirectory}voice_${Date.now()}.wav`
    const result = await FileSystem.downloadAsync(
      // encodeURIComponent, not URLSearchParams — another browser global
      // that may not be in this runtime, and the last one cost a day.
      `${API_BASE}/voice/speak`
        + `?text=${encodeURIComponent(body.slice(0, 1500))}`
        + `&user_id=${encodeURIComponent(opts.userId || 'default')}`
        + `&intent=${encodeURIComponent(opts.intent || '')}`,
      uri,
      { headers: await getAuthHeaders() },
    )
    if (result.status !== 200) {
      console.log('[voice] no audio', result.status)
      return false
    }

    // Named, so a failure says which half broke even when Hermes gives no
    // stack: 'undefined is not a function' alone has cost most of a morning.
    if (typeof (FileSystem as any).downloadAsync !== 'function') {
      throw new Error('FileSystem.downloadAsync missing')
    }
    if (typeof (Audio as any)?.Sound?.createAsync !== 'function') {
      throw new Error('Audio.Sound.createAsync missing - expo-av not linked')
    }

    // Sarvam sends WAV, Google (the fallback) sends MP3. iOS goes by the file
    // name, so an MP3 saved as .wav would not play — silently, on exactly
    // the days the fallback is needed.
    let playUri = uri
    const ctype = String(
      (result.headers as any)?.['Content-Type'] ?? (result.headers as any)?.['content-type'] ?? '',
    ).toLowerCase()
    if (ctype.includes('mpeg') || ctype.includes('mp3')) {
      playUri = uri.replace(/\.wav$/, '.mp3')
      await FileSystem.moveAsync({ from: uri, to: playUri })
    }

    const { sound } = await Audio.Sound.createAsync({ uri: playUri }, { shouldPlay: true })
    current = sound
    announce(opts.id || null)

    sound.setOnPlaybackStatusUpdate((status) => {
      if (!status.isLoaded) return
      if (status.didJustFinish) {
        announce(null)
        current = null
        sound.unloadAsync().catch(() => {})
        FileSystem.deleteAsync(playUri, { idempotent: true }).catch(() => {})
      }
    })
    return true
  } catch (e) {
    // Loud while this is new. A silent failure is what hid btoa for a day.
    console.log('[voice] speak failed', e)
    try {
      const { Alert } = require('react-native')
      // The message alone says 'undefined is not a function' with no name.
      // The stack says which line, which is what is actually needed.
      Alert.alert('Voice', String((e as any)?.stack || e).slice(0, 700))
    } catch {}
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

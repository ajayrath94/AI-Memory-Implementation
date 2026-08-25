/**
 * useT — the translation lookup.
 *
 * Language lives locally rather than being fetched per screen: the app has to
 * render in the right language before any network call returns, and someone
 * with no signal should still get their own language rather than a fallback.
 * The backend copy is authoritative when they differ, and is reconciled once
 * at startup.
 */
import { useCallback } from 'react'
import AsyncStorage from '@react-native-async-storage/async-storage'
import { STRINGS, Lang, langFromPref } from '../i18n/strings'
import { useAppStore } from '../store/appStore'
import { API_BASE, API_KEY } from '../constants'

const KEY = 'appLanguage'

export function useT() {
  const lang = useAppStore(s => s.language) as Lang

  return useCallback((key: string, vars?: Record<string, string | number>) => {
    // English is the fallback, not the language of last resort for the user —
    // a missing key showing English is ugly but legible, where showing the key
    // itself is neither.
    let s = STRINGS[lang]?.[key] ?? STRINGS.english[key] ?? key
    if (vars) {
      for (const [k, v] of Object.entries(vars)) {
        s = s.replace(`{${k}}`, String(v))
      }
    }
    return s
  }, [lang])
}

/** Set the language and remember it across launches. */
export async function setLanguage(lang: Lang) {
  useAppStore.getState().setLanguage(lang)
  try {
    await AsyncStorage.setItem(KEY, lang)
  } catch (e) {
    console.log('[i18n] persist failed', e)
  }
}

/**
 * Called once at startup. Reads the stored choice immediately so the first
 * frame is already right, then reconciles with the profile — a caregiver may
 * have changed it from the dashboard, and that should win.
 */
export async function loadLanguage(userId: string) {
  try {
    const saved = await AsyncStorage.getItem(KEY)
    if (saved) useAppStore.getState().setLanguage(saved as Lang)
  } catch {}

  try {
    const res  = await fetch(`${API_BASE}/memory/profile/${userId}`, {
      headers: { 'X-API-Key': API_KEY },
    })
    const data = await res.json()
    if (data?.language_pref) {
      const lang = langFromPref(data.language_pref)
      if (lang !== useAppStore.getState().language) await setLanguage(lang)
    }
  } catch (e) {
    // Offline is not an error here — the stored choice already applied.
    console.log('[i18n] profile read failed', e)
  }
}

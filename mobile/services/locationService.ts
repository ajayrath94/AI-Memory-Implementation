/**
 * Live location — opt-in, foreground only.
 *
 * Design notes:
 *  - Opt-in by default OFF. We never ask for location on first launch.
 *  - Foreground permission only ("when in use"); no background tracking.
 *  - Throttled: at most one sync per SYNC_INTERVAL_MS, so we don't drain
 *    battery or spam the backend on every app resume.
 *  - Every failure path is silent and non-fatal — if location is unavailable
 *    the backend simply falls back to the user's saved profile location.
 */
import * as Location from 'expo-location'
import AsyncStorage from '@react-native-async-storage/async-storage'
import { API_BASE, API_KEY } from '../constants'

const ENABLED_KEY   = 'location:enabled'
const LAST_SYNC_KEY = 'location:lastSyncAt'

const SYNC_INTERVAL_MS = 15 * 60 * 1000   // 15 minutes

export async function isLocationEnabled(): Promise<boolean> {
  try {
    return (await AsyncStorage.getItem(ENABLED_KEY)) === 'true'
  } catch {
    return false
  }
}

export async function setLocationEnabled(enabled: boolean): Promise<void> {
  try {
    await AsyncStorage.setItem(ENABLED_KEY, enabled ? 'true' : 'false')
    if (!enabled) await AsyncStorage.removeItem(LAST_SYNC_KEY)
  } catch (e) {
    console.log('[Location] Failed to persist preference:', e)
  }
}

/** Ask for foreground permission. Returns true if granted. */
export async function requestLocationPermission(): Promise<boolean> {
  try {
    const { status } = await Location.requestForegroundPermissionsAsync()
    return status === 'granted'
  } catch (e) {
    console.log('[Location] Permission request failed:', e)
    return false
  }
}

async function shouldSync(force: boolean): Promise<boolean> {
  if (force) return true
  try {
    const last = await AsyncStorage.getItem(LAST_SYNC_KEY)
    if (!last) return true
    return Date.now() - Number(last) > SYNC_INTERVAL_MS
  } catch {
    return true
  }
}

/**
 * Read the device location and send it to the backend.
 * No-ops quietly if disabled, unpermitted, or recently synced.
 */
export async function syncLocation(
  userId: string,
  opts: { force?: boolean } = {},
): Promise<void> {
  try {
    if (!(await isLocationEnabled())) return
    if (!(await shouldSync(opts.force ?? false))) return

    const { status } = await Location.getForegroundPermissionsAsync()
    if (status !== 'granted') return

    const pos = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.Balanced,   // city-level is all we need
    })

    const res = await fetch(`${API_BASE}/location/gps`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body:    JSON.stringify({
        user_id:  userId,
        lat:      pos.coords.latitude,
        lng:      pos.coords.longitude,
        accuracy: pos.coords.accuracy,
      }),
    })

    if (res.ok) {
      await AsyncStorage.setItem(LAST_SYNC_KEY, String(Date.now()))
    } else {
      console.log('[Location] Backend rejected update:', res.status)
    }
  } catch (e) {
    console.log('[Location] Sync failed:', e)
  }
}

import * as Notifications from 'expo-notifications'
import { Platform } from 'react-native'
import Constants from 'expo-constants'
import { API_BASE } from '../constants'
import { getAuthHeaders } from './authService'

// Show notifications even when the app is foregrounded.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList:   true,
    shouldPlaySound:  true,
    shouldSetBadge:   false,
  }),
})

let _permissionAsked = false

/** Ask for notification permission (once). Returns true if granted. */
export async function ensureNotificationPermission(): Promise<boolean> {
  try {
    const { status: existing } = await Notifications.getPermissionsAsync()
    let status = existing
    if (existing !== 'granted') {
      const req = await Notifications.requestPermissionsAsync()
      status = req.status
    }
    _permissionAsked = true

    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('reminders', {
        name: 'Reminders',
        importance: Notifications.AndroidImportance.HIGH,
        sound: 'default',
      })
    }
    return status === 'granted'
  } catch (e) {
    console.error('[notif] permission error', e)
    return false
  }
}

interface Nudge { at: string; message: string }

/**
 * Schedule one local notification per nudge for a reminder. Each fires at its
 * absolute UTC time with Nancy's pre-written message — works offline, app-closed.
 * Skips nudge times already in the past.
 */
export async function scheduleReminderNudges(
  reminder: { id: string; what: string; nudges?: Nudge[] }
): Promise<number> {
  if (!reminder?.nudges?.length) return 0
  const granted = await ensureNotificationPermission()
  if (!granted) {
    console.log('[notif] permission not granted — skipping scheduling')
    return 0
  }

  const now = Date.now()
  let scheduled = 0
  for (const n of reminder.nudges) {
    const when = new Date(n.at).getTime()
    if (isNaN(when) || when <= now) continue   // skip past/invalid
    try {
      await Notifications.scheduleNotificationAsync({
        content: {
          title: 'Nancy',
          body:  n.message,
          sound: 'default',
          data:  { reminderId: reminder.id, kind: 'reminder' },
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.DATE,
          date: new Date(when),
        },
      })
      scheduled += 1
    } catch (e) {
      console.error('[notif] schedule failed', e)
    }
  }
  console.log(`[notif] scheduled ${scheduled} nudge(s) for "${reminder.what}"`)
  return scheduled
}

/** Cancel all pending local notifications (e.g. on logout). */
export async function cancelAllNotifications() {
  try { await Notifications.cancelAllScheduledNotificationsAsync() }
  catch (e) { console.error('[notif] cancel-all failed', e) }
}


/**
 * Central sync: fetch ALL pending reminders (regular + calendar-sourced) and
 * schedule a local notification for each future one. Cancels previously-scheduled
 * ones first to avoid duplicates. Call on app open — covers reminders added via
 * chat AND calendar events, offline + app-closed delivery.
 */
export async function syncReminderNotifications(
  userId: string, apiBase: string, apiKey: string
): Promise<number> {
  const granted = await ensureNotificationPermission()
  if (!granted) {
    console.log('[notif] permission not granted — skipping sync')
    return 0
  }
  try {
    // clear existing scheduled notifications so we re-schedule cleanly
    await Notifications.cancelAllScheduledNotificationsAsync()

    const res = await fetch(`${apiBase}/reminders/${userId}`, {
      headers: { 'X-API-Key': apiKey },
    })
    const data = await res.json()
    const upcoming = data?.upcoming || []
    const now = Date.now()
    let scheduled = 0

    for (const r of upcoming) {
      // prefer explicit nudges; else a single notification at fire_at
      const points: { at: string; message: string }[] =
        (r.nudges && r.nudges.length)
          ? r.nudges
          : [{ at: r.fire_at_utc, message: reminderMessage(r) }]

      for (const p of points) {
        const when = new Date(p.at).getTime()
        if (isNaN(when) || when <= now) continue
        try {
          await Notifications.scheduleNotificationAsync({
            content: {
              title: 'Nancy',
              body:  p.message,
              sound: 'default',
              data:  { reminderId: r.id, kind: r.source || 'reminder' },
            },
            trigger: {
              type: Notifications.SchedulableTriggerInputTypes.DATE,
              date: new Date(when),
            },
          })
          scheduled += 1
        } catch (e) {
          console.error('[notif] schedule failed', e)
        }
      }
    }
    console.log(`[notif] synced ${scheduled} notification(s) from ${upcoming.length} reminders`)
    return scheduled
  } catch (e) {
    console.error('[notif] sync failed', e)
    return 0
  }
}

/** A warm, simple notification message for a reminder with no pre-written nudge. */
function reminderMessage(r: { what: string; source?: string }): string {
  const what = r.what || 'Reminder'
  if (r.source === 'calendar') return `Yaad hai na? ${what} aaj hai.`
  return `Yaad dila rahi hoon: ${what}`
}

/**
 * Register this device for server-initiated push (alerts, proactive nudges,
 * recommendations). Local notifications already cover reminders known at
 * creation time; this covers what the server decides later.
 */
export async function registerPushToken(userId: string): Promise<string | null> {
  try {
    const granted = await ensureNotificationPermission()
    if (!granted) {
      console.log('[push] permission not granted — no token')
      return null
    }

    const projectId = Constants?.expoConfig?.extra?.eas?.projectId
    if (!projectId) {
      console.error('[push] no EAS projectId in config')
      return null
    }

    const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId })
    if (!token) return null

    const res = await fetch(`${API_BASE}/push/register`, {
      method:  'POST',
      headers: { ...(await getAuthHeaders()) },
      body:    JSON.stringify({
        user_id:    userId,
        expo_token: token,
        platform:   Platform.OS,
      }),
    })
    if (!res.ok) {
      console.error('[push] register failed', res.status)
      return null
    }
    console.log('[push] registered', token.slice(0, 25) + '...')
    return token
  } catch (e) {
    console.error('[push] token error', e)
    return null
  }
}

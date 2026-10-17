import * as Notifications from 'expo-notifications'
import { Platform } from 'react-native'
import Constants from 'expo-constants'
import { API_BASE } from '../constants'
import { getAuthHeaders } from './authService'
import { speak, enqueue, prefetch, pruneVoices, getPreference, wasJustSpoken } from './voiceService'

// Show notifications even when the app is foregrounded.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList:   true,
    shouldPlaySound:  true,
    shouldSetBadge:   false,
  }),
})

/**
 * Tapping a notification opens the conversation.
 *
 * Nothing handled taps at all, so a message she had just read on the lock
 * screen led nowhere — the app opened wherever it had been, and the thing she
 * responded to was gone. The message itself is written to her session when
 * pushed, so the chat already contains it by the time she arrives.
 */
function _userId(): string {
  try {
    const { useAppStore } = require('../store/appStore')
    return useAppStore.getState().userId || 'default'
  } catch { return 'default' }
}

/** A reminder's words, from a notification — local alert or server push. */
function _reminderText(n: Notifications.Notification): string | null {
  const c = n.request.content
  const data = (c.data || {}) as any
  const isReminder = data.kind === 'reminder' || data.kind === 'calendar' || data.kind === 'user'
                     || data.type === 'reminder' || !!data.reminderId || !!data.reminder_id
  return isReminder ? (c.body || null) : null
}

let _handled = ''
async function _onOpened(response: Notifications.NotificationResponse) {
  const id = response.notification.request.identifier
  if (id && id === _handled) return            // cold start: listener and last-response both fire
  _handled = id
  try {
    console.log('[notif] tapped', (response.notification.request.content.data as any)?.type || 'unknown')
    // expo-router is imported lazily: this module is loaded before the router
    // is ready, and importing it at the top throws on a cold start.
    const { router } = require('expo-router')
    router.push('/')
  } catch (e) {
    console.log('[notif] tap handling failed', e)
  }
  // She tapped a reminder: say it. From the voice kept on the phone when it
  // was scheduled, so it speaks without internet too. Always — tapping it is
  // her asking, whatever the chat's playback setting.
  const text = _reminderText(response.notification)
  if (text && !wasJustSpoken(text)) {
    setTimeout(() => { speak(text, { userId: _userId(), intent: 'reminder' }) }, 700)
  }
}

/**
 * Tapping a notification opens the conversation, and a reminder is spoken.
 *
 * Nothing handled taps at all, so a message she had just read on the lock
 * screen led nowhere — the app opened wherever it had been, and the thing she
 * responded to was gone. The message itself is written to her session when
 * pushed, so the chat already contains it by the time she arrives.
 */
Notifications.addNotificationResponseReceivedListener(r => { _onOpened(r) })

// A tap that STARTED the app can arrive before the listener exists.
setTimeout(() => {
  Notifications.getLastNotificationResponseAsync()
    .then(r => {
      if (r && Date.now() - r.notification.date < 5 * 60 * 1000) _onOpened(r)
    })
    .catch(() => {})
}, 1500)

// A reminder that rings while she is in the app is read out straight away
// (after anything already being read), unless she has turned voice off.
Notifications.addNotificationReceivedListener(async n => {
  const text = _reminderText(n)
  if (!text || wasJustSpoken(text)) return
  try {
    const p = await getPreference(_userId())
    if (p.playback === 'off') return
  } catch {}
  enqueue(text, { userId: _userId(), intent: 'reminder' })
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
        // On Android 8+ the channel controls vibration, not the message
        // payload — without a pattern here the phone stays silent however the
        // server sends it. Two firm buzzes: noticeable if the phone is in
        // another room, less alarming than one long one.
        vibrationPattern: [0, 400, 200, 400],
        enableVibrate: true,
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
 * Tell the server these reminders' alerts are on this phone, so it does not
 * push them as well. The phone's own alert and the server's push used to both
 * arrive — two for one reminder. If this call fails, the server simply pushes
 * too: a duplicate, never a missed reminder.
 */
async function markOnDevice(ids: string[]): Promise<void> {
  for (const id of ids) {
    try {
      await fetch(`${API_BASE}/reminders/${id}/on-device`, {
        method:  'POST',
        headers: await getAuthHeaders(),
      })
    } catch (e) {
      console.log('[notif] on-device mark failed', id, e)
    }
  }
}

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
  if (scheduled > 0) await markOnDevice([reminder.id])
  // Its voice, kept now while she is online, so the tap speaks offline.
  for (const n of reminder.nudges) {
    if (new Date(n.at).getTime() > now) prefetch(n.message, { userId: _userId() }).catch(() => {})
  }
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
    const onPhone: string[] = []
    const words: string[] = []

    for (const r of upcoming) {
      const before = scheduled
      // prefer explicit nudges; else a single notification at fire_at
      const points: { at: string; message: string }[] =
        (r.nudges && r.nudges.length)
          ? r.nudges
          : [{ at: r.fire_at_utc, message: reminderMessage(r) }]

      for (const p of points) {
        const when = new Date(p.at).getTime()
        if (isNaN(when) || when <= now) continue
        words.push(p.message)
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
      if (scheduled > before) onPhone.push(r.id)
    }
    console.log(`[notif] synced ${scheduled} notification(s) from ${upcoming.length} reminders`)
    await markOnDevice(onPhone)
    // The voices for what is coming, kept on the phone; the rest let go.
    pruneVoices(words).catch(() => {})
    for (const w of words) prefetch(w, { userId }).catch(() => {})
    return scheduled
  } catch (e) {
    console.error('[notif] sync failed', e)
    return 0
  }
}

/** A warm, simple notification message for a reminder with no pre-written nudge. */
function reminderMessage(r: { what: string; source?: string }): string {
  // The same words the server writes into her chat when it fires
  // (reminder_engine.fire_due), so a reminder spoken on her tap is known
  // when the chat shows it, and is not read out twice.
  return `Yaad dila rahi hoon: ${r.what || 'Reminder'}`
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

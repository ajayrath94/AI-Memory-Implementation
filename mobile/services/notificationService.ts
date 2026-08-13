import * as Notifications from 'expo-notifications'
import { Platform } from 'react-native'

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

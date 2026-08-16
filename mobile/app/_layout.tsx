import './_errorHandler'
import React, { useState, useRef, useCallback, useEffect} from 'react'
import {
  View, Text, TouchableOpacity, StyleSheet,
  Animated, Dimensions, Pressable,
} from 'react-native'
import { Slot, useRouter, usePathname } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import { SafeAreaView } from 'react-native-safe-area-context'
import { Colors, Spacing, Radius, API_BASE, API_KEY } from '../constants'
import { useAppStore } from '../store/appStore'

const COLLAPSED_W = 56
const EXPANDED_W  = 200
const ANIM_MS     = 250

const NAV_ITEMS = [
  { path: '/',         icon: 'chatbubble-outline',    label: 'Chat'     },
  { path: '/sessions', icon: 'time-outline',          label: 'Sessions' },
  { path: '/memory',   icon: 'hardware-chip-outline', label: 'Memory'   },
  { path: '/reminders', icon: 'alarm-outline',          label: 'Reminders'},
  { path: '/calendar', icon: 'calendar-outline',       label: 'Calendar' },
  { path: '/profile',  icon: 'person-outline',        label: 'Profile'  },
  { path: '/settings', icon: 'settings-outline',      label: 'Settings' },
]

function isLightHex(hex: string): boolean {
  const h = hex.replace('#', '')
  const r = parseInt(h.substring(0, 2), 16)
  const g = parseInt(h.substring(2, 4), 16)
  const b = parseInt(h.substring(4, 6), 16)
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.5
}

import { syncReminderNotifications } from '../services/notificationService'

export default function RootLayout() {
  // ── All hooks at top, no conditionals before them ──
  const router   = useRouter()
  const pathname = usePathname()
  const bgColor  = useAppStore(s => s.bgColor)
  const [open, setOpen] = useState(false)
  const anim     = useRef(new Animated.Value(COLLAPSED_W)).current
  const fadeAnim = useRef(new Animated.Value(0)).current

  const isHidden = pathname.startsWith('/caregiver') ||
                   pathname === '/persona-setup' ||
                   pathname === '/onboarding'

  const toggle = useCallback(() => {
    const toW    = open ? COLLAPSED_W : EXPANDED_W
    const toFade = open ? 0 : 1
    Animated.parallel([
      Animated.spring(anim, { toValue: toW, useNativeDriver: false, damping: 20, stiffness: 200 }),
      Animated.timing(fadeAnim, { toValue: toFade, duration: ANIM_MS, useNativeDriver: true }),
    ]).start()
    setOpen(o => !o)
  }, [open, anim, fadeAnim])

  const navigate = useCallback((path: string) => {
    router.push(path as any)
    if (open) toggle()
  }, [router, open, toggle])

  const userId = useAppStore(s => s.userId)
  useEffect(() => {
    if (userId) {
      syncReminderNotifications(userId, API_BASE, API_KEY)
    }
  }, [userId])

  const resolvedBg   = bgColor || Colors.bg
  const isSidebarLight = isLightHex(resolvedBg)

  // ── Full screen for hidden routes ──
  if (isHidden) {
    return (
      <SafeAreaView style={[styles.safe, { backgroundColor: resolvedBg }]} edges={['top', 'bottom']}>
        <Slot />
      </SafeAreaView>
    )
  }

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: resolvedBg }]} edges={['top', 'bottom']}>
      <View style={styles.root}>

        {/* Overlay */}
        {open && (
          <Pressable style={styles.overlay} onPress={toggle} />
        )}

        {/* Sidebar */}
        <Animated.View style={[styles.sidebar, { width: anim, backgroundColor: isSidebarLight ? '#f0f0f0' : '#0d0d0d' }]}>

          {/* Logo */}
          <TouchableOpacity style={styles.logoBtn} onPress={toggle} activeOpacity={0.8}>
            <View style={styles.logo}>
              <Text style={styles.logoText}>N</Text>
            </View>
            <Animated.Text style={[styles.appName, { opacity: fadeAnim }]} numberOfLines={1}>
              Nancy
            </Animated.Text>
          </TouchableOpacity>

          <View style={styles.divider} />

          {/* Nav items */}
          <View style={styles.navList}>
            {NAV_ITEMS.map(item => {
              const isActive = pathname === item.path ||
                (item.path !== '/' && pathname.startsWith(item.path))
              return (
                <TouchableOpacity
                  key={item.path}
                  style={[styles.navItem, isActive && styles.navItemActive]}
                  onPress={() => navigate(item.path)}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name={item.icon as any}
                    size={20}
                    color={isActive ? Colors.accent : Colors.textMuted}
                  />
                  <Animated.Text
                    style={[styles.navLabel, isActive && styles.navLabelActive, { opacity: fadeAnim }]}
                    numberOfLines={1}
                  >
                    {item.label}
                  </Animated.Text>
                </TouchableOpacity>
              )
            })}
          </View>

          {/* Online dot */}
          <View style={styles.sidebarBottom}>
            <View style={styles.onlineDot} />
            <Animated.Text style={[styles.onlineText, { opacity: fadeAnim }]} numberOfLines={1}>
              Online
            </Animated.Text>
          </View>

        </Animated.View>

        {/* Main content */}
        <View style={[styles.content, { backgroundColor: resolvedBg }]}>
          <Slot />
        </View>

      </View>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe:    { flex: 1, backgroundColor: Colors.bg },
  root:    { flex: 1, flexDirection: 'row' },

  overlay: {
    position:        'absolute',
    top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: '#00000055',
    zIndex:          10,
  },

  sidebar: {
    backgroundColor:  '#0d0d0d',
    borderRightWidth: 0.5,
    borderRightColor: Colors.border,
    paddingVertical:  Spacing.md,
    paddingHorizontal: 8,
    overflow:         'hidden',
    zIndex:           20,
  },

  logoBtn: {
    flexDirection:   'row',
    alignItems:      'center',
    gap:             Spacing.md,
    paddingVertical: Spacing.sm,
    paddingHorizontal: 4,
    marginBottom:    Spacing.sm,
  },
  logo: {
    width:           36,
    height:          36,
    borderRadius:    10,
    backgroundColor: Colors.accent + '22',
    borderWidth:     1.5,
    borderColor:     Colors.accent + '55',
    alignItems:      'center',
    justifyContent:  'center',
    flexShrink:      0,
  },
  logoText: { fontSize: 16, fontWeight: '700', color: Colors.accent },
  appName:  { fontSize: 16, fontWeight: '700', color: Colors.text, flexShrink: 0 },

  divider: { height: 0.5, backgroundColor: Colors.border, marginBottom: Spacing.sm },

  navList:  { flex: 1, gap: 2 },
  navItem: {
    flexDirection:    'row',
    alignItems:       'center',
    gap:              Spacing.md,
    paddingVertical:  11,
    paddingHorizontal: 8,
    borderRadius:     Radius.md,
  },
  navItemActive: { backgroundColor: Colors.accent + '15' },
  navLabel:      { fontSize: 15, color: Colors.textMuted, fontWeight: '500', flexShrink: 0 },
  navLabelActive:{ color: Colors.text, fontWeight: '600' },

  sidebarBottom: {
    flexDirection:    'row',
    alignItems:       'center',
    gap:              Spacing.md,
    paddingHorizontal: 8,
    paddingVertical:  Spacing.sm,
  },
  onlineDot:  { width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.accentGreen, flexShrink: 0 },
  onlineText: { fontSize: 13, color: Colors.textMuted },

  content: { flex: 1, backgroundColor: Colors.bg },
})

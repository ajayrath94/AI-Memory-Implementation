import React, { useState, useRef } from 'react'
import {
  View, Text, TouchableOpacity, StyleSheet,
  Animated, Dimensions, Pressable,
} from 'react-native'
import { Slot, useRouter, usePathname } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import { Colors, Spacing, Radius } from '../constants'
import { useAppStore } from '../store/appStore'
import { isLoggedIn, getCurrentUser } from '../services/authService'
import { useEffect } from 'react'
import { SafeAreaView } from 'react-native-safe-area-context'

const COLLAPSED_W = 56
const EXPANDED_W  = 200
const ANIM_MS     = 250

const NAV_ITEMS = [
  { path: '/',         icon: 'chatbubble-outline',    label: 'Chat'     },
  { path: '/sessions', icon: 'time-outline',          label: 'Sessions' },
  { path: '/memory',   icon: 'hardware-chip-outline', label: 'Memory'   },
  { path: '/profile',  icon: 'person-outline',        label: 'Profile'  },
  { path: '/settings', icon: 'settings-outline',      label: 'Settings' },
]

export default function RootLayout() {
  const router    = useRouter()
  const pathname  = usePathname()
  const [open,        setOpen]        = useState(false)
  const [authChecked, setAuthChecked] = useState(false)

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const loggedIn = await isLoggedIn()
        if (loggedIn) {
          const user = await getCurrentUser()
          if (user) setUserId(user.id)
        } else {
          router.replace('/onboarding')
        }
      } catch {
        router.replace('/onboarding')
      } finally {
        setAuthChecked(true)
      }
    }
    checkAuth()
  }, [])

  const { setUserId } = useAppStore()
  const anim      = useRef(new Animated.Value(COLLAPSED_W)).current
  const fadeAnim  = useRef(new Animated.Value(0)).current

  if (!authChecked) return null

  const isHidden  = pathname.startsWith('/caregiver') || pathname === '/persona-setup'

  const toggle = () => {
    const toW    = open ? COLLAPSED_W : EXPANDED_W
    const toFade = open ? 0 : 1
    Animated.parallel([
      Animated.spring(anim, { toValue: toW, useNativeDriver: false, damping: 20, stiffness: 200 }),
      Animated.timing(fadeAnim, { toValue: toFade, duration: ANIM_MS, useNativeDriver: true }),
    ]).start()
    setOpen(!open)
  }

  const navigate = (path: string) => {
    router.push(path as any)
    if (open) toggle()
  }

  if (isHidden) {
    return (
      <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
        <Slot />
      </SafeAreaView>
    )
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.root}>

        {/* Overlay — tap to close */}
        {open && (
          <Pressable style={styles.overlay} onPress={toggle} />
        )}

        {/* Sidebar */}
        <Animated.View style={[styles.sidebar, { width: anim }]}>

          {/* Logo / toggle button */}
          <TouchableOpacity style={styles.logoBtn} onPress={toggle} activeOpacity={0.8}>
            <View style={styles.logo}>
              <Text style={styles.logoText}>N</Text>
            </View>
            <Animated.Text style={[styles.appName, { opacity: fadeAnim }]}>
              Nancy
            </Animated.Text>
          </TouchableOpacity>

          {/* Divider */}
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

          {/* Bottom — online dot */}
          <View style={styles.sidebarBottom}>
            <View style={styles.onlineDot} />
            <Animated.Text style={[styles.onlineText, { opacity: fadeAnim }]}>
              Online
            </Animated.Text>
          </View>

        </Animated.View>

        {/* Main content */}
        <View style={styles.content}>
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
    top:             0, left: 0, right: 0, bottom: 0,
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
    flexDirection: 'row',
    alignItems:    'center',
    gap:           Spacing.md,
    paddingVertical: Spacing.sm,
    paddingHorizontal: 4,
    marginBottom:  Spacing.sm,
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
    flexDirection:   'row',
    alignItems:      'center',
    gap:             Spacing.md,
    paddingVertical: 11,
    paddingHorizontal: 8,
    borderRadius:    Radius.md,
  },
  navItemActive: { backgroundColor: Colors.accent + '15' },

  navLabel: {
    fontSize:   15,
    color:      Colors.textMuted,
    fontWeight: '500',
    flexShrink: 0,
  },
  navLabelActive: { color: Colors.text, fontWeight: '600' },

  sidebarBottom: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           Spacing.md,
    paddingHorizontal: 8,
    paddingVertical:   Spacing.sm,
  },
  onlineDot: {
    width: 8, height: 8, borderRadius: 4,
    backgroundColor: Colors.accentGreen,
    flexShrink: 0,
  },
  onlineText: { fontSize: 13, color: Colors.textMuted },

  content: { flex: 1, backgroundColor: Colors.bg },
})

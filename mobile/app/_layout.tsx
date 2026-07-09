import React, { useState } from 'react'
import { View, Text, TouchableOpacity, StyleSheet, Animated, Dimensions } from 'react-native'
import { Slot, useRouter, usePathname } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import { Colors, Spacing, Radius, Typography } from '../constants'
import { SafeAreaView } from 'react-native-safe-area-context'

const { width } = Dimensions.get('window')
const SIDEBAR_WIDTH = 72

const NAV_ITEMS = [
  { path: '/',         icon: 'chatbubble-outline',      label: 'Chat'     },
  { path: '/sessions', icon: 'time-outline',            label: 'Sessions' },
  { path: '/memory',   icon: 'hardware-chip-outline',   label: 'Memory'   },
  { path: '/profile',  icon: 'person-outline',          label: 'Profile'  },
  { path: '/settings', icon: 'settings-outline',        label: 'Settings' },
]

export default function RootLayout() {
  const router   = useRouter()
  const pathname = usePathname()

  const isHidden = pathname.startsWith('/caregiver') || pathname === '/persona-setup'

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.container}>

        {/* Left sidebar — hidden on caregiver/persona screens */}
        {!isHidden && (
          <View style={styles.sidebar}>
            {/* Nancy logo */}
            <View style={styles.logo}>
              <Text style={styles.logoText}>N</Text>
            </View>

            <View style={styles.navItems}>
              {NAV_ITEMS.map(item => {
                const isActive = pathname === item.path ||
                  (item.path !== '/' && pathname.startsWith(item.path))
                return (
                  <TouchableOpacity
                    key={item.path}
                    style={[styles.navItem, isActive && styles.navItemActive]}
                    onPress={() => router.push(item.path as any)}
                    activeOpacity={0.7}
                  >
                    <Ionicons
                      name={item.icon as any}
                      size={22}
                      color={isActive ? Colors.accent : Colors.textMuted}
                    />
                    <Text style={[styles.navLabel, isActive && styles.navLabelActive]}>
                      {item.label}
                    </Text>
                  </TouchableOpacity>
                )
              })}
            </View>

            {/* Online indicator */}
            <View style={styles.sidebarBottom}>
              <View style={styles.onlineDot} />
            </View>
          </View>
        )}

        {/* Main content */}
        <View style={[styles.content, isHidden && styles.contentFull]}>
          <Slot />
        </View>

      </View>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe:      { flex: 1, backgroundColor: Colors.bg },
  container: { flex: 1, flexDirection: 'row' },

  sidebar: {
    width:           SIDEBAR_WIDTH,
    backgroundColor: '#0d0d0d',
    borderRightWidth: 0.5,
    borderRightColor: Colors.border,
    alignItems:      'center',
    paddingVertical: Spacing.md,
    gap:             Spacing.sm,
  },

  logo: {
    width:           40,
    height:          40,
    borderRadius:    12,
    backgroundColor: Colors.accent + '22',
    borderWidth:     1.5,
    borderColor:     Colors.accent + '44',
    alignItems:      'center',
    justifyContent:  'center',
    marginBottom:    Spacing.md,
  },
  logoText: { fontSize: 18, fontWeight: '700', color: Colors.accent },

  navItems: { flex: 1, gap: 4, width: '100%', paddingHorizontal: 8 },

  navItem: {
    alignItems:      'center',
    justifyContent:  'center',
    paddingVertical: 10,
    borderRadius:    Radius.md,
    gap:             4,
  },
  navItemActive: {
    backgroundColor: Colors.accent + '15',
  },
  navLabel: {
    fontSize:   9,
    color:      Colors.textMuted,
    fontWeight: '500',
    textAlign:  'center',
  },
  navLabelActive: { color: Colors.accent },

  sidebarBottom: {
    paddingBottom: Spacing.sm,
    alignItems:    'center',
  },
  onlineDot: {
    width:           8,
    height:          8,
    borderRadius:    4,
    backgroundColor: Colors.accentGreen,
  },

  content:     { flex: 1, backgroundColor: Colors.bg },
  contentFull: { flex: 1 },
})

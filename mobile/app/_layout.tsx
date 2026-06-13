import { Tabs } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import { Colors } from '../constants'

export default function RootLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown:     false,
        tabBarStyle: {
          backgroundColor: '#0f0f0f',
          borderTopColor:  '#1a1a1a',
          borderTopWidth:  1,
          paddingBottom:   8,
          paddingTop:      6,
          height:          60,
        },
        tabBarActiveTintColor:   Colors.accent,
        tabBarInactiveTintColor: Colors.textMuted,
        tabBarLabelStyle: {
          fontSize:   11,
          fontWeight: '500',
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Chat',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="chatbubble-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="sessions"
        options={{
          title: 'Sessions',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="time-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="memory"
        options={{
          title: 'Memory',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="brain-outline" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
  )
}

import { Stack } from 'expo-router'
import { Colors } from '../constants'

export default function RootLayout() {
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: Colors.bg } }}>
      <Stack.Screen name="index" />
    </Stack>
  )
}

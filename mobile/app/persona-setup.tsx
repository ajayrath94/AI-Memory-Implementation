import { useAppStore } from '../store/appStore'
import PersonaSetup from '../components/persona/PersonaSetup'
import { router } from 'expo-router'

export default function PersonaSetupScreen() {
  const { userId } = useAppStore()
  return (
    <PersonaSetup
      userId={userId}
      onSaved={() => router.back()}
    />
  )
}

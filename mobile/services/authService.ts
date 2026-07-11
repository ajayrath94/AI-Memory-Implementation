/**
 * Nancy AI — Auth Service
 * Handles JWT token storage, refresh, and user session management
 * Uses expo-secure-store for encrypted token storage
 */

import * as SecureStore from 'expo-secure-store'
import { API_BASE, API_KEY } from '../constants'

const TOKEN_KEY    = 'nancy_access_token'
const REFRESH_KEY  = 'nancy_refresh_token'
const USER_KEY     = 'nancy_user'

export interface NancyUser {
  id:           string
  phone?:       string
  email?:       string
  role:         'user' | 'caregiver'
  created_at?:  string
}

export interface AuthSession {
  access_token:  string
  refresh_token: string
  user:          NancyUser
  expires_at:    number
}

// ── Token Storage ──────────────────────────────────────────────────────────────

export async function saveSession(session: AuthSession): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY,   session.access_token)
  await SecureStore.setItemAsync(REFRESH_KEY, session.refresh_token)
  await SecureStore.setItemAsync(USER_KEY,    JSON.stringify(session.user))
}

export async function getAccessToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY)
  } catch {
    return null
  }
}

export async function getRefreshToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(REFRESH_KEY)
  } catch {
    return null
  }
}

export async function getCurrentUser(): Promise<NancyUser | null> {
  try {
    const raw = await SecureStore.getItemAsync(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export async function clearSession(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY)
  await SecureStore.deleteItemAsync(REFRESH_KEY)
  await SecureStore.deleteItemAsync(USER_KEY)
}

// ── Auth Headers ───────────────────────────────────────────────────────────────

export async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken()
  if (token) {
    return {
      'Content-Type':  'application/json',
      'Authorization': `Bearer ${token}`,
    }
  }
  // Fallback to API key for dev/testing
  return {
    'Content-Type': 'application/json',
    'X-API-Key':    API_KEY,
  }
}

// ── Phone OTP Auth (elderly users) ────────────────────────────────────────────

export async function requestOTP(phone: string): Promise<{ success: boolean; error?: string }> {
  try {
    const res  = await fetch(`${API_BASE}/auth/user/otp-request`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body:    JSON.stringify({ phone }),
    })
    const data = await res.json()
    return { success: res.ok, error: data.detail }
  } catch (e: any) {
    return { success: false, error: e.message }
  }
}

export async function verifyOTP(phone: string, otp: string): Promise<{ success: boolean; user?: NancyUser; error?: string }> {
  try {
    const res  = await fetch(`${API_BASE}/auth/user/otp-verify`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body:    JSON.stringify({ phone, token: otp }),
    })
    const data = await res.json()

    if (res.ok && data.session) {
      const user: NancyUser = {
        id:    data.session.user.id,
        phone: data.session.user.phone,
        role:  'user',
      }
      await saveSession({
        access_token:  data.session.access_token,
        refresh_token: data.session.refresh_token,
        user,
        expires_at:    data.session.expires_at,
      })
      return { success: true, user }
    }
    return { success: false, error: data.detail || 'OTP verification failed' }
  } catch (e: any) {
    return { success: false, error: e.message }
  }
}

// ── Caregiver Email Auth ───────────────────────────────────────────────────────

export async function caregiverLogin(email: string, password: string): Promise<{ success: boolean; user?: NancyUser; error?: string }> {
  try {
    const res  = await fetch(`${API_BASE}/auth/caregiver/login`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body:    JSON.stringify({ email, password }),
    })
    const data = await res.json()

    if (res.ok && data.session) {
      const user: NancyUser = {
        id:    data.caregiver_id,
        email: email,
        role:  'caregiver',
      }
      await saveSession({
        access_token:  data.session.access_token,
        refresh_token: data.session.refresh_token,
        user,
        expires_at:    data.session.expires_at || 0,
      })
      return { success: true, user }
    }
    return { success: false, error: data.detail || 'Login failed' }
  } catch (e: any) {
    return { success: false, error: e.message }
  }
}

// ── Token refresh ──────────────────────────────────────────────────────────────

export async function refreshSession(): Promise<boolean> {
  try {
    const refresh_token = await getRefreshToken()
    if (!refresh_token) return false

    const res  = await fetch(`${API_BASE}/auth/refresh`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body:    JSON.stringify({ refresh_token }),
    })
    const data = await res.json()

    if (res.ok && data.access_token) {
      await SecureStore.setItemAsync(TOKEN_KEY, data.access_token)
      if (data.refresh_token) {
        await SecureStore.setItemAsync(REFRESH_KEY, data.refresh_token)
      }
      return true
    }
    return false
  } catch {
    return false
  }
}

// ── Logout ────────────────────────────────────────────────────────────────────

export async function logout(): Promise<void> {
  try {
    const token = await getAccessToken()
    if (token) {
      await fetch(`${API_BASE}/auth/caregiver/logout`, {
        method:  'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'X-API-Key': API_KEY },
      })
    }
  } catch {}
  await clearSession()
}

// ── Check if logged in ─────────────────────────────────────────────────────────

export async function isLoggedIn(): Promise<boolean> {
  const token = await getAccessToken()
  return !!token
}

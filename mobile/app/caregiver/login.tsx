import React, { useState } from 'react'
import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, SafeAreaView, KeyboardAvoidingView,
  Platform, ActivityIndicator, Alert,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { router } from 'expo-router'
import { useTheme } from '../../hooks/useTheme'
import { Colors, Typography, Spacing, Radius, API_BASE } from '../../constants'

export default function LoginScreen() {
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [loading,  setLoading]  = useState(false)
  const [showPass, setShowPass] = useState(false)

  const login = async () => {
    if (!email.trim() || !password.trim()) {
      Alert.alert('Missing fields', 'Please enter your email and password.')
      return
    }
    setLoading(true)
    try {
      const res  = await fetch(`${API_BASE}/auth/caregiver/login`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ email: email.trim().toLowerCase(), password }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Login failed')

      // TODO: store token in secure store
      router.replace('/caregiver/dashboard')
    } catch (e: any) {
      Alert.alert('Login failed', e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />
      <KeyboardAvoidingView
        style={styles.kav}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >

        {/* Brand */}
        <View style={styles.brand}>
          <View style={styles.logo}>
            <Text style={styles.logoText}>N</Text>
          </View>
          <Text style={styles.brandName}>Nancy</Text>
          <Text style={styles.brandTagline}>Caregiver Portal</Text>
        </View>

        {/* Form */}
        <View style={styles.form}>
          <Text style={styles.formTitle}>Welcome back</Text>
          <Text style={styles.formSubtitle}>Sign in to monitor your loved ones</Text>

          <View style={styles.field}>
            <Text style={styles.fieldLabel}>Email</Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder="you@example.com"
              placeholderTextColor={Colors.textHint}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>

          <View style={styles.field}>
            <Text style={styles.fieldLabel}>Password</Text>
            <View style={styles.passwordWrap}>
              <TextInput
                style={[styles.input, styles.passwordInput]}
                value={password}
                onChangeText={setPassword}
                placeholder="••••••••"
                placeholderTextColor={Colors.textHint}
                secureTextEntry={!showPass}
                autoCapitalize="none"
              />
              <TouchableOpacity
                style={styles.eyeBtn}
                onPress={() => setShowPass(!showPass)}
              >
                <Text style={styles.eyeText}>{showPass ? '🙈' : '👁'}</Text>
              </TouchableOpacity>
            </View>
          </View>

          <TouchableOpacity
            style={[styles.btn, loading && styles.btnLoading]}
            onPress={login}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.btnText}>Sign in</Text>
            }
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.linkBtn}
            onPress={() => router.push('/caregiver/signup')}
          >
            <Text style={styles.linkText}>
              New here? <Text style={styles.linkHighlight}>Create an account</Text>
            </Text>
          </TouchableOpacity>
        </View>

      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  kav:  { flex: 1, justifyContent: 'center', paddingHorizontal: Spacing.xl },

  // Brand
  brand: { alignItems: 'center', marginBottom: Spacing.xxl * 1.5 },
  logo: {
    width:           64,
    height:          64,
    borderRadius:    32,
    backgroundColor: Colors.accent + '22',
    borderWidth:     1.5,
    borderColor:     Colors.accent + '44',
    alignItems:      'center',
    justifyContent:  'center',
    marginBottom:    Spacing.md,
  },
  logoText:      { fontSize: 28, fontWeight: '700', color: Colors.accent },
  brandName:     { ...Typography.display, color: Colors.text },
  brandTagline:  { ...Typography.label, color: Colors.textMuted, marginTop: 4 },

  // Form
  form: {
    backgroundColor: Colors.bgCard,
    borderRadius:    Radius.xl,
    padding:         Spacing.xl,
    borderWidth:     0.5,
    borderColor:     Colors.border,
    gap:             Spacing.lg,
  },
  formTitle:    { ...Typography.title, color: Colors.text },
  formSubtitle: { ...Typography.body, color: Colors.textMuted, marginTop: -Spacing.sm },

  // Fields
  field:        { gap: Spacing.xs },
  fieldLabel:   { ...Typography.label, color: Colors.textSecond },
  input: {
    backgroundColor:   Colors.bgInput,
    color:             Colors.text,
    borderWidth:       0.5,
    borderColor:       Colors.border,
    borderRadius:      Radius.md,
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.md,
    fontSize:          16,
  },
  passwordWrap:  { position: 'relative' },
  passwordInput: { paddingRight: 50 },
  eyeBtn: {
    position: 'absolute',
    right:    Spacing.md,
    top:      0, bottom: 0,
    justifyContent: 'center',
  },
  eyeText: { fontSize: 16 },

  // Button
  btn: {
    backgroundColor: Colors.accent,
    borderRadius:    Radius.md,
    paddingVertical: Spacing.lg,
    alignItems:      'center',
    marginTop:       Spacing.sm,
  },
  btnLoading: { opacity: 0.7 },
  btnText:    { color: '#fff', fontSize: 16, fontWeight: '600' },

  // Link
  linkBtn:       { alignItems: 'center', paddingVertical: Spacing.sm },
  linkText:      { ...Typography.body, color: Colors.textMuted },
  linkHighlight: { color: Colors.accent, fontWeight: '600' },
})

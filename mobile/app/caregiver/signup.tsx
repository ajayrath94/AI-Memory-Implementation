import React, { useState } from 'react'
import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, SafeAreaView, KeyboardAvoidingView,
  Platform, ActivityIndicator, Alert, ScrollView,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { router } from 'expo-router'
import { useTheme } from '../../hooks/useTheme'
import { Colors, Typography, Spacing, Radius, API_BASE } from '../../constants'

export default function SignupScreen() {
  const [name,     setName]     = useState('')
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [phone,    setPhone]    = useState('')
  const [loading,  setLoading]  = useState(false)

  const signup = async () => {
    if (!name.trim() || !email.trim() || !password.trim()) {
      Alert.alert('Missing fields', 'Please fill in all required fields.')
      return
    }
    if (password.length < 8) {
      Alert.alert('Weak password', 'Password must be at least 8 characters.')
      return
    }
    setLoading(true)
    try {
      const res  = await fetch(`${API_BASE}/auth/caregiver/signup`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          name:     name.trim(),
          email:    email.trim().toLowerCase(),
          password,
          phone:    phone.trim() || null,
          org_type: 'family',
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Signup failed')

      Alert.alert(
        'Account created!',
        'Welcome to Nancy. You can now add your family members.',
        [{ text: 'Get started', onPress: () => router.replace('/caregiver/dashboard') }]
      )
    } catch (e: any) {
      Alert.alert('Signup failed', e.message)
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
        <ScrollView
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.scroll}
        >

          {/* Brand */}
          <View style={styles.brand}>
            <View style={styles.logo}>
              <Text style={styles.logoText}>N</Text>
            </View>
            <Text style={styles.brandName}>Nancy</Text>
            <Text style={styles.brandTagline}>Create caregiver account</Text>
          </View>

          {/* Form */}
          <View style={styles.form}>
            <Text style={styles.formTitle}>Let's get you set up</Text>
            <Text style={styles.formSubtitle}>
              You'll be able to add family members and receive alerts
            </Text>

            <View style={styles.field}>
              <Text style={styles.fieldLabel}>Full name *</Text>
              <TextInput
                style={styles.input}
                value={name}
                onChangeText={setName}
                placeholder="Vikram Sharma"
                placeholderTextColor={Colors.textHint}
                autoCapitalize="words"
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.fieldLabel}>Email *</Text>
              <TextInput
                style={styles.input}
                value={email}
                onChangeText={setEmail}
                placeholder="vikram@example.com"
                placeholderTextColor={Colors.textHint}
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.fieldLabel}>Password *</Text>
              <TextInput
                style={styles.input}
                value={password}
                onChangeText={setPassword}
                placeholder="Min 8 characters"
                placeholderTextColor={Colors.textHint}
                secureTextEntry
                autoCapitalize="none"
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.fieldLabel}>Phone (optional)</Text>
              <TextInput
                style={styles.input}
                value={phone}
                onChangeText={setPhone}
                placeholder="+91 98765 43210"
                placeholderTextColor={Colors.textHint}
                keyboardType="phone-pad"
              />
              <Text style={styles.fieldHint}>For voice alerts when something urgent is detected</Text>
            </View>

            <TouchableOpacity
              style={[styles.btn, loading && styles.btnLoading]}
              onPress={signup}
              disabled={loading}
              activeOpacity={0.85}
            >
              {loading
                ? <ActivityIndicator color="#fff" />
                : <Text style={styles.btnText}>Create account</Text>
              }
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.linkBtn}
              onPress={() => router.back()}
            >
              <Text style={styles.linkText}>
                Already have an account? <Text style={styles.linkHighlight}>Sign in</Text>
              </Text>
            </TouchableOpacity>

            <Text style={styles.privacy}>
              By creating an account you agree that Nancy handles your family's
              data with care. You can delete all data at any time from Settings.
            </Text>
          </View>

        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: Colors.bg },
  kav:    { flex: 1 },
  scroll: { paddingHorizontal: Spacing.xl, paddingVertical: Spacing.xl },

  brand: { alignItems: 'center', marginBottom: Spacing.xxl },
  logo: {
    width:           56,
    height:          56,
    borderRadius:    28,
    backgroundColor: Colors.accent + '22',
    borderWidth:     1.5,
    borderColor:     Colors.accent + '44',
    alignItems:      'center',
    justifyContent:  'center',
    marginBottom:    Spacing.md,
  },
  logoText:     { fontSize: 24, fontWeight: '700', color: Colors.accent },
  brandName:    { ...Typography.display, color: Colors.text },
  brandTagline: { ...Typography.label, color: Colors.textMuted, marginTop: 4 },

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

  field:      { gap: Spacing.xs },
  fieldLabel: { ...Typography.label, color: Colors.textSecond },
  fieldHint:  { ...Typography.caption, color: Colors.textMuted, marginTop: 4 },
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

  btn: {
    backgroundColor: Colors.accent,
    borderRadius:    Radius.md,
    paddingVertical: Spacing.lg,
    alignItems:      'center',
    marginTop:       Spacing.sm,
  },
  btnLoading:    { opacity: 0.7 },
  btnText:       { color: '#fff', fontSize: 16, fontWeight: '600' },

  linkBtn:       { alignItems: 'center', paddingVertical: Spacing.sm },
  linkText:      { ...Typography.body, color: Colors.textMuted },
  linkHighlight: { color: Colors.accent, fontWeight: '600' },

  privacy: {
    ...Typography.caption,
    color:     Colors.textMuted,
    textAlign: 'center',
    lineHeight: 18,
    marginTop: Spacing.sm,
  },
})

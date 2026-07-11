import React, { useState } from 'react'
import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, SafeAreaView, ActivityIndicator,
  KeyboardAvoidingView, Platform, Alert,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { router } from 'expo-router'
import { Colors, Typography, Spacing, Radius } from '../constants'
import { requestOTP, verifyOTP } from '../services/authService'
import { useAppStore } from '../store/appStore'

type Step = 'phone' | 'otp' | 'done'

export default function OnboardingScreen() {
  const { setUserId } = useAppStore()
  const [step,    setStep]    = useState<Step>('phone')
  const [phone,   setPhone]   = useState('')
  const [otp,     setOtp]     = useState('')
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')

  const handleRequestOTP = async () => {
    if (!phone.trim() || phone.length < 10) {
      setError('Please enter a valid phone number')
      return
    }
    setLoading(true)
    setError('')
    const formatted = phone.startsWith('+') ? phone : `+91${phone}`
    const result    = await requestOTP(formatted)
    setLoading(false)
    if (result.success) {
      setStep('otp')
    } else {
      setError(result.error || 'Failed to send OTP')
    }
  }

  const handleVerifyOTP = async () => {
    if (!otp.trim() || otp.length < 6) {
      setError('Please enter the 6-digit OTP')
      return
    }
    setLoading(true)
    setError('')
    const formatted = phone.startsWith('+') ? phone : `+91${phone}`
    const result    = await verifyOTP(formatted, otp)
    setLoading(false)
    if (result.success && result.user) {
      setUserId(result.user.id)
      setStep('done')
      setTimeout(() => router.replace('/'), 1500)
    } else {
      setError(result.error || 'Invalid OTP')
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.logo}>
            <Text style={styles.logoText}>N</Text>
          </View>
          <Text style={styles.title}>Welcome to Nancy</Text>
          <Text style={styles.subtitle}>
            {step === 'phone' && "Enter your phone number to get started"}
            {step === 'otp'   && `We sent a code to ${phone}`}
            {step === 'done'  && "You're all set! 🎉"}
          </Text>
        </View>

        {/* Steps */}
        {step === 'phone' && (
          <View style={styles.form}>
            <Text style={styles.label}>Phone number</Text>
            <View style={styles.phoneRow}>
              <View style={styles.countryCode}>
                <Text style={styles.countryCodeText}>+91</Text>
              </View>
              <TextInput
                style={styles.phoneInput}
                value={phone}
                onChangeText={setPhone}
                placeholder="10-digit number"
                placeholderTextColor={Colors.textHint}
                keyboardType="phone-pad"
                maxLength={10}
                autoFocus
              />
            </View>
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <TouchableOpacity
              style={[styles.btn, loading && { opacity: 0.7 }]}
              onPress={handleRequestOTP}
              disabled={loading}
            >
              {loading
                ? <ActivityIndicator color="#fff" />
                : <Text style={styles.btnText}>Send OTP</Text>
              }
            </TouchableOpacity>
          </View>
        )}

        {step === 'otp' && (
          <View style={styles.form}>
            <Text style={styles.label}>Enter OTP</Text>
            <TextInput
              style={[styles.phoneInput, styles.otpInput]}
              value={otp}
              onChangeText={setOtp}
              placeholder="6-digit code"
              placeholderTextColor={Colors.textHint}
              keyboardType="number-pad"
              maxLength={6}
              autoFocus
            />
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <TouchableOpacity
              style={[styles.btn, loading && { opacity: 0.7 }]}
              onPress={handleVerifyOTP}
              disabled={loading}
            >
              {loading
                ? <ActivityIndicator color="#fff" />
                : <Text style={styles.btnText}>Verify & Continue</Text>
              }
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.resendBtn}
              onPress={() => { setStep('phone'); setOtp(''); setError('') }}
            >
              <Text style={styles.resendText}>Change number</Text>
            </TouchableOpacity>
          </View>
        )}

        {step === 'done' && (
          <View style={styles.doneContainer}>
            <Ionicons name="checkmark-circle" size={80} color={Colors.accentGreen} />
            <Text style={styles.doneText}>You're verified!</Text>
            <Text style={styles.doneSubtext}>Taking you to Nancy...</Text>
            <ActivityIndicator color={Colors.accent} style={{ marginTop: Spacing.lg }} />
          </View>
        )}

        {/* Caregiver login link */}
        {step === 'phone' && (
          <TouchableOpacity
            style={styles.caregiverLink}
            onPress={() => router.push('/caregiver/login')}
          >
            <Ionicons name="people-outline" size={16} color={Colors.textMuted} />
            <Text style={styles.caregiverLinkText}>
              Are you a caregiver? Login here
            </Text>
          </TouchableOpacity>
        )}

      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe:      { flex: 1, backgroundColor: Colors.bg },
  container: { flex: 1, justifyContent: 'center', padding: Spacing.xl },

  header: { alignItems: 'center', marginBottom: Spacing.xl * 2 },
  logo: {
    width: 72, height: 72, borderRadius: 20,
    backgroundColor: Colors.accent + '22',
    borderWidth: 2, borderColor: Colors.accent + '44',
    alignItems: 'center', justifyContent: 'center',
    marginBottom: Spacing.lg,
  },
  logoText:  { fontSize: 32, fontWeight: '700', color: Colors.accent },
  title:     { ...Typography.title, color: Colors.text, marginBottom: Spacing.sm },
  subtitle:  { ...Typography.body, color: Colors.textMuted, textAlign: 'center' },

  form:  { gap: Spacing.md },
  label: { ...Typography.label, color: Colors.textMuted },

  phoneRow: { flexDirection: 'row', gap: Spacing.sm },
  countryCode: {
    backgroundColor: Colors.bgCard,
    borderWidth: 0.5, borderColor: Colors.border,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.md,
    justifyContent: 'center',
  },
  countryCodeText: { ...Typography.body, color: Colors.text },

  phoneInput: {
    flex: 1,
    backgroundColor: Colors.bgCard,
    color: Colors.text,
    borderWidth: 0.5, borderColor: Colors.border,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    fontSize: 18,
  },
  otpInput: {
    flex: 0,
    textAlign: 'center',
    fontSize: 28,
    letterSpacing: 8,
    fontWeight: '700',
  },

  error: { ...Typography.caption, color: Colors.accentRed },

  btn: {
    backgroundColor: Colors.accent,
    borderRadius: Radius.lg,
    paddingVertical: Spacing.lg,
    alignItems: 'center',
    marginTop: Spacing.sm,
  },
  btnText: { ...Typography.heading, color: '#fff' },

  resendBtn:  { alignItems: 'center', paddingVertical: Spacing.md },
  resendText: { ...Typography.label, color: Colors.accent },

  doneContainer: { alignItems: 'center', gap: Spacing.md },
  doneText:      { ...Typography.title, color: Colors.text },
  doneSubtext:   { ...Typography.body, color: Colors.textMuted },

  caregiverLink: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: Spacing.sm, marginTop: Spacing.xl * 2,
  },
  caregiverLinkText: { ...Typography.label, color: Colors.textMuted },
})

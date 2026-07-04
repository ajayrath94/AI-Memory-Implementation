import React, { useState } from 'react'
import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, SafeAreaView, KeyboardAvoidingView,
  Platform, ActivityIndicator, Alert,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { router } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import { Colors, Typography, Spacing, Radius, API_BASE } from '../../constants'

type Step = 'email' | 'otp' | 'newpassword' | 'done'

export default function ResetPasswordScreen() {
  const [step,        setStep]        = useState<Step>('email')
  const [email,       setEmail]       = useState('')
  const [otp,         setOtp]         = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirm,     setConfirm]     = useState('')
  const [loading,     setLoading]     = useState(false)

  const sendOtp = async () => {
    if (!email.trim()) { Alert.alert('Enter your email'); return }
    setLoading(true)
    try {
      const res  = await fetch(`${API_BASE}/auth/caregiver/reset-request`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ email: email.trim().toLowerCase() }),
      })
      if (!res.ok) throw new Error('Email not found')
      setStep('otp')
    } catch (e: any) {
      Alert.alert('Error', e.message)
    } finally {
      setLoading(false)
    }
  }

  const verifyOtp = async () => {
    if (otp.length < 6) { Alert.alert('Enter the 6-digit code'); return }
    setStep('newpassword')
  }

  const resetPassword = async () => {
    if (newPassword.length < 8) { Alert.alert('Password too short', 'Min 8 characters'); return }
    if (newPassword !== confirm)  { Alert.alert('Passwords don\'t match'); return }
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/auth/caregiver/reset-confirm`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ email, otp, new_password: newPassword }),
      })
      if (!res.ok) throw new Error('Invalid or expired code')
      setStep('done')
    } catch (e: any) {
      Alert.alert('Error', e.message)
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

        {/* Back button */}
        <TouchableOpacity style={styles.back} onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={22} color={Colors.textMuted} />
          <Text style={styles.backText}>Back to login</Text>
        </TouchableOpacity>

        {/* Step: Email */}
        {step === 'email' && (
          <View style={styles.form}>
            <Text style={styles.title}>Reset password</Text>
            <Text style={styles.subtitle}>
              Enter your email and we'll send you a verification code
            </Text>
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
                autoFocus
              />
            </View>
            <TouchableOpacity
              style={[styles.btn, loading && styles.btnLoading]}
              onPress={sendOtp}
              disabled={loading}
            >
              {loading
                ? <ActivityIndicator color="#fff" />
                : <Text style={styles.btnText}>Send verification code</Text>
              }
            </TouchableOpacity>
          </View>
        )}

        {/* Step: OTP */}
        {step === 'otp' && (
          <View style={styles.form}>
            <Text style={styles.title}>Check your email</Text>
            <Text style={styles.subtitle}>
              We sent a 6-digit code to {email}
            </Text>
            <View style={styles.field}>
              <Text style={styles.fieldLabel}>Verification code</Text>
              <TextInput
                style={[styles.input, styles.otpInput]}
                value={otp}
                onChangeText={setOtp}
                placeholder="000000"
                placeholderTextColor={Colors.textHint}
                keyboardType="number-pad"
                maxLength={6}
                autoFocus
              />
            </View>
            <TouchableOpacity style={styles.btn} onPress={verifyOtp}>
              <Text style={styles.btnText}>Verify code</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.linkBtn} onPress={sendOtp}>
              <Text style={styles.linkText}>Didn't receive it? <Text style={styles.linkHighlight}>Resend</Text></Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Step: New password */}
        {step === 'newpassword' && (
          <View style={styles.form}>
            <Text style={styles.title}>New password</Text>
            <Text style={styles.subtitle}>Choose a strong password for your account</Text>
            <View style={styles.field}>
              <Text style={styles.fieldLabel}>New password</Text>
              <TextInput
                style={styles.input}
                value={newPassword}
                onChangeText={setNewPassword}
                placeholder="Min 8 characters"
                placeholderTextColor={Colors.textHint}
                secureTextEntry
                autoFocus
              />
            </View>
            <View style={styles.field}>
              <Text style={styles.fieldLabel}>Confirm password</Text>
              <TextInput
                style={styles.input}
                value={confirm}
                onChangeText={setConfirm}
                placeholder="Same as above"
                placeholderTextColor={Colors.textHint}
                secureTextEntry
              />
            </View>
            <TouchableOpacity
              style={[styles.btn, loading && styles.btnLoading]}
              onPress={resetPassword}
              disabled={loading}
            >
              {loading
                ? <ActivityIndicator color="#fff" />
                : <Text style={styles.btnText}>Reset password</Text>
              }
            </TouchableOpacity>
          </View>
        )}

        {/* Step: Done */}
        {step === 'done' && (
          <View style={styles.form}>
            <View style={styles.successIcon}>
              <Ionicons name="checkmark" size={36} color={Colors.accentGreen} />
            </View>
            <Text style={styles.title}>Password reset!</Text>
            <Text style={styles.subtitle}>
              Your password has been updated. You can now sign in.
            </Text>
            <TouchableOpacity
              style={styles.btn}
              onPress={() => router.replace('/caregiver/login')}
            >
              <Text style={styles.btnText}>Back to sign in</Text>
            </TouchableOpacity>
          </View>
        )}

      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  kav:  { flex: 1, paddingHorizontal: Spacing.xl, justifyContent: 'center' },

  back: {
    flexDirection:  'row',
    alignItems:     'center',
    gap:            Spacing.sm,
    marginBottom:   Spacing.xxl,
    alignSelf:      'flex-start',
  },
  backText: { ...Typography.label, color: Colors.textMuted },

  form: {
    backgroundColor: Colors.bgCard,
    borderRadius:    Radius.xl,
    padding:         Spacing.xl,
    borderWidth:     0.5,
    borderColor:     Colors.border,
    gap:             Spacing.lg,
  },
  title:    { ...Typography.title, color: Colors.text },
  subtitle: { ...Typography.body, color: Colors.textMuted, marginTop: -Spacing.sm },

  field:      { gap: Spacing.xs },
  fieldLabel: { ...Typography.label, color: Colors.textSecond },
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
  otpInput: {
    fontSize:    24,
    letterSpacing: 8,
    textAlign:   'center',
  },

  btn: {
    backgroundColor: Colors.accent,
    borderRadius:    Radius.md,
    paddingVertical: Spacing.lg,
    alignItems:      'center',
    marginTop:       Spacing.sm,
  },
  btnLoading: { opacity: 0.7 },
  btnText:    { color: '#fff', fontSize: 16, fontWeight: '600' },

  linkBtn:       { alignItems: 'center' },
  linkText:      { ...Typography.body, color: Colors.textMuted },
  linkHighlight: { color: Colors.accent, fontWeight: '600' },

  successIcon: {
    width:           72,
    height:          72,
    borderRadius:    36,
    backgroundColor: Colors.accentGreen + '15',
    borderWidth:     1.5,
    borderColor:     Colors.accentGreen + '40',
    alignItems:      'center',
    justifyContent:  'center',
    alignSelf:       'center',
  },
})

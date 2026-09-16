import React, { useEffect, useState, useCallback } from 'react'
import {
  View, Text, ScrollView, StyleSheet,
  SafeAreaView, TouchableOpacity, ActivityIndicator,
  RefreshControl, Linking, Alert,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { Ionicons } from '@expo/vector-icons'
import { useTheme } from '../hooks/useTheme'
import { Colors, API_BASE, API_KEY } from '../constants'
import { useAppStore } from '../store/appStore'

/**
 * Zaroori numbers.
 *
 * She mentioned chest pain and her son got an email. She got a reply about
 * her day — the alert chain worked and none of it helped the woman sitting
 * alone with the pain, at the moment she had it.
 *
 * This is somewhere she goes, never something that arrives. A card appearing
 * unbidden saying "here are emergency numbers" frames an ordinary afternoon
 * as dangerous.
 *
 * WHAT IS DELIBERATELY NOT HERE
 * No red. No warning triangle. No "in case of emergency" banner. Nothing
 * about her conditions — she knows what is wrong with her and does not need
 * it printed on a screen she opens when frightened. The hospital happens to
 * suit her history and the screen never says so.
 *
 * Big text and big targets, because the hands using this may be shaking.
 */

interface Entry {
  label:   string
  number:  string
  address?: string
  kind:    'caregiver' | 'national' | 'hospital'
}

export default function EmergencyScreen() {
  const theme = useTheme()
  const { userId } = useAppStore()
  const [entries,    setEntries]    = useState<Entry[]>([])
  const [where,      setWhere]      = useState('')
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchCard = useCallback(async () => {
    try {
      const res  = await fetch(`${API_BASE}/emergency/${userId}`, {
        headers: { 'X-API-Key': API_KEY },
      })
      const json = await res.json()
      setEntries(json.entries || [])
      setWhere(json.where || '')
    } catch (err) {
      console.error('Failed to fetch emergency card:', err)
      // Even offline she should have these. They are constants, not data.
      setEntries([
        { label: 'Ambulance', number: '108', kind: 'national' },
        { label: 'Emergency', number: '112', kind: 'national' },
      ])
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [userId])

  useEffect(() => { fetchCard() }, [fetchCard])

  const call = async (num: string, label: string) => {
    if (!num) return
    const url = `tel:${num.replace(/\s/g, '')}`
    try {
      const ok = await Linking.canOpenURL(url)
      if (ok) await Linking.openURL(url)
      else Alert.alert(label, num)     // at least show it, so she can dial by hand
    } catch {
      Alert.alert(label, num)
    }
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.screen, { backgroundColor: theme.bg }]}>
        <ActivityIndicator size="large" color={Colors.accent} />
      </SafeAreaView>
    )
  }

  const people   = entries.filter(e => e.kind === 'caregiver')
  const national = entries.filter(e => e.kind === 'national')
  const places   = entries.filter(e => e.kind === 'hospital')

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: theme.bg }]}>
      <StatusBar style={theme.statusBar} />
      <ScrollView
        contentContainerStyle={styles.body}
        refreshControl={
          <RefreshControl refreshing={refreshing} tintColor={Colors.accent}
            onRefresh={() => { setRefreshing(true); fetchCard() }} />
        }
      >
        <Text style={[styles.title, { color: theme.text }]}>Zaroori numbers</Text>
        {where ? (
          <Text style={[styles.where, { color: theme.textDim }]}>{where}</Text>
        ) : null}

        {/* Her people first. A son who knows her history is more use in the
            first minute than any switchboard. */}
        {people.map((e, i) => (
          <TouchableOpacity
            key={`p${i}`}
            style={[styles.row, styles.rowPerson, { borderColor: theme.border }]}
            onPress={() => call(e.number, e.label)}
            activeOpacity={0.7}
          >
            <View style={styles.rowText}>
              <Text style={[styles.label, { color: theme.text }]}>{e.label}</Text>
              <Text style={[styles.number, { color: theme.textDim }]}>{e.number}</Text>
            </View>
            <Ionicons name="call" size={26} color={Colors.accent} />
          </TouchableOpacity>
        ))}

        {national.map((e, i) => (
          <TouchableOpacity
            key={`n${i}`}
            style={[styles.row, { borderColor: theme.border }]}
            onPress={() => call(e.number, e.label)}
            activeOpacity={0.7}
          >
            <View style={styles.rowText}>
              <Text style={[styles.label, { color: theme.text }]}>{e.label}</Text>
              <Text style={[styles.numberBig, { color: theme.text }]}>{e.number}</Text>
            </View>
            <Ionicons name="call" size={26} color={Colors.accent} />
          </TouchableOpacity>
        ))}

        {places.map((e, i) => (
          <TouchableOpacity
            key={`h${i}`}
            style={[styles.row, { borderColor: theme.border }]}
            onPress={() => call(e.number, e.label)}
            activeOpacity={0.7}
            disabled={!e.number}
          >
            <View style={styles.rowText}>
              <Text style={[styles.label, { color: theme.text }]}>{e.label}</Text>
              {e.address ? (
                <Text style={[styles.address, { color: theme.textDim }]} numberOfLines={2}>
                  {e.address}
                </Text>
              ) : null}
              {e.number ? (
                <Text style={[styles.number, { color: theme.textDim }]}>{e.number}</Text>
              ) : null}
            </View>
            {e.number ? <Ionicons name="call" size={26} color={Colors.accent} /> : null}
          </TouchableOpacity>
        ))}
      </ScrollView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, justifyContent: 'center' },
  body:   { padding: 20, paddingBottom: 40 },

  title:  { fontSize: 26, fontWeight: '600', marginBottom: 4 },
  // Where she is, small. It explains why the hospital is the one it is,
  // without the screen having to say anything about why.
  where:  { fontSize: 14, marginBottom: 22 },

  // Generous rows. The hands using this may be shaking, and a small target
  // is the difference between reaching someone and not.
  row: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingVertical: 18, paddingHorizontal: 16,
    borderWidth: 1, borderRadius: 14, marginBottom: 12,
  },
  rowPerson: { borderWidth: 2 },
  rowText:   { flex: 1, paddingRight: 12 },

  label:     { fontSize: 20, fontWeight: '500', marginBottom: 2 },
  number:    { fontSize: 15 },
  numberBig: { fontSize: 22, fontWeight: '600' },
  address:   { fontSize: 13, marginBottom: 4, lineHeight: 18 },
})

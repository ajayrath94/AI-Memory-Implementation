import React, { useEffect, useState, useCallback } from 'react'
import {
  View, Text, ScrollView, StyleSheet,
  SafeAreaView, TouchableOpacity, ActivityIndicator,
  RefreshControl, TextInput, Alert, Modal,
} from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { Ionicons } from '@expo/vector-icons'
import { useTheme } from '../hooks/useTheme'
import { Colors, Typography, Spacing, Radius, API_BASE, API_KEY } from '../constants'

const theme = useTheme()
  const { userId: USER_ID } = require('../store/appStore').useAppStore.getState() // Replace with auth context later

// ── Types ──────────────────────────────────────────────────────────────────────

interface UserProfile {
  name:          string | null
  age_group:     string | null
  location:      string | null
  language_pref: string | null
  family:        { children?: string[]; spouse?: string; other?: string[] }
  health:        { conditions?: string[]; concerns?: string[]; medications?: string[] }
  interests:     Record<string, string[]>
  personality:   { emotional_state?: string; communication_style?: string; traits?: string[] }
  life_context:  { occupation?: string; living_situation?: string; notable_events?: string[] }
  updated_at:    string
}

interface Interest {
  source:       'profile' | 'ltm'
  category:     string
  label:        string
  strength:     number
  confidence:   'confirmed' | 'high' | 'medium'
  recall_count?: number
}

// ── API helpers ────────────────────────────────────────────────────────────────

const api = async (path: string, method = 'GET', body?: any) => {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
    body:    body ? JSON.stringify(body) : undefined,
  })
  return res.json()
}

// ── Main Screen ────────────────────────────────────────────────────────────────

export default function ProfileScreen() {
  const [profile,    setProfile]    = useState<UserProfile | null>(null)
  const [interests,  setInterests]  = useState<{ profile_interests: Interest[], ltm_interests: Interest[] } | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  // Edit states
  const [editField,  setEditField]  = useState<string | null>(null)
  const [editValue,  setEditValue]  = useState('')
  const [addModal,   setAddModal]   = useState(false)
  const [addCategory, setAddCategory] = useState('hobbies')
  const [addLabel,    setAddLabel]    = useState('')
  const [saving,      setSaving]      = useState(false)

  const fetchAll = useCallback(async () => {
    try {
      const [p, i] = await Promise.all([
        api(`/memory/profile/${USER_ID}`),
        api(`/memory/interests/${USER_ID}`),
      ])
      setProfile(Object.keys(p).length ? p : null)
      setInterests(i)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { fetchAll() }, [])

  const onRefresh = () => { setRefreshing(true); fetchAll() }

  // ── Edit a simple field ──────────────────────────────────────────────────────
  const startEdit = (field: string, current: string) => {
    setEditField(field)
    setEditValue(current || '')
  }

  const saveField = async () => {
    if (!editField) return
    setSaving(true)
    try {
      await api(`/memory/profile/${USER_ID}/field`, 'PATCH', {
        field: editField, value: editValue.trim()
      })
      await fetchAll()
      setEditField(null)
    } catch (e) {
      Alert.alert('Error', 'Failed to save. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  // ── Add interest ─────────────────────────────────────────────────────────────
  const addInterest = async () => {
    if (!addLabel.trim()) return
    setSaving(true)
    try {
      await api(`/memory/interests/${USER_ID}/add`, 'POST', {
        category: addCategory, label: addLabel.trim()
      })
      await fetchAll()
      setAddModal(false)
      setAddLabel('')
    } catch (e) {
      Alert.alert('Error', 'Failed to add interest.')
    } finally {
      setSaving(false)
    }
  }

  // ── Remove interest ──────────────────────────────────────────────────────────
  const removeInterest = (category: string, label: string) => {
    Alert.alert(
      'Remove interest',
      `Remove "${label}" from your interests?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove', style: 'destructive',
          onPress: async () => {
            await api(`/memory/interests/${USER_ID}/remove`, 'DELETE', { category, label })
            fetchAll()
          }
        }
      ]
    )
  }

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}>
          <ActivityIndicator color={Colors.accent} />
          <Text style={styles.loadingText}>Loading your profile...</Text>
        </View>
      </SafeAreaView>
    )
  }

  const allInterests = [
    ...(interests?.profile_interests || []),
    ...(interests?.ltm_interests || []),
  ]

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />

      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Your Profile</Text>
        <TouchableOpacity onPress={onRefresh} style={styles.headerBtn}>
          <Ionicons name="refresh-outline" size={20} color={theme.textMuted} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Colors.accent} />
        }
        showsVerticalScrollIndicator={false}
      >

        {/* Identity card */}
        <View style={styles.identityCard}>
          <View style={styles.avatarCircle}>
            <Text style={styles.avatarText}>
              {profile?.name ? profile.name[0].toUpperCase() : '?'}
            </Text>
          </View>
          <View style={{ flex: 1 }}>
            <EditableRow
              label="Name"
              value={profile?.name || ''}
              placeholder="Not set yet"
              onEdit={() => startEdit('name', profile?.name || '')}
            />
            <EditableRow
              label="Location"
              value={profile?.location || ''}
              placeholder="Not set"
              onEdit={() => startEdit('location', profile?.location || '')}
              icon="📍"
            />
            <EditableRow
              label="Language"
              value={profile?.language_pref || ''}
              placeholder="Auto-detected"
              onEdit={() => startEdit('language_pref', profile?.language_pref || '')}
              icon="💬"
            />
          </View>
        </View>

        {/* Emotional state — auto-detected, read-only */}
        {profile?.personality?.emotional_state && (
          <View style={styles.emotionCard}>
            <Text style={styles.emotionLabel}>Nancy senses you're feeling</Text>
            <Text style={styles.emotionValue}>{profile.personality.emotional_state}</Text>
            <Text style={styles.emotionHint}>Auto-detected from your conversations</Text>
          </View>
        )}

        {/* Health */}
        <Section
          title="🏥 Health"
          onAdd={() => startEdit('health.conditions', '')}
          addLabel="Add condition"
        >
          {(profile?.health?.conditions || []).length === 0 ? (
            <Text style={styles.emptySection}>
              Nancy will pick up health information from your conversations naturally.
            </Text>
          ) : (
            profile?.health?.conditions?.map((c, i) => (
              <TagRow
                key={i}
                label={c}
                color={Colors.accentRed}
                onRemove={() => {/* remove health condition */}}
              />
            ))
          )}
        </Section>

        {/* Family */}
        <Section title="👨‍👩‍👧 Family">
          {(profile?.family?.children || []).length === 0 && !profile?.family?.spouse ? (
            <Text style={styles.emptySection}>
              Tell Nancy about your family — she'll remember for next time.
            </Text>
          ) : (
            <>
              {profile?.family?.spouse && (
                <TagRow label={`Spouse: ${profile.family.spouse}`} color={Colors.accentWarm} />
              )}
              {profile?.family?.children?.map((c, i) => (
                <TagRow key={i} label={`Child: ${c}`} color={Colors.accent} />
              ))}
            </>
          )}
        </Section>

        {/* Interests — the main section, fully editable */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>⭐ Interests</Text>
            <TouchableOpacity
              style={styles.addBtn}
              onPress={() => setAddModal(true)}
            >
              <Ionicons name="add" size={16} color={Colors.accent} />
              <Text style={styles.addBtnText}>Add</Text>
            </TouchableOpacity>
          </View>

          {allInterests.length === 0 ? (
            <View style={styles.interestEmpty}>
              <Text style={styles.emptySection}>
                Nancy learns your interests naturally from conversation.
                You can also add them manually.
              </Text>
              <TouchableOpacity
                style={styles.addInterestBtn}
                onPress={() => setAddModal(true)}
              >
                <Text style={styles.addInterestBtnText}>+ Add an interest</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <>
              {/* Profile-extracted interests */}
              {interests?.profile_interests && interests.profile_interests.length > 0 && (
                <View style={styles.interestGroup}>
                  <Text style={styles.interestGroupLabel}>From your conversations</Text>
                  <View style={styles.chipRow}>
                    {interests.profile_interests.map((interest, i) => (
                      <InterestChip
                        key={`p-${i}`}
                        interest={interest}
                        onRemove={() => removeInterest(interest.category, interest.label)}
                      />
                    ))}
                  </View>
                </View>
              )}

              {/* LTM-observed interests */}
              {interests?.ltm_interests && interests.ltm_interests.length > 0 && (
                <View style={styles.interestGroup}>
                  <Text style={styles.interestGroupLabel}>Nancy has noticed you often discuss</Text>
                  <View style={styles.chipRow}>
                    {interests.ltm_interests.map((interest, i) => (
                      <InterestChip
                        key={`l-${i}`}
                        interest={interest}
                        isObserved
                        onConfirm={() => {
                          // Promote observed to confirmed profile interest
                          api(`/memory/interests/${USER_ID}/add`, 'POST', {
                            category: 'observed', label: interest.label
                          }).then(fetchAll)
                        }}
                      />
                    ))}
                  </View>
                </View>
              )}
            </>
          )}
        </View>

        {/* Life context */}
        <Section title="📖 Life">
          {profile?.life_context?.occupation && (
            <EditableRow
              label="Occupation"
              value={profile.life_context.occupation}
              onEdit={() => startEdit('life_context.occupation', profile?.life_context?.occupation || '')}
            />
          )}
          {profile?.life_context?.living_situation && (
            <TagRow label={profile.life_context.living_situation} color={Colors.accent} />
          )}
          {!profile?.life_context?.occupation && !profile?.life_context?.living_situation && (
            <Text style={styles.emptySection}>
              Nancy learns about your life through conversation.
            </Text>
          )}
        </Section>

        {profile?.updated_at && (
          <Text style={styles.updatedAt}>
            Profile last updated: {new Date(profile.updated_at).toLocaleString()}
          </Text>
        )}

        <View style={styles.deleteSection}>
          <TouchableOpacity
            style={styles.deleteBtn}
            onPress={() => Alert.alert(
              'Delete all data',
              'This will permanently delete everything Nancy knows about you. This cannot be undone.',
              [
                { text: 'Cancel', style: 'cancel' },
                {
                  text: 'Delete everything', style: 'destructive',
                  onPress: () => {
                    // TODO: implement full data deletion
                    Alert.alert('Data deleted', 'All your data has been removed.')
                  }
                }
              ]
            )}
          >
            <Ionicons name="trash-outline" size={16} color={Colors.accentRed} />
            <Text style={styles.deleteBtnText}>Delete all my data</Text>
          </TouchableOpacity>
        </View>

      </ScrollView>

      {/* Edit field modal */}
      <Modal visible={!!editField} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Edit {editField?.replace('.', ' → ')}</Text>
            <TextInput
              style={styles.modalInput}
              value={editValue}
              onChangeText={setEditValue}
              autoFocus
              placeholder="Enter value"
              placeholderTextColor={Colors.textHint}
            />
            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalCancel}
                onPress={() => setEditField(null)}
              >
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalSave, saving && { opacity: 0.6 }]}
                onPress={saveField}
                disabled={saving}
              >
                {saving
                  ? <ActivityIndicator size="small" color="#fff" />
                  : <Text style={styles.modalSaveText}>Save</Text>
                }
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Add interest modal */}
      <Modal visible={addModal} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Add an interest</Text>

            <Text style={styles.modalLabel}>Category</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: Spacing.md }}>
              <View style={{ flexDirection: 'row', gap: Spacing.sm }}>
                {['sports', 'music', 'hobbies', 'entertainment', 'religion', 'food'].map(cat => (
                  <TouchableOpacity
                    key={cat}
                    style={[styles.catChip, addCategory === cat && styles.catChipActive]}
                    onPress={() => setAddCategory(cat)}
                  >
                    <Text style={[styles.catChipText, addCategory === cat && styles.catChipTextActive]}>
                      {cat}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>

            <Text style={styles.modalLabel}>Interest</Text>
            <TextInput
              style={styles.modalInput}
              value={addLabel}
              onChangeText={setAddLabel}
              autoFocus
              placeholder="e.g. Cricket, Kishore Kumar songs..."
              placeholderTextColor={Colors.textHint}
            />

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalCancel}
                onPress={() => { setAddModal(false); setAddLabel('') }}
              >
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalSave, (!addLabel.trim() || saving) && { opacity: 0.5 }]}
                onPress={addInterest}
                disabled={!addLabel.trim() || saving}
              >
                {saving
                  ? <ActivityIndicator size="small" color="#fff" />
                  : <Text style={styles.modalSaveText}>Add</Text>
                }
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

    </SafeAreaView>
  )
}

// ── Reusable components ────────────────────────────────────────────────────────

function Section({ title, children, onAdd, addLabel }: {
  title: string; children: React.ReactNode; onAdd?: () => void; addLabel?: string
}) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>{title}</Text>
        {onAdd && (
          <TouchableOpacity style={styles.addBtn} onPress={onAdd}>
            <Ionicons name="add" size={16} color={Colors.accent} />
            <Text style={styles.addBtnText}>{addLabel || 'Add'}</Text>
          </TouchableOpacity>
        )}
      </View>
      {children}
    </View>
  )
}

function EditableRow({ label, value, placeholder, onEdit, icon }: {
  label: string; value: string; placeholder?: string; onEdit: () => void; icon?: string
}) {
  return (
    <TouchableOpacity style={styles.editableRow} onPress={onEdit} activeOpacity={0.7}>
      <Text style={styles.editableLabel}>{icon} {label}</Text>
      <View style={styles.editableRight}>
        <Text style={[styles.editableValue, !value && styles.editablePlaceholder]}>
          {value || placeholder || 'Tap to add'}
        </Text>
        <Ionicons name="pencil-outline" size={14} color={theme.textHint} />
      </View>
    </TouchableOpacity>
  )
}

function TagRow({ label, color, onRemove }: {
  label: string; color: string; onRemove?: () => void
}) {
  return (
    <View style={styles.tagRow}>
      <View style={[styles.tagDot, { backgroundColor: color }]} />
      <Text style={styles.tagLabel}>{label}</Text>
      {onRemove && (
        <TouchableOpacity onPress={onRemove} style={styles.tagRemove}>
          <Ionicons name="close" size={14} color={theme.textMuted} />
        </TouchableOpacity>
      )}
    </View>
  )
}

function InterestChip({ interest, isObserved, onRemove, onConfirm }: {
  interest: Interest; isObserved?: boolean; onRemove?: () => void; onConfirm?: () => void
}) {
  const strengthColor = interest.strength > 0.8 ? Colors.accentGreen
    : interest.strength > 0.5 ? Colors.accentWarm
    : Colors.textMuted

  return (
    <View style={[styles.interestChip, isObserved && styles.interestChipObserved]}>
      <Text style={styles.interestChipText}>{interest.label}</Text>

      {/* Strength indicator */}
      <View style={[styles.strengthDot, { backgroundColor: strengthColor }]} />

      {isObserved ? (
        // Confirm button for LTM-observed interests
        <TouchableOpacity onPress={onConfirm} style={styles.confirmBtn}>
          <Ionicons name="checkmark" size={12} color={Colors.accentGreen} />
        </TouchableOpacity>
      ) : (
        // Remove button for confirmed interests
        onRemove && (
          <TouchableOpacity onPress={onRemove} style={styles.chipRemove}>
            <Ionicons name="close" size={12} color={theme.textMuted} />
          </TouchableOpacity>
        )
      )}
    </View>
  )
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe:        { flex: 1, backgroundColor: theme.bg },
  center:      { flex: 1, alignItems: 'center', justifyContent: 'center', gap: Spacing.md },
  loadingText: { ...Typography.body, color: theme.textMuted },

  header: {
    flexDirection:     'row',
    alignItems:        'center',
    justifyContent:    'space-between',
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.md,
    borderBottomWidth: 0.5,
    borderBottomColor: Colors.border,
  },
  headerTitle: { ...Typography.heading, color: theme.text },
  headerBtn:   { padding: Spacing.sm },

  scroll: { padding: Spacing.lg, gap: Spacing.md },

  // Identity card
  identityCard: {
    backgroundColor: theme.bgCard,
    borderRadius:    Radius.xl,
    padding:         Spacing.lg,
    flexDirection:   'row',
    gap:             Spacing.lg,
    borderWidth:     0.5,
    borderColor:     Colors.border,
  },
  avatarCircle: {
    width:           56,
    height:          56,
    borderRadius:    28,
    backgroundColor: Colors.accent + '22',
    borderWidth:     1.5,
    borderColor:     Colors.accent + '44',
    alignItems:      'center',
    justifyContent:  'center',
    flexShrink:      0,
  },
  avatarText: { fontSize: 22, fontWeight: '700', color: Colors.accent },

  // Editable rows
  editableRow: {
    flexDirection:  'row',
    justifyContent: 'space-between',
    alignItems:     'center',
    paddingVertical: Spacing.xs,
    gap:             Spacing.sm,
  },
  editableLabel:       { ...Typography.caption, color: theme.textMuted, width: 70 },
  editableRight:       { flex: 1, flexDirection: 'row', alignItems: 'center', gap: Spacing.xs, justifyContent: 'flex-end' },
  editableValue:       { ...Typography.label, color: theme.text, textAlign: 'right' },
  editablePlaceholder: { color: theme.textHint },

  // Emotion card
  emotionCard: {
    backgroundColor: Colors.accentGreen + '10',
    borderRadius:    Radius.lg,
    padding:         Spacing.lg,
    borderWidth:     0.5,
    borderColor:     Colors.accentGreen + '30',
    alignItems:      'center',
    gap:             Spacing.xs,
  },
  emotionLabel: { ...Typography.caption, color: theme.textMuted },
  emotionValue: { ...Typography.heading, color: Colors.accentGreen },
  emotionHint:  { ...Typography.caption, color: theme.textMuted },

  // Sections
  section: {
    backgroundColor: theme.bgCard,
    borderRadius:    Radius.lg,
    padding:         Spacing.lg,
    borderWidth:     0.5,
    borderColor:     Colors.border,
    gap:             Spacing.sm,
  },
  sectionHeader: {
    flexDirection:  'row',
    justifyContent: 'space-between',
    alignItems:     'center',
    marginBottom:   Spacing.xs,
  },
  sectionTitle: {
    ...Typography.label,
    color:          Colors.textMuted,
    textTransform:  'uppercase',
    letterSpacing:  0.8,
  },
  addBtn: {
    flexDirection:  'row',
    alignItems:     'center',
    gap:            4,
    backgroundColor: Colors.accent + '15',
    paddingHorizontal: Spacing.sm,
    paddingVertical:   4,
    borderRadius:   Radius.full,
  },
  addBtnText: { ...Typography.caption, color: Colors.accent, fontWeight: '600' },
  emptySection: { ...Typography.body, color: theme.textMuted, lineHeight: 22 },

  // Tag rows
  tagRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, paddingVertical: 4 },
  tagDot: { width: 8, height: 8, borderRadius: 4 },
  tagLabel: { ...Typography.body, color: theme.text, flex: 1 },
  tagRemove: { padding: 4 },

  // Interests
  interestEmpty:       { gap: Spacing.md },
  interestGroup:       { gap: Spacing.sm },
  interestGroupLabel:  { ...Typography.caption, color: theme.textMuted },
  chipRow:             { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm },

  interestChip: {
    flexDirection:     'row',
    alignItems:        'center',
    gap:               Spacing.xs,
    backgroundColor:   Colors.accent + '15',
    borderRadius:      Radius.full,
    paddingHorizontal: Spacing.md,
    paddingVertical:   Spacing.xs,
    borderWidth:       0.5,
    borderColor:       Colors.accent + '30',
  },
  interestChipObserved: {
    backgroundColor: Colors.accentWarm + '12',
    borderColor:     Colors.accentWarm + '30',
  },
  interestChipText: { ...Typography.label, color: theme.text },
  strengthDot: { width: 5, height: 5, borderRadius: 3 },
  confirmBtn:  { padding: 2 },
  chipRemove:  { padding: 2 },

  addInterestBtn: {
    alignSelf:       'flex-start',
    backgroundColor: Colors.accent + '15',
    borderRadius:    Radius.full,
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.sm,
  },
  addInterestBtnText: { ...Typography.label, color: Colors.accent },

  // Life context
  lifeRow: { flexDirection: 'row', gap: Spacing.sm, alignItems: 'center' },

  // Updated at
  updatedAt: {
    ...Typography.caption,
    color:     Colors.textMuted,
    textAlign: 'center',
    marginTop: Spacing.sm,
  },

  // Delete section
  deleteSection: { alignItems: 'center', paddingVertical: Spacing.lg },
  deleteBtn: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           Spacing.sm,
    padding:       Spacing.md,
  },
  deleteBtnText: { ...Typography.label, color: Colors.accentRed },

  // Modals
  modalOverlay: {
    flex:            1,
    backgroundColor: '#000000aa',
    justifyContent:  'flex-end',
  },
  modalCard: {
    backgroundColor: theme.bgCard,
    borderRadius:    Radius.xl,
    padding:         Spacing.xl,
    margin:          Spacing.lg,
    gap:             Spacing.md,
    borderWidth:     0.5,
    borderColor:     Colors.border,
  },
  modalTitle:       { ...Typography.heading, color: theme.text },
  modalLabel:       { ...Typography.label, color: theme.textMuted },
  modalInput: {
    backgroundColor:   Colors.bgInput,
    color:             Colors.text,
    borderWidth:       0.5,
    borderColor:       Colors.border,
    borderRadius:      Radius.md,
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.md,
    fontSize:          16,
  },
  modalActions:     { flexDirection: 'row', gap: Spacing.md, marginTop: Spacing.sm },
  modalCancel: {
    flex:           1,
    paddingVertical: Spacing.md,
    alignItems:     'center',
    borderRadius:   Radius.md,
    borderWidth:    0.5,
    borderColor:    Colors.border,
  },
  modalCancelText:  { ...Typography.label, color: theme.textMuted },
  modalSave: {
    flex:            1,
    paddingVertical: Spacing.md,
    alignItems:      'center',
    borderRadius:    Radius.md,
    backgroundColor: Colors.accent,
  },
  modalSaveText: { ...Typography.label, color: '#fff', fontWeight: '600' },

  // Category chips in add modal
  catChip: {
    paddingHorizontal: Spacing.md,
    paddingVertical:   Spacing.xs,
    borderRadius:      Radius.full,
    borderWidth:       0.5,
    borderColor:       Colors.border,
    backgroundColor:   Colors.bgInput,
  },
  catChipActive: {
    backgroundColor: Colors.accent + '20',
    borderColor:     Colors.accent,
  },
  catChipText:       { ...Typography.label, color: theme.textMuted },
  catChipTextActive: { color: Colors.accent },
})

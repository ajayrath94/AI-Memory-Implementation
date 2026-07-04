import React, { useState } from 'react'
import { View, Text, TouchableOpacity, Modal, FlatList, StyleSheet } from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { Colors, MODELS } from '../../constants'
import { useAppStore } from '../../store/appStore'

export function ModelPicker() {
  const { model, setModel } = useAppStore()
  const [open, setOpen] = useState(false)
  const current = MODELS.find(m => m.value === model) ?? MODELS[0]

  return (
    <>
      <TouchableOpacity onPress={() => setOpen(true)} style={styles.trigger}>
        <Text style={styles.label}>{current.label}</Text>
        <Ionicons name="chevron-down" size={14} color={Colors.textMuted} />
      </TouchableOpacity>

      <Modal visible={open} transparent animationType="slide">
        <TouchableOpacity style={styles.overlay} onPress={() => setOpen(false)} activeOpacity={1}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>Select model</Text>
            <FlatList
              data={MODELS}
              keyExtractor={m => m.value}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={[styles.option, item.value === model && styles.optionActive]}
                  onPress={() => { setModel(item.value); setOpen(false) }}
                >
                  <View>
                    <Text style={styles.optionLabel}>{item.label}</Text>
                    <Text style={styles.optionProvider}>{item.provider}</Text>
                  </View>
                  {item.value === model && (
                    <Ionicons name="checkmark" size={18} color={Colors.accent} />
                  )}
                </TouchableOpacity>
              )}
            />
          </View>
        </TouchableOpacity>
      </Modal>
    </>
  )
}

const styles = StyleSheet.create({
  trigger: {
    flexDirection:  'row',
    alignItems:     'center',
    gap:            4,
    backgroundColor: Colors.bgInput,
    borderWidth:    1,
    borderColor:    Colors.border,
    borderRadius:   8,
    paddingHorizontal: 10,
    paddingVertical:    6,
  },
  label:    { color: Colors.text, fontSize: 13 },
  overlay:  { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: Colors.bgCard,
    borderTopLeftRadius:  20,
    borderTopRightRadius: 20,
    padding: 20,
    paddingBottom: 40,
  },
  sheetTitle: { color: Colors.textMuted, fontSize: 12, marginBottom: 16, textTransform: 'uppercase', letterSpacing: 1 },
  option: {
    flexDirection:  'row',
    alignItems:     'center',
    justifyContent: 'space-between',
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  optionActive:    { },
  optionLabel:    { color: Colors.text, fontSize: 15 },
  optionProvider: { color: Colors.textMuted, fontSize: 12, marginTop: 2 },
})

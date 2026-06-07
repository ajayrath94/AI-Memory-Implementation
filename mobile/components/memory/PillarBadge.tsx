import React from 'react'
import { View, Text, StyleSheet } from 'react-native'
import { Colors } from '../../constants'

interface Props {
  core:       string
  emotion:    string
  functional: string
  memoryUsed: boolean
}

export function PillarBadge({ core, emotion, functional, memoryUsed }: Props) {
  return (
    <View style={styles.row}>
      <Pill label={core}       color={Colors.pill[core]       ?? Colors.pill.GENERAL} />
      <Pill label={emotion}    color={Colors.pill[emotion]    ?? Colors.pill.NEUTRAL} />
      <Pill label={functional} color={Colors.pill.GENERAL} />
      {memoryUsed && <Pill label="🧠 memory" color="#1a2a3a" />}
    </View>
  )
}

function Pill({ label, color }: { label: string; color: string }) {
  return (
    <View style={[styles.pill, { backgroundColor: color }]}>
      <Text style={styles.pillText}>{label}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    flexWrap:      'wrap',
    gap:           6,
    paddingHorizontal: 16,
    paddingVertical:    6,
  },
  pill: {
    borderRadius:      10,
    paddingHorizontal: 8,
    paddingVertical:   3,
  },
  pillText: {
    color:     Colors.textMuted,
    fontSize:  11,
    fontWeight: '500',
  },
})

import React, { useState } from 'react'
import {
  View, Text, StyleSheet, TouchableOpacity,
  Modal, TextInput, TouchableWithoutFeedback,
  Keyboard, Alert,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { Colors, Typography, Spacing, Radius } from '../../constants'

interface Message {
  id:          string
  role:        'user' | 'assistant'
  content:     string
  model?:      string
  timestamp:   number
  pillar?:     { core: string; emotion: string; functional: string }
  memoryUsed?: boolean
}

interface Props {
  message:  Message
  onResend?: (text: string, messageId: string) => void
}

export function MessageBubble({ message, onResend }: Props) {
  const isUser = message.role === 'user'
  const time   = new Date(message.timestamp).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit'
  })

  const [showMenu,  setShowMenu]  = useState(false)
  const [editMode,  setEditMode]  = useState(false)
  const [editText,  setEditText]  = useState(message.content)

  const handleLongPress = () => {
    if (isUser) setShowMenu(true)
  }

  const handleEdit = () => {
    setShowMenu(false)
    setEditText(message.content)
    setEditMode(true)
  }

  const handleResend = () => {
    if (!editText.trim()) return
    setEditMode(false)
    onResend?.(editText.trim(), message.id)
  }

  const handleCopy = () => {
    setShowMenu(false)
    // Copy to clipboard
    Alert.alert('Copied', message.content.slice(0, 50) + '...')
  }

  return (
    <>
      <TouchableOpacity
        onLongPress={handleLongPress}
        activeOpacity={0.9}
        delayLongPress={400}
      >
        <View style={[styles.wrapper, isUser ? styles.wrapperUser : styles.wrapperBot]}>
          {!isUser && <View style={styles.nancyDot} />}

          <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleBot]}>
            <Text style={[styles.text, isUser ? styles.textUser : styles.textBot]}>
              {message.content}
            </Text>

            <View style={styles.footer}>
              {!isUser && message.memoryUsed && (
                <View style={styles.memoryTag}>
                  <Text style={styles.memoryText}>🧠</Text>
                </View>
              )}
              <Text style={styles.time}>{time}</Text>
            </View>
          </View>
        </View>
      </TouchableOpacity>

      {/* Context menu */}
      <Modal visible={showMenu} transparent animationType="fade">
        <TouchableWithoutFeedback onPress={() => setShowMenu(false)}>
          <View style={styles.menuOverlay}>
            <View style={styles.menu}>
              <TouchableOpacity style={styles.menuItem} onPress={handleEdit}>
                <Ionicons name="pencil-outline" size={18} color={Colors.text} />
                <Text style={styles.menuText}>Edit & Resend</Text>
              </TouchableOpacity>
              <View style={styles.menuDivider} />
              <TouchableOpacity style={styles.menuItem} onPress={handleCopy}>
                <Ionicons name="copy-outline" size={18} color={Colors.text} />
                <Text style={styles.menuText}>Copy</Text>
              </TouchableOpacity>
            </View>
          </View>
        </TouchableWithoutFeedback>
      </Modal>

      {/* Edit modal */}
      <Modal visible={editMode} transparent animationType="slide">
        <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
          <View style={styles.editOverlay}>
            <View style={styles.editCard}>
              <View style={styles.editHeader}>
                <Text style={styles.editTitle}>Edit message</Text>
                <TouchableOpacity onPress={() => setEditMode(false)}>
                  <Ionicons name="close" size={22} color={Colors.textMuted} />
                </TouchableOpacity>
              </View>

              <TextInput
                style={styles.editInput}
                value={editText}
                onChangeText={setEditText}
                multiline
                autoFocus
                placeholder="Edit your message..."
                placeholderTextColor={Colors.textHint}
              />

              <View style={styles.editActions}>
                <TouchableOpacity
                  style={styles.editCancel}
                  onPress={() => setEditMode(false)}
                >
                  <Text style={styles.editCancelText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.editResend, !editText.trim() && { opacity: 0.5 }]}
                  onPress={handleResend}
                  disabled={!editText.trim()}
                >
                  <Ionicons name="send" size={16} color="#fff" />
                  <Text style={styles.editResendText}>Resend</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </TouchableWithoutFeedback>
      </Modal>
    </>
  )
}

const styles = StyleSheet.create({
  wrapper: {
    marginVertical:    3,
    paddingHorizontal: Spacing.lg,
    flexDirection:     'row',
    alignItems:        'flex-end',
    gap:               Spacing.sm,
  },
  wrapperUser: { justifyContent: 'flex-end' },
  wrapperBot:  { justifyContent: 'flex-start' },

  nancyDot: {
    width:           8,
    height:          8,
    borderRadius:    4,
    backgroundColor: Colors.accent + '60',
    marginBottom:    16,
    flexShrink:      0,
  },

  bubble: {
    maxWidth:          '82%',
    borderRadius:      Radius.xl,
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.md,
  },
  bubbleUser: {
    backgroundColor:        Colors.bgUserBubble,
    borderBottomRightRadius: Radius.sm,
    borderWidth:             0.5,
    borderColor:             Colors.borderBlue,
  },
  bubbleBot: {
    backgroundColor:       Colors.bgCard,
    borderBottomLeftRadius: Radius.sm,
    borderWidth:            0.5,
    borderColor:            Colors.border,
  },

  text:     { ...Typography.body, lineHeight: 24 },
  textUser: { color: Colors.text },
  textBot:  { color: Colors.text },

  footer: {
    flexDirection:  'row',
    alignItems:     'center',
    justifyContent: 'flex-end',
    marginTop:      Spacing.xs,
    gap:            Spacing.xs,
  },
  memoryTag: {
    backgroundColor:   Colors.accentPurple + '15',
    borderRadius:      Radius.sm,
    paddingHorizontal: 5,
    paddingVertical:   1,
  },
  memoryText: { fontSize: 10 },
  time:       { ...Typography.caption, color: Colors.textHint },

  // Context menu
  menuOverlay: {
    flex:            1,
    backgroundColor: '#00000066',
    justifyContent:  'center',
    alignItems:      'center',
  },
  menu: {
    backgroundColor: Colors.bgCard,
    borderRadius:    Radius.lg,
    padding:         Spacing.xs,
    borderWidth:     0.5,
    borderColor:     Colors.border,
    minWidth:        180,
  },
  menuItem: {
    flexDirection:  'row',
    alignItems:     'center',
    gap:            Spacing.md,
    padding:        Spacing.md,
    borderRadius:   Radius.md,
  },
  menuText:    { ...Typography.body, color: Colors.text },
  menuDivider: { height: 0.5, backgroundColor: Colors.border, marginHorizontal: Spacing.sm },

  // Edit modal
  editOverlay: {
    flex:            1,
    backgroundColor: '#00000088',
    justifyContent:  'flex-end',
  },
  editCard: {
    backgroundColor: Colors.bgCard,
    borderRadius:    Radius.xl,
    padding:         Spacing.xl,
    margin:          Spacing.lg,
    gap:             Spacing.md,
    borderWidth:     0.5,
    borderColor:     Colors.border,
  },
  editHeader: {
    flexDirection:  'row',
    justifyContent: 'space-between',
    alignItems:     'center',
  },
  editTitle: { ...Typography.heading, color: Colors.text },
  editInput: {
    backgroundColor:   Colors.bgInput,
    color:             Colors.text,
    borderWidth:       0.5,
    borderColor:       Colors.border,
    borderRadius:      Radius.md,
    paddingHorizontal: Spacing.lg,
    paddingVertical:   Spacing.md,
    fontSize:          16,
    minHeight:         80,
    textAlignVertical: 'top',
  },
  editActions: { flexDirection: 'row', gap: Spacing.md },
  editCancel: {
    flex:            1,
    paddingVertical: Spacing.md,
    alignItems:      'center',
    borderRadius:    Radius.md,
    borderWidth:     0.5,
    borderColor:     Colors.border,
  },
  editCancelText:  { ...Typography.label, color: Colors.textMuted },
  editResend: {
    flex:            1,
    flexDirection:   'row',
    alignItems:      'center',
    justifyContent:  'center',
    gap:             Spacing.sm,
    paddingVertical: Spacing.md,
    borderRadius:    Radius.md,
    backgroundColor: Colors.accent,
  },
  editResendText: { ...Typography.label, color: '#fff', fontWeight: '600' },
})

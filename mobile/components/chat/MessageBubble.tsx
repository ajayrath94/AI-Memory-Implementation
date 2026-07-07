import React, { useState } from 'react'
import {
  View, Text, StyleSheet, TouchableOpacity,
  Modal, TextInput, TouchableWithoutFeedback,
  Keyboard,
} from 'react-native'
import Markdown from 'react-native-markdown-display'
import { Ionicons } from '@expo/vector-icons'
import { Colors, Typography, Spacing, Radius } from '../../constants'
import { YouTubePlayer } from '../media/YouTubePlayer'

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
  message:   Message
  onResend?: (text: string, messageId: string) => void
}

// Extract YouTube video ID from text
function extractYouTube(text: string): string | null {
  const match = text.match(/youtube\.com\/watch\?v=([\w-]+)/)
  return match ? match[1] : null
}

// Remove YouTube URL from text for clean display
function cleanText(text: string): string {
  return text.replace(/https?:\/\/www\.youtube\.com\/watch\?v=[\w-]+/g, '').trim()
}

export function MessageBubble({ message, onResend }: Props) {
  const isUser = message.role === 'user'
  const time   = new Date(message.timestamp).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit'
  })

  const [showMenu, setShowMenu] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editText, setEditText] = useState(message.content)

  const videoId   = !isUser ? extractYouTube(message.content) : null
  const cleanMsg  = videoId ? cleanText(message.content) : message.content

  const handleLongPress = () => { if (isUser) setShowMenu(true) }
  const handleEdit      = () => { setShowMenu(false); setEditText(message.content); setEditMode(true) }
  const handleResend    = () => { if (!editText.trim()) return; setEditMode(false); onResend?.(editText.trim(), message.id) }

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

            {isUser ? (
              <Text style={styles.textUser}>{cleanMsg}</Text>
            ) : (
              <Markdown style={markdownStyles}>{cleanMsg}</Markdown>
            )}

            {videoId && (
              <YouTubePlayer video={{
                video_id:    videoId,
                title:       'Nancy recommends',
                channel:     '',
                youtube_url: `https://www.youtube.com/watch?v=${videoId}`,
              }} />
            )}

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
                placeholderTextColor={Colors.textHint}
              />
              <View style={styles.editActions}>
                <TouchableOpacity style={styles.editCancel} onPress={() => setEditMode(false)}>
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

// Markdown styles
const markdownStyles = {
  body:       { color: Colors.text, fontSize: 16, lineHeight: 24 },
  strong:     { color: Colors.text, fontWeight: '700' as const },
  em:         { color: Colors.textSecond, fontStyle: 'italic' as const },
  bullet_list:{ marginVertical: 4 },
  list_item:  { flexDirection: 'row' as const, marginVertical: 2 },
  paragraph:  { marginVertical: 4, color: Colors.text },
  code_inline:{ backgroundColor: Colors.bgInput, color: Colors.accent, borderRadius: 4, paddingHorizontal: 4 },
}

const styles = StyleSheet.create({
  wrapper:     { marginVertical: 3, paddingHorizontal: Spacing.lg, flexDirection: 'row', alignItems: 'flex-end', gap: Spacing.sm },
  wrapperUser: { justifyContent: 'flex-end' },
  wrapperBot:  { justifyContent: 'flex-start' },
  nancyDot:    { width: 8, height: 8, borderRadius: 4, backgroundColor: Colors.accent + '60', marginBottom: 16, flexShrink: 0 },
  bubble:      { maxWidth: '82%', borderRadius: Radius.xl, paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  bubbleUser:  { backgroundColor: Colors.bgUserBubble, borderBottomRightRadius: Radius.sm, borderWidth: 0.5, borderColor: Colors.borderBlue },
  bubbleBot:   { backgroundColor: Colors.bgCard, borderBottomLeftRadius: Radius.sm, borderWidth: 0.5, borderColor: Colors.border },
  textUser:    { ...Typography.body, color: Colors.text, lineHeight: 24 },
  footer:      { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', marginTop: Spacing.xs, gap: Spacing.xs },
  memoryTag:   { backgroundColor: Colors.accentPurple + '15', borderRadius: Radius.sm, paddingHorizontal: 5, paddingVertical: 1 },
  memoryText:  { fontSize: 10 },
  time:        { ...Typography.caption, color: Colors.textHint },
  menuOverlay: { flex: 1, backgroundColor: '#00000066', justifyContent: 'center', alignItems: 'center' },
  menu:        { backgroundColor: Colors.bgCard, borderRadius: Radius.lg, padding: Spacing.xs, borderWidth: 0.5, borderColor: Colors.border, minWidth: 180 },
  menuItem:    { flexDirection: 'row', alignItems: 'center', gap: Spacing.md, padding: Spacing.md, borderRadius: Radius.md },
  menuText:    { ...Typography.body, color: Colors.text },
  editOverlay: { flex: 1, backgroundColor: '#00000088', justifyContent: 'flex-end' },
  editCard:    { backgroundColor: Colors.bgCard, borderRadius: Radius.xl, padding: Spacing.xl, margin: Spacing.lg, gap: Spacing.md, borderWidth: 0.5, borderColor: Colors.border },
  editHeader:  { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  editTitle:   { ...Typography.heading, color: Colors.text },
  editInput:   { backgroundColor: Colors.bgInput, color: Colors.text, borderWidth: 0.5, borderColor: Colors.border, borderRadius: Radius.md, paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md, fontSize: 16, minHeight: 80, textAlignVertical: 'top' },
  editActions: { flexDirection: 'row', gap: Spacing.md },
  editCancel:  { flex: 1, paddingVertical: Spacing.md, alignItems: 'center', borderRadius: Radius.md, borderWidth: 0.5, borderColor: Colors.border },
  editCancelText: { ...Typography.label, color: Colors.textMuted },
  editResend:  { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: Spacing.sm, paddingVertical: Spacing.md, borderRadius: Radius.md, backgroundColor: Colors.accent },
  editResendText: { ...Typography.label, color: '#fff', fontWeight: '600' },
})

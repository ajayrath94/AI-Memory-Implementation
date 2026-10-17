import React, { useState } from 'react'
import {
  View, Text, StyleSheet, TouchableOpacity,
  Modal, TextInput, TouchableWithoutFeedback,
  Keyboard, Linking,
} from 'react-native'
import Markdown from 'react-native-markdown-display'
import { Ionicons } from '@expo/vector-icons'
import { Colors, Typography, Spacing, Radius } from '../../constants'
import { YouTubePlayer } from '../media/YouTubePlayer'
import { useAppStore } from '../../store/appStore'
import { LINK, pick } from '../../i18n/words'
import { ListCard } from './ListCard'

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
  onSpeak?:  () => void
  speaking?: boolean
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

// Links become large buttons under the message. They were plain text she
// could not tap — "https://www.google.com/maps/search/?api=1&query=Malnad%20Chai…"
// in the middle of a sentence.
//
// Two shapes arrive. A bare link (a map from an offer). And [name](link), which
// Nancy writes for places and news so each button can carry its own name —
// four news buttons all saying "news.google.com kholo" told her nothing. A
// tel: link is a call button. YouTube is left alone: it has its own player.
type Btn = { url: string; name?: string }

const MD_LINK = /\[([^\]]+)\]\(((?:https?:\/\/|tel:)[^)\s]+)\)/g
const isYouTube = (u: string) => /youtube\.com\/watch|youtu\.be\//.test(u)

function linkButtons(text: string): Btn[] {
  const out: Btn[] = []
  const seen = new Set<string>()
  const add = (b: Btn) => { if (!seen.has(b.url)) { seen.add(b.url); out.push(b) } }
  let m: RegExpExecArray | null
  const md = new RegExp(MD_LINK.source, 'g')
  while ((m = md.exec(text))) {
    if (!isYouTube(m[2])) add({ url: m[2], name: m[1].trim() })
  }
  const bare = /(?:https?:\/\/[^\s<>()\]]+|tel:\+?[\d-]{6,})/g
  while ((m = bare.exec(text))) {
    if (text.slice(Math.max(0, m.index - 2), m.index) === '](') continue
    const url = m[0].replace(/[.,;:!?]+$/, '')
    if (isYouTube(url)) continue
    add({ url })
  }
  return out
}

// The text without the links: a line that is only a link goes (it is the
// button now); a link inside a sentence leaves its name; a bare link goes.
function withoutLinks(text: string, btns: Btn[]): string {
  let t = text.replace(/^[ \t]*(?:[-*•][ \t]*)?\[[^\]]+\]\(((?:https?:\/\/|tel:)[^)\s]+)\)[ \t]*$/gm,
                       (all, url) => (isYouTube(url) ? all : ''))
  t = t.replace(new RegExp(MD_LINK.source, 'g'), (all, name, url) => (isYouTube(url) ? all : name))
  for (const b of btns) if (!b.name) t = t.split(b.url).join('')
  return t.replace(/\n{3,}/g, '\n\n')
}

// The button's words in her language (i18n/words.ts LINK).
function linkLabel(b: Btn, lang: string): string {
  const url = b.url
  const name = (b.name || '').replace(/^📞\s*/, '').trim()
  if (url.startsWith('tel:')) {
    return `📞  ${pick(LINK.call, lang, { name: name || url.slice(4) })}`
  }
  const isMap = /google\.[^/]+\/maps|maps\.google\.|maps\.app\.goo\.gl|goo\.gl\/maps/.test(url)
  if (isMap) {
    if (name) return `📍  ${pick(LINK.map, lang, { name })}`
    const q = url.match(/[?&]query=([^&]+)/)
    let place = ''
    try { place = q ? decodeURIComponent(q[1].replace(/\+/g, ' ')) : '' } catch {}
    return place && !/^[-\d.,\s]+$/.test(place)
      ? `📍  ${pick(LINK.map, lang, { name: place })}` : `📍  ${pick(LINK.mapBare, lang)}`
  }
  if (/news\.google\./.test(url)) return `📰  ${pick(LINK.news, lang, { name: name || pick(LINK.newsName, lang) })}`
  const host = (url.match(/^https?:\/\/(?:www\.)?([^/?#]+)/) || [])[1] || 'link'
  return `🔗  ${pick(LINK.open, lang, { name: name || host })}`
}

export function MessageBubble({ message, onResend, onSpeak, speaking }: Props) {
  const isUser = message.role === 'user'
  const lang   = useAppStore(s => s.language)
  const time   = new Date(message.timestamp).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit'
  })

  const [showMenu, setShowMenu] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editText, setEditText] = useState(message.content)

  const videoId   = !isUser ? extractYouTube(message.content) : null
  // A list Nancy read carries its card as [[list:<id>]] (memory/lists.py).
  const cardIds   = !isUser ? Array.from(new Set(
    (message.content.match(/\[\[list:([0-9a-fA-F-]{8,})\]\]/g) || []).map(m => m.slice(7, -2)))) : []
  const links     = !isUser ? linkButtons(message.content) : []
  let cleanMsg    = videoId ? cleanText(message.content) : message.content
  if (links.length) cleanMsg = withoutLinks(cleanMsg, links)
  cleanMsg = cleanMsg.replace(/\[\[list:[^\]]*\]\]/g, '').trim()
  cleanMsg = cleanMsg.replace(/[ \t]+([.,;:!?])/g, '$1').replace(/:\s*$/, '.').trim()

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

            {cardIds.map(id => <ListCard key={id} listId={id} />)}

            {links.map(b => (
              <TouchableOpacity key={b.url} activeOpacity={0.75}
                onPress={() => Linking.openURL(b.url).catch(() => {})}
                style={styles.linkBtn}>
                <Text style={styles.linkText} numberOfLines={2}>{linkLabel(b, lang)}</Text>
                <Ionicons name={b.url.startsWith('tel:') ? 'call-outline' : 'open-outline'}
                  size={18} color={Colors.accent} />
              </TouchableOpacity>
            ))}

            {videoId && (
              <YouTubePlayer video={{
                video_id:    videoId,
                // Blank rather than 'Nancy recommends': the companion may
                // be called something else, and the message above already
                // says what this is.
                title:       '',
                channel:     '',
                youtube_url: `https://www.youtube.com/watch?v=${videoId}`,
              }} />
            )}

            <View style={styles.footer}>
              {/* Hearing it rather than reading it. She is seventy; for
                  anyone whose eyes are going this is the difference between
                  using the app and not.

                  Always shown, not hidden behind a setting — she will not go
                  looking. The preference decides whether it also plays on
                  its own. */}
              {!isUser && (
                <TouchableOpacity
                  onPress={onSpeak}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                  style={styles.speakBtn}
                >
                  <Ionicons
                    name={speaking ? 'volume-high' : 'volume-medium-outline'}
                    size={15}
                    color={speaking ? Colors.accent : Colors.textHint}
                  />
                </TouchableOpacity>
              )}
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
  linkBtn:     { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: Spacing.sm,
                 marginTop: Spacing.sm, paddingVertical: 12, paddingHorizontal: Spacing.md,
                 borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.accent + '66',
                 backgroundColor: Colors.accent + '14' },
  linkText:    { flex: 1, color: Colors.accent, fontSize: 16, fontWeight: '600' },
  speakBtn: {
    paddingRight: 6,
    paddingVertical: 2,
  },
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

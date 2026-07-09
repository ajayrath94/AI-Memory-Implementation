import React, { useState } from 'react'
import {
  View, Text, StyleSheet, TouchableOpacity,
  Linking, ActivityIndicator, Image,
} from 'react-native'
import { WebView } from 'react-native-webview'
import { Ionicons } from '@expo/vector-icons'
import { Colors, Spacing, Radius, Typography } from '../../constants'

interface YouTubeVideo {
  video_id:    string
  title:       string
  channel:     string
  youtube_url: string
  thumbnail?:  string
}

interface Props {
  video: YouTubeVideo
}

export function YouTubePlayer({ video }: Props) {
  const [playing,  setPlaying]  = useState(false)
  const [loading,  setLoading]  = useState(false)

  const embedUrl = `https://www.youtube-nocookie.com/embed/${video.video_id}?autoplay=1&playsinline=1&rel=0&modestbranding=1&fs=1`

  const handlePlay = () => {
    setPlaying(true)
    setLoading(true)
  }

  const openInYouTube = () => {
    Linking.openURL(video.youtube_url)
  }

  if (playing) {
    return (
      <View style={styles.playerContainer}>
        {loading && (
          <View style={styles.loadingOverlay}>
            <ActivityIndicator color={Colors.accent} size="large" />
          </View>
        )}
        <WebView
          source={{ uri: embedUrl }}
          style={styles.webview}
          allowsInlineMediaPlayback
          mediaPlaybackRequiresUserAction={false}
          onLoad={() => setLoading(false)}
          onError={() => { setPlaying(false); openInYouTube() }}
          javaScriptEnabled
          allowsFullscreenVideo
        />
        <TouchableOpacity style={styles.closeBtn} onPress={() => setPlaying(false)}>
          <Ionicons name="close-circle" size={28} color="#fff" />
        </TouchableOpacity>
      </View>
    )
  }

  return (
    <View style={styles.card}>
      {/* Thumbnail */}
      <TouchableOpacity style={styles.thumbnailWrap} onPress={handlePlay} activeOpacity={0.9}>
        {video.thumbnail ? (
          <Image source={{ uri: video.thumbnail }} style={styles.thumbnail} resizeMode="cover" />
        ) : (
          <View style={styles.thumbnailPlaceholder}>
            <Ionicons name="musical-notes" size={32} color={Colors.textMuted} />
          </View>
        )}

        {/* Play button overlay */}
        <View style={styles.playOverlay}>
          <View style={styles.playBtn}>
            <Ionicons name="play" size={24} color="#fff" />
          </View>
        </View>

        {/* YouTube logo */}
        <View style={styles.ytBadge}>
          <Text style={styles.ytText}>▶ YouTube</Text>
        </View>
      </TouchableOpacity>

      {/* Info */}
      <View style={styles.info}>
        <Text style={styles.title} numberOfLines={2}>{video.title}</Text>
        <Text style={styles.channel} numberOfLines={1}>{video.channel}</Text>

        <View style={styles.actions}>
          <TouchableOpacity style={styles.playAction} onPress={handlePlay}>
            <Ionicons name="play-circle" size={18} color={Colors.accent} />
            <Text style={styles.playActionText}>Play in app</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.openAction} onPress={openInYouTube}>
            <Ionicons name="open-outline" size={16} color={Colors.textMuted} />
            <Text style={styles.openActionText}>Open YouTube</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  )
}

// ── Music recommendations list ─────────────────────────────────────────────────
interface MusicCardProps {
  videos: YouTubeVideo[]
  query:  string
}

export function MusicRecommendations({ videos, query }: MusicCardProps) {
  if (!videos || videos.length === 0) return null

  return (
    <View style={styles.musicCard}>
      <View style={styles.musicHeader}>
        <Text style={styles.musicIcon}>🎵</Text>
        <Text style={styles.musicTitle}>Nancy suggests</Text>
      </View>
      <Text style={styles.musicQuery}>{query}</Text>
      {videos.slice(0, 3).map((video, i) => (
        <YouTubePlayer key={video.video_id || i} video={video} />
      ))}
    </View>
  )
}

const styles = StyleSheet.create({
  // Player
  playerContainer: {
    width:         '100%',
    aspectRatio:   16 / 9,
    borderRadius:  Radius.lg,
    overflow:      'hidden',
    backgroundColor: '#000',
    marginVertical: Spacing.sm,
    position:      'relative',
  },
  webview:      { flex: 1 },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: '#000',
    alignItems:      'center',
    justifyContent:  'center',
    zIndex:          10,
  },
  closeBtn: {
    position: 'absolute',
    top:      8,
    right:    8,
    zIndex:   20,
  },

  // Thumbnail card
  card: {
    backgroundColor: Colors.bgCard,
    borderRadius:    Radius.lg,
    overflow:        'hidden',
    borderWidth:     0.5,
    borderColor:     Colors.border,
    marginVertical:  Spacing.xs,
  },
  thumbnailWrap: {
    width:       '100%',
    aspectRatio: 16 / 9,
    position:    'relative',
  },
  thumbnail: {
    width:  '100%',
    height: '100%',
  },
  thumbnailPlaceholder: {
    width:           '100%',
    height:          '100%',
    backgroundColor: Colors.bgInput,
    alignItems:      'center',
    justifyContent:  'center',
  },
  playOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems:      'center',
    justifyContent:  'center',
    backgroundColor: '#00000044',
  },
  playBtn: {
    width:           56,
    height:          56,
    borderRadius:    28,
    backgroundColor: Colors.accentRed,
    alignItems:      'center',
    justifyContent:  'center',
    paddingLeft:     4,
  },
  ytBadge: {
    position:        'absolute',
    bottom:          8,
    right:           8,
    backgroundColor: '#00000088',
    borderRadius:    4,
    paddingHorizontal: 6,
    paddingVertical:   3,
  },
  ytText: { color: '#fff', fontSize: 10, fontWeight: '600' },

  // Info
  info: { padding: Spacing.md, gap: Spacing.xs },
  title: {
    ...Typography.label,
    color:      Colors.text,
    fontWeight: '600',
    lineHeight: 18,
  },
  channel: { ...Typography.caption, color: Colors.textMuted },
  actions: {
    flexDirection: 'row',
    gap:           Spacing.md,
    marginTop:     Spacing.xs,
  },
  playAction: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           4,
  },
  playActionText: { ...Typography.caption, color: Colors.accent, fontWeight: '600' },
  openAction: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           4,
  },
  openActionText: { ...Typography.caption, color: Colors.textMuted },

  // Music recommendations wrapper
  musicCard: {
    backgroundColor: Colors.bgCard,
    borderRadius:    Radius.lg,
    padding:         Spacing.lg,
    borderWidth:     0.5,
    borderColor:     Colors.border,
    gap:             Spacing.md,
    marginVertical:  Spacing.sm,
  },
  musicHeader: {
    flexDirection: 'row',
    alignItems:    'center',
    gap:           Spacing.sm,
  },
  musicIcon:  { fontSize: 20 },
  musicTitle: { ...Typography.heading, color: Colors.text },
  musicQuery: { ...Typography.caption, color: Colors.textMuted },
})

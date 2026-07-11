/**
 * useTheme — Dynamic theme hook
 * Returns colors adjusted for current background selection
 * Light backgrounds → dark text
 * Dark backgrounds → light text
 */

import { useAppStore } from '../store/appStore'

// Determine if a hex color is light or dark
function isLightColor(hex: string): boolean {
  const h = hex.replace('#', '')
  const r = parseInt(h.substring(0, 2), 16)
  const g = parseInt(h.substring(2, 4), 16)
  const b = parseInt(h.substring(4, 6), 16)
  // Perceived luminance formula
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.5
}

export function useTheme() {
  const { bgColor } = useAppStore()
  const bg      = bgColor || '#0a0a0a'
  const isLight = isLightColor(bg)

  return {
    // Backgrounds
    bg,
    bgCard:    isLight ? '#ffffff'  : '#1a1a1a',
    bgInput:   isLight ? '#f0f0f0'  : '#111111',
    bgSidebar: isLight ? '#f5f5f5'  : '#0d0d0d',

    // Text
    text:       isLight ? '#1a1a1a'  : '#f0f0f0',
    textSecond: isLight ? '#333333'  : '#cccccc',
    textMuted:  isLight ? '#666666'  : '#888888',
    textHint:   isLight ? '#999999'  : '#555555',

    // Borders
    border:     isLight ? '#e0e0e0'  : '#2a2a2a',
    borderBlue: isLight ? '#90b8e0'  : '#2a4a6a',

    // Accent (stays same regardless of theme)
    accent:       '#4a90d9',
    accentGreen:  '#4caf50',
    accentRed:    '#e53935',
    accentWarm:   '#ff9800',
    accentPurple: '#9c27b0',

    // Chat bubbles
    bgUserBubble: isLight ? '#ddeeff'  : '#1e3a5f',

    // Status bar
    statusBar: isLight ? 'dark' : 'light',

    // Is light theme (useful for conditional styling)
    isLight,
  }
}

// Static version for use outside components
export function getThemeColors(bgColor: string) {
  const bg      = bgColor || '#0a0a0a'
  const isLight = isLightColor(bg)

  return {
    bg,
    text:      isLight ? '#1a1a1a' : '#f0f0f0',
    textMuted: isLight ? '#666666' : '#888888',
    bgCard:    isLight ? '#ffffff' : '#1a1a1a',
    border:    isLight ? '#e0e0e0' : '#2a2a2a',
    isLight,
  }
}

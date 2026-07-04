// ── Nancy Design System ────────────────────────────────────────────────────────
// Production-grade design tokens for Nancy AI companion app
// Two audiences: elderly user (warm, simple, large) + caregiver (professional, data-rich)

// ── Color Palette ──────────────────────────────────────────────────────────────
export const Colors = {
  // Backgrounds
  bg:           '#0a0a0a',
  bgCard:       '#141414',
  bgInput:      '#1c1c1c',
  bgUserBubble: '#1a3a5c',
  bgNancyBubble:'#1a1a1a',

  // Borders
  border:       '#252525',
  borderBlue:   '#1e4a7a',
  borderSubtle: '#1a1a1a',

  // Text
  text:         '#f0f0f0',
  textSecond:   '#b0b0b0',
  textMuted:    '#606060',
  textHint:     '#383838',

  // Brand
  accent:       '#4a90d9',       // Nancy blue
  accentWarm:   '#e8875a',       // Warm orange — emotional contexts
  accentGreen:  '#3dba7a',       // Positive/health good
  accentRed:    '#d94a4a',       // Alerts/danger
  accentPurple: '#7a5ad9',       // Memory/intelligence

  // Nancy persona color
  nancy:        '#4a90d9',
  nancyGlow:    '#4a90d915',

  // Status
  success:      '#3dba7a',
  warning:      '#e8a23a',
  danger:       '#d94a4a',
  info:         '#4a90d9',

  // Pillar colors (subtle, for caregiver view only)
  pillar: {
    HEALTH_WELLNESS: '#d94a4a22',
    SADNESS:         '#7a5ad922',
    STRESS:          '#e8875a22',
    JOY:             '#3dba7a22',
    LOVE:            '#d94a7a22',
    ENTERTAINMENT:   '#e8a23a22',
    FINANCE:         '#4a90d922',
    GENERAL:         '#25252522',
  }
}

// ── Typography ─────────────────────────────────────────────────────────────────
export const Typography = {
  // Display — for Nancy's name, hero text
  display: { fontSize: 28, fontWeight: '700' as const, letterSpacing: -0.5 },
  // Title — screen titles, section headers
  title:   { fontSize: 20, fontWeight: '600' as const, letterSpacing: -0.3 },
  // Heading — card headers, group labels
  heading: { fontSize: 17, fontWeight: '600' as const, letterSpacing: -0.2 },
  // Body — main content, chat bubbles
  body:    { fontSize: 16, fontWeight: '400' as const, lineHeight: 24 },
  // Body large — for elderly users (larger text)
  bodyLg:  { fontSize: 18, fontWeight: '400' as const, lineHeight: 28 },
  // Label — secondary info, metadata
  label:   { fontSize: 13, fontWeight: '500' as const },
  // Caption — timestamps, hints, subtle info
  caption: { fontSize: 11, fontWeight: '400' as const },
}

// ── Spacing ────────────────────────────────────────────────────────────────────
export const Spacing = {
  xs:  4,
  sm:  8,
  md:  12,
  lg:  16,
  xl:  24,
  xxl: 32,
}

// ── Border Radius ──────────────────────────────────────────────────────────────
export const Radius = {
  sm:   8,
  md:   12,
  lg:   16,
  xl:   24,
  full: 999,
}

// ── Shadows ────────────────────────────────────────────────────────────────────
export const Shadow = {
  sm: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 2,
  },
  md: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 12,
    elevation: 6,
  },
}

// ── API ────────────────────────────────────────────────────────────────────────
const DEV_IP = 'ai-memory-implementation-production.up.railway.app'  // ← update to your local IP
export const API_BASE   = __DEV__ ? `https://${DEV_IP}` : 'https://ai-memory-implementation-production.up.railway.app'
export const API_KEY    = 'jSQ2qdMyXMJq4Y8dwcQuDjkc7zp_vB79uHvCvDTKVZA'

// ── AI Models ──────────────────────────────────────────────────────────────────
export const MODELS = [
  { label: 'Claude Haiku',  value: 'claude-haiku-4-5',           provider: 'Anthropic' },
  { label: 'Claude Sonnet', value: 'claude-sonnet-4-20250514',    provider: 'Anthropic' },
  { label: 'GPT-4o Mini',   value: 'gpt-4o-mini',                provider: 'OpenAI'    },
  { label: 'Gemini Flash',  value: 'gemini-2.0-flash',           provider: 'Google'    },
  { label: 'Llama 70B',     value: 'llama-3.3-70b-versatile',    provider: 'Groq'      },
]

export const DEFAULT_MODEL = 'claude-haiku-4-5'

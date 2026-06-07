// ── Colors ─────────────────────────────────────────────────────────────────────
export const Colors = {
  bg:           '#0f0f0f',
  bgCard:       '#161616',
  bgInput:      '#1a1a1a',
  bgUserBubble: '#1e3a5f',
  border:       '#2a2a2a',
  borderBlue:   '#2a4f7a',
  text:         '#e8e8e8',
  textMuted:    '#666',
  textHint:     '#444',
  accent:       '#4a8fd4',
  accentRed:    '#e05555',
  accentGreen:  '#4caf7d',
  pill: {
    FINANCE:         '#1a3a2a',
    ASPIRATIONS:     '#2a1a3a',
    CAREER_GOAL:     '#1a2a3a',
    HEALTH_WELLNESS: '#1a3a1a',
    ENTERTAINMENT:   '#3a2a1a',
    GENERAL:         '#2a2a2a',
    STRESS:          '#3a1a1a',
    JOY:             '#1a3a2a',
    NEUTRAL:         '#222',
  }
}

// ── API ────────────────────────────────────────────────────────────────────────
// Change this to your machine's local IP when testing on a real device
// e.g. 'http://192.168.1.10:8000'  (find with: ifconfig | grep inet)
export const API_BASE = 'http://localhost:8000'

// ── AI Models ──────────────────────────────────────────────────────────────────
export const MODELS = [
  { label: 'Claude Sonnet', value: 'claude-sonnet-4-20250514',  provider: 'Anthropic' },
  { label: 'Claude Haiku',  value: 'claude-haiku-4-5-20251001', provider: 'Anthropic' },
  { label: 'GPT-4o',        value: 'gpt-4o',                    provider: 'OpenAI'    },
  { label: 'GPT-4o Mini',   value: 'gpt-4o-mini',               provider: 'OpenAI'    },
  { label: 'Gemini 1.5',    value: 'gemini-1.5-pro',            provider: 'Google'    },
]

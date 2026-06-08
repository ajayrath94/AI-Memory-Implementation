// ── Colors ────────────────────────────────────────────────────────────────────
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
export const API_BASE = 'http://192.168.1.8:8000'

// ── AI Models ──────────────────────────────────────────────────────────────────
export const MODELS = [
  // ── Anthropic
  { label: 'Claude Sonnet',      value: 'claude-sonnet-4-20250514',           provider: 'Anthropic'  },
  { label: 'Claude Haiku',       value: 'claude-haiku-4-5-20251001',          provider: 'Anthropic'  },
  { label: 'Claude Opus',        value: 'claude-opus-4-20250514',             provider: 'Anthropic'  },
  // ── Google
  { label: 'Gemini 2.0 Flash',   value: 'gemini-2.0-flash',                  provider: 'Google'     },
  { label: 'Gemini 1.5 Pro',     value: 'gemini-1.5-pro',                    provider: 'Google'     },
  { label: 'Gemini 1.5 Flash',   value: 'gemini-1.5-flash',                  provider: 'Google'     },
  // ── xAI
  { label: 'Grok 2',             value: 'grok-2',                            provider: 'xAI'        },
  { label: 'Grok 2 Mini',        value: 'grok-2-mini',                       provider: 'xAI'        },
  // ── Mistral
  { label: 'Mistral Large',      value: 'mistral-large-latest',              provider: 'Mistral'    },
  { label: 'Mistral Small',      value: 'mistral-small-latest',              provider: 'Mistral'    },
  { label: 'Codestral',          value: 'codestral-latest',                  provider: 'Mistral'    },
  // ── OpenAI
  { label: 'GPT-4o',             value: 'gpt-4o',                            provider: 'OpenAI'     },
  { label: 'GPT-4o Mini',        value: 'gpt-4o-mini',                       provider: 'OpenAI'     },
  { label: 'o3 Mini',            value: 'o3-mini',                           provider: 'OpenAI'     },
  // ── Groq (fast Llama)
  { label: 'Llama 3.3 70B',      value: 'llama-3.3-70b-versatile',          provider: 'Groq'       },
  { label: 'Llama 3.1 8B',       value: 'llama-3.1-8b-instant',             provider: 'Groq'       },
  { label: 'DeepSeek R1 (Groq)', value: 'deepseek-r1-distill-llama-70b',    provider: 'Groq'       },
  // ── DeepSeek (Chinese 🇨🇳)
  { label: 'DeepSeek V3',        value: 'deepseek-chat',                    provider: 'DeepSeek'   },
  { label: 'DeepSeek R1',        value: 'deepseek-reasoner',                provider: 'DeepSeek'   },
  // ── Alibaba Qwen (Chinese 🇨🇳)
  { label: 'Qwen Max',           value: 'qwen-max',                         provider: 'Alibaba'    },
  { label: 'Qwen Plus',          value: 'qwen-plus',                        provider: 'Alibaba'    },
  { label: 'Qwen Turbo',         value: 'qwen-turbo',                       provider: 'Alibaba'    },
  // ── Baidu ERNIE (Chinese 🇨🇳)
  { label: 'ERNIE 4.0',          value: 'ernie-4.0-8k',                     provider: 'Baidu'      },
  { label: 'ERNIE Speed',        value: 'ernie-speed-128k',                 provider: 'Baidu'      },
  // ── Zhipu GLM (Chinese 🇨🇳)
  { label: 'GLM-4',              value: 'glm-4',                            provider: 'Zhipu'      },
  { label: 'GLM-4 Flash',        value: 'glm-4-flash',                     provider: 'Zhipu'      },
  // ── Moonshot Kimi (Chinese 🇨🇳)
  { label: 'Kimi (128k)',        value: 'moonshot-v1-128k',                 provider: 'Moonshot'   },
  // ── Perplexity
  { label: 'Sonar Large',        value: 'llama-3.1-sonar-large-128k-online',provider: 'Perplexity' },
  { label: 'Sonar Small',        value: 'llama-3.1-sonar-small-128k-online',provider: 'Perplexity' },
  // ── Cohere
  { label: 'Command R+',         value: 'command-r-plus',                   provider: 'Cohere'     },
  { label: 'Command R',          value: 'command-r',                        provider: 'Cohere'     },
  // ── Together AI (open source)
  { label: 'Mixtral 8x22B',      value: 'mistralai/Mixtral-8x22B-Instruct-v0.1', provider: 'Together' },
  { label: 'Llama 3 70B',        value: 'meta-llama/Llama-3-70b-chat-hf',  provider: 'Together'   },
]

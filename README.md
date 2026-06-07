# AI Memory App

Multi-engine AI chat with three-layered vector memory, pillar classification, voice + text interface.

## Stack
```
📱 React Native (Expo)   →  mobile/
🐍 FastAPI (Python)      →  backend/
```

---

## Setup — Backend (Python)

```bash
cd backend

# 1. Create virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your API keys
cp .env.example .env
# Open .env and fill in ANTHROPIC_API_KEY (minimum required)

# 4. Run the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Test it's working: open http://localhost:8000 in your browser — should show `{"status": "AI Memory API running"}`

---

## Setup — Mobile (React Native + Expo)

```bash
cd mobile

# 1. Install dependencies
npm install

# 2. Set your backend IP
# Open constants/index.ts
# If testing on a real iPhone, change API_BASE from localhost to your Mac's IP:
#   Run: ifconfig | grep "inet " | grep -v 127
#   e.g. API_BASE = 'http://192.168.1.10:8000'

# 3. Start Expo
npx expo start
```

Then:
- **iPhone**: Install Expo Go from App Store → scan QR code
- **Simulator**: Press `i` in terminal

---

## Running both together

```bash
# Terminal 1 — Backend
cd backend && source venv/bin/activate && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Mobile
cd mobile && npx expo start
```

---

## Project Structure

```
AI-Memory-Implementation/
├── backend/
│   ├── main.py                          ← FastAPI app
│   ├── requirements.txt
│   ├── .env.example                     ← Copy to .env
│   ├── classifier/
│   │   └── pillar_classifier.py         ← Core/Emotion/Functional/Modifiers
│   ├── memory/
│   │   ├── cache/cache_memory.py        ← M(x,t) vector field, α-blend
│   │   ├── recall/recall_memory.py      ← Cosine similarity, STM/LTM
│   │   └── decay/decay_memory.py        ← λ decay, void threshold
│   ├── store/
│   │   └── pillar_vector_store.py       ← Cross-pillar correlation tracking
│   ├── engine/
│   │   └── engine_router.py             ← Claude / GPT / Gemini switcher
│   └── routes/
│       ├── chat.py                      ← POST /chat/
│       └── memory.py                    ← GET /memory/cache, /stm, /ltm, etc.
│
└── mobile/
    ├── app.json                         ← Expo config
    ├── package.json
    ├── app/
    │   ├── _layout.tsx                  ← Root layout
    │   └── index.tsx                    ← Main chat screen
    ├── components/
    │   ├── chat/
    │   │   ├── MessageBubble.tsx
    │   │   ├── ChatInput.tsx            ← Voice + text input bar
    │   │   └── ModelPicker.tsx          ← Model switcher sheet
    │   └── memory/
    │       └── PillarBadge.tsx          ← Shows active pillars
    ├── hooks/
    │   ├── useChat.ts                   ← Send message logic
    │   └── useVoice.ts                  ← Voice recognition
    ├── services/api.ts                  ← All API calls to backend
    ├── store/appStore.ts                ← Zustand global state
    └── constants/index.ts              ← Colors, models, API_BASE
```

---

## Phase 2 Roadmap
- [ ] Real embeddings (Anthropic Embeddings API)
- [ ] Supabase for persistent LTM across sessions
- [ ] User auth — memories scoped per user
- [ ] Memory debug screen — visualize slots + decay

import React, { useState } from 'react'
import TextInput from './interface/text/TextInput.jsx'
import VoiceInput from './interface/voice/VoiceInput.jsx'
import { processInput } from './engine/EngineRouter.js'

export default function App() {
  const [messages, setMessages] = useState([])
  const [model, setModel] = useState('claude-sonnet-4-20250514')
  const [loading, setLoading] = useState(false)

  const handleInput = async (text) => {
    if (!text.trim()) return
    const userMsg = { role: 'user', content: text, ts: Date.now() }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)
    try {
      const reply = await processInput(text, model, messages)
      setMessages(prev => [...prev, { role: 'assistant', content: reply, ts: Date.now() }])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>

      {/* Header */}
      <div style={{ padding: '12px 20px', borderBottom: '1px solid #222', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontWeight: 600, letterSpacing: '0.02em' }}>AI Memory</span>
        <select
          value={model}
          onChange={e => setModel(e.target.value)}
          style={{ background: '#1a1a1a', color: '#e8e8e8', border: '1px solid #333', borderRadius: 6, padding: '4px 8px', fontSize: 13 }}
        >
          <option value="claude-sonnet-4-20250514">Sonnet</option>
          <option value="claude-haiku-4-5-20251001">Haiku</option>
          <option value="claude-opus-4-20250514">Opus</option>
        </select>
      </div>

      {/* Message thread */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {messages.length === 0 && (
          <div style={{ color: '#555', textAlign: 'center', marginTop: 60, fontSize: 14 }}>
            Start a conversation — voice or text
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            background: m.role === 'user' ? '#1e3a5f' : '#1a1a1a',
            border: '1px solid ' + (m.role === 'user' ? '#2a4f7a' : '#2a2a2a'),
            borderRadius: 10,
            padding: '10px 14px',
            maxWidth: '75%',
            fontSize: 14,
            lineHeight: 1.6,
            whiteSpace: 'pre-wrap',
          }}>
            {m.content}
          </div>
        ))}
        {loading && (
          <div style={{ alignSelf: 'flex-start', color: '#555', fontSize: 13 }}>thinking…</div>
        )}
      </div>

      {/* Input area */}
      <div style={{ padding: '12px 20px', borderTop: '1px solid #222', display: 'flex', gap: 10, alignItems: 'flex-end' }}>
        <VoiceInput onTranscript={handleInput} />
        <TextInput onSubmit={handleInput} loading={loading} />
      </div>

    </div>
  )
}

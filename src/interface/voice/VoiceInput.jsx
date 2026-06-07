import React, { useState, useRef } from 'react'

export default function VoiceInput({ onTranscript }) {
  const [listening, setListening] = useState(false)
  const [supported] = useState(() => 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window)
  const recognitionRef = useRef(null)

  const toggle = () => {
    if (!supported) return alert('Speech recognition not supported in this browser.')

    if (listening) {
      recognitionRef.current?.stop()
      setListening(false)
      return
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    const rec = new SpeechRecognition()
    rec.continuous = false
    rec.interimResults = false
    rec.lang = 'en-US'

    rec.onresult = (e) => {
      const transcript = e.results[0][0].transcript
      if (transcript.trim()) onTranscript(transcript.trim())
    }

    rec.onerror = (e) => {
      console.error('Speech error:', e.error)
      setListening(false)
    }

    rec.onend = () => setListening(false)

    recognitionRef.current = rec
    rec.start()
    setListening(true)
  }

  return (
    <button
      onClick={toggle}
      title={listening ? 'Stop listening' : 'Start voice input'}
      style={{
        background: listening ? '#3a1e1e' : '#1a1a1a',
        color: listening ? '#e05555' : '#888',
        border: '1px solid ' + (listening ? '#5a2e2e' : '#333'),
        borderRadius: 8,
        width: 42,
        height: 42,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: supported ? 'pointer' : 'not-allowed',
        fontSize: 18,
        flexShrink: 0,
        transition: 'all 0.2s',
        animation: listening ? 'pulse 1.2s infinite' : 'none',
      }}
    >
      🎙️
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </button>
  )
}

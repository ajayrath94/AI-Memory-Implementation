import React, { useState } from 'react'

export default function TextInput({ onSubmit, loading }) {
  const [value, setValue] = useState('')

  const submit = () => {
    if (!value.trim() || loading) return
    onSubmit(value.trim())
    setValue('')
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <>
      <textarea
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Type a message… (Enter to send)"
        rows={1}
        style={{
          flex: 1,
          background: '#1a1a1a',
          color: '#e8e8e8',
          border: '1px solid #333',
          borderRadius: 8,
          padding: '10px 14px',
          fontSize: 14,
          resize: 'none',
          outline: 'none',
          lineHeight: 1.5,
          fontFamily: 'inherit',
        }}
      />
      <button
        onClick={submit}
        disabled={!value.trim() || loading}
        style={{
          background: '#1e3a5f',
          color: '#e8e8e8',
          border: '1px solid #2a4f7a',
          borderRadius: 8,
          padding: '10px 18px',
          fontSize: 14,
          cursor: 'pointer',
          opacity: (!value.trim() || loading) ? 0.4 : 1,
          transition: 'opacity 0.2s',
        }}
      >
        Send
      </button>
    </>
  )
}

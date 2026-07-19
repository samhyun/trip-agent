import { useState } from 'react'

function suggestionsFor(stage) {
  switch (stage) {
    case 'active':
      return ['항공·숙소 예약해줘', '결제까지 진행']
    default:
      return []
  }
}

export default function Composer({ stage, dispatch, loading = false }) {
  const [value, setValue] = useState('')
  const suggestions = suggestionsFor(stage)

  const send = (text) => {
    const trimmed = text.trim()
    if (!trimmed || loading) return
    dispatch({ type: 'SEND_TEXT', text: trimmed })
    setValue('')
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    send(value)
  }

  return (
    <div className="composer">
      {suggestions.length > 0 && (
        <div className="composer__suggestions scroll-thin">
          {suggestions.map((label) => (
            <button key={label} type="button" className="chip" disabled={loading} onClick={() => send(label)}>
              {label}
            </button>
          ))}
        </div>
      )}
      <form className="composer__bar" onSubmit={handleSubmit}>
        <span aria-hidden="true" style={{ color: 'var(--faint)', fontSize: 15 }}>
          ＋
        </span>
        <input
          className="composer__input"
          placeholder={loading ? '답변을 기다리는 중…' : "메시지를 입력하세요… (예: '예약 진행')"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={loading}
        />
        <button type="submit" className="composer__send" disabled={!value.trim() || loading} aria-label="전송">
          ↑
        </button>
      </form>
    </div>
  )
}

import { useState } from 'react'

function suggestionsFor(stage) {
  switch (stage) {
    case 'jeju:itinerary':
    case 'bohol:itinerary':
      return ['일정 수정', '항공·숙소 예약']
    case 'jeju:pay':
    case 'bohol:pay':
      return ['결제 진행']
    case 'jeju:done':
    case 'bohol:done':
      return ['새 여행 시작하기']
    default:
      return []
  }
}

export default function Composer({ stage, dispatch }) {
  const [value, setValue] = useState('')
  const suggestions = suggestionsFor(stage)

  const send = (text) => {
    const trimmed = text.trim()
    if (!trimmed) return
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
            <button key={label} type="button" className="chip" onClick={() => send(label)}>
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
          placeholder="메시지를 입력하세요… (예: '예약 진행')"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <button type="submit" className="composer__send" disabled={!value.trim()} aria-label="전송">
          ↑
        </button>
      </form>
    </div>
  )
}

import { useEffect, useRef } from 'react'
import MessageRenderer from './MessageRenderer'

export default function MessageList({ messages, trip, stage, dispatch }) {
  const scrollRef = useRef(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  return (
    <div className="message-list scroll-thin" ref={scrollRef}>
      <div className="message-list__marker">오늘 · 여행 계획을 시작해 볼까요?</div>
      {messages.map((message, index) => (
        <MessageRenderer
          key={message.id}
          message={message}
          trip={trip}
          stage={stage}
          dispatch={dispatch}
          isLatest={index === messages.length - 1}
        />
      ))}
    </div>
  )
}

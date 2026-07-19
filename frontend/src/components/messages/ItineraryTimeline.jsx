import { useState } from 'react'
import { renderRich } from '../../lib/richText'

// 백엔드 itinerary 는 LLM 이 서술한 자유 텍스트(markdown)라 day/시간 구조로 안정적
// 파싱이 어렵다. 그래서 정합성은 "프론트가 markdown 도 렌더" 하는 쪽으로 맞춘다.
// payload.days(구조화)가 있으면 접이식 타임라인, 없으면 payload.markdown 을 렌더한다.

// 아주 가벼운 markdown 렌더러 (제목/리스트/굵게/줄바꿈만). 외부 의존성 없음.
function ItineraryMarkdown({ text }) {
  const lines = (text || '').split('\n')
  return (
    <div className="card card-lg fade-up itinerary-md">
      {lines.map((line, i) => {
        const trimmed = line.trim()
        if (!trimmed) return <div key={i} className="itinerary-md__gap" />
        const heading = trimmed.match(/^#{1,6}\s+(.*)$/)
        if (heading) {
          return (
            <div key={i} className="itinerary-md__heading">
              {renderRich(heading[1])}
            </div>
          )
        }
        const bullet = trimmed.match(/^([-*]|\d+\.)\s+(.*)$/)
        if (bullet) {
          return (
            <div key={i} className="itinerary-md__item">
              <span className="itinerary-md__dot">•</span>
              <span>{renderRich(bullet[2])}</span>
            </div>
          )
        }
        return (
          <div key={i} className="itinerary-md__line">
            {renderRich(trimmed)}
          </div>
        )
      })}
    </div>
  )
}

function ItineraryDays({ days }) {
  const [openDay, setOpenDay] = useState(days[0]?.day)

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {days.map((day) => {
        const isOpen = openDay === day.day
        return (
          <div key={day.day} className="itinerary-day">
            <button
              type="button"
              className="itinerary-day__toggle"
              onClick={() => setOpenDay(isOpen ? null : day.day)}
            >
              <span className="itinerary-day__badge">DAY {day.day}</span>
              <span className="itinerary-day__title">{day.title}</span>
              <span className="itinerary-day__date">{day.dateLabel}</span>
              <span className="itinerary-day__chevron">{isOpen ? '▾' : '▸'}</span>
            </button>
            {isOpen && (
              <div className="itinerary-day__items">
                {day.items.map((item) => (
                  <div key={item.time + item.text} className="itinerary-item">
                    <span className="itinerary-item__time">{item.time}</span>
                    <span className={`itinerary-item__dot${item.accent ? ' itinerary-item__dot--accent' : ''}`} />
                    <span className="itinerary-item__text">{item.text}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function ItineraryTimeline({ payload = {} }) {
  const { days, markdown } = payload
  if (Array.isArray(days) && days.length > 0) {
    return <ItineraryDays days={days} />
  }
  return <ItineraryMarkdown text={markdown || ''} />
}

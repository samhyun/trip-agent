import { useState } from 'react'

export default function ItineraryTimeline({ days }) {
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

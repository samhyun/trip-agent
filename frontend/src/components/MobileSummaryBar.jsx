import { won } from '../lib/format'

export default function MobileSummaryBar({ trip, stage, open, onToggle, onProceed }) {
  if (trip.destination === null) return null

  const isDone = stage.endsWith(':done')

  return (
    <div className="mobile-summary">
      <button type="button" className="mobile-summary__toggle" onClick={onToggle}>
        <span aria-hidden="true">🧳</span>
        <span className="mobile-summary__label">
          {trip.destination} · {trip.dateLabel ?? '일정 미정'} · {trip.travelers}명
        </span>
        <span className="mobile-summary__total">{won(trip.total)}</span>
        <span className="mobile-summary__chevron">{open ? '▴' : '▾'}</span>
      </button>

      {open && (
        <div className="mobile-summary__panel">
          <div className="mobile-summary__facts">
            <span>
              📅 <b>{trip.dateLabel ?? '미정'}</b>
            </span>
            <span>
              👤 <b>{trip.travelers}명</b>
            </span>
          </div>

          {trip.spots.length > 0 && (
            <div className="mobile-summary__tags">
              {trip.spots.map((s) => (
                <span key={s.id}>{s.name}</span>
              ))}
            </div>
          )}

          {trip.flight && (
            <div className="mobile-summary__item">
              <span>✈️</span>
              <span>
                {trip.flight.route} · {trip.flight.dep}
              </span>
              <span>{won(trip.flight.price * trip.travelers)}</span>
            </div>
          )}
          {trip.hotels.map((hotel) => (
            <div key={hotel.id} className="mobile-summary__item">
              <span>🏨</span>
              <span>
                {hotel.name} · {hotel.nights}박
              </span>
              <span>{won(hotel.price * hotel.nights)}</span>
            </div>
          ))}

          <button type="button" className="btn btn-accent btn-block" onClick={onProceed}>
            {isDone ? '새 여행 시작' : '예약 진행 →'}
          </button>
        </div>
      )}
    </div>
  )
}

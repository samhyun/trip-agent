import { won } from '../lib/format'

function statusInfo(stage, trip) {
  if (stage === 'welcome') return null
  if (stage.endsWith(':done')) return { label: '예약 확정', done: true }
  if (trip.hotels.length > 0 && trip.flight) return { label: '결제 대기', done: false }
  if (trip.flight) return { label: '항공 예약됨', done: false }
  return { label: '예약 대기', done: false }
}

export default function TripSummaryPanel({ trip, stage, onProceed }) {
  const status = statusInfo(stage, trip)
  const empty = trip.destination === null
  const isDone = stage.endsWith(':done')

  return (
    <aside className="trip-panel trip-panel--desktop">
      <div className="trip-panel__header">
        <strong>내 여행</strong>
        {status && (
          <span className={`trip-panel__status${status.done ? ' trip-panel__status--done' : ''}`}>{status.label}</span>
        )}
      </div>

      <div className="trip-panel__body scroll-thin">
        {empty ? (
          <div className="trip-panel__empty">✈️
            <br />
            여행을 시작해 보세요
          </div>
        ) : (
          <>
            <div className="trip-panel__facts">
              <div className="trip-panel__fact">
                <span>📍</span>
                <span className="trip-panel__fact-label">목적지</span>
                <span className="trip-panel__fact-value">{trip.destination}</span>
              </div>
              <div className="trip-panel__fact">
                <span>📅</span>
                <span className="trip-panel__fact-label">일정</span>
                <span className="trip-panel__fact-value">{trip.dateLabel ?? '미정'}</span>
              </div>
              <div className="trip-panel__fact">
                <span>👤</span>
                <span className="trip-panel__fact-label">인원</span>
                <span className="trip-panel__fact-value">{trip.travelers}명</span>
              </div>
            </div>

            {trip.spots.length > 0 && (
              <>
                <div className="trip-panel__divider" />
                <div>
                  <span className="trip-panel__section-label">담은 명소</span>
                  <div className="trip-panel__spots">
                    {trip.spots.map((s) => (
                      <span key={s.id} className="trip-panel__spot">
                        {s.name}
                      </span>
                    ))}
                  </div>
                </div>
              </>
            )}

            <div className="trip-panel__divider" />
            <div>
              <span className="trip-panel__section-label">예약 항목</span>
              {trip.flight ? (
                <div className="trip-panel__item">
                  <span className="trip-panel__item-icon">✈️</span>
                  <div className="trip-panel__item-meta">
                    <strong>{trip.flight.route}</strong>
                    <span>
                      {trip.flight.air} · {trip.flight.dep}
                    </span>
                  </div>
                  <span className="trip-panel__item-price">{won(trip.flight.price * trip.travelers)}</span>
                </div>
              ) : (
                <div className="trip-panel__item-placeholder">
                  <span>✈️</span>
                  <span>항공 선택 시 갱신</span>
                </div>
              )}
              {trip.hotels.map((hotel) => (
                <div key={hotel.id} className="trip-panel__item">
                  <span className="trip-panel__item-icon">🏨</span>
                  <div className="trip-panel__item-meta">
                    <strong>{hotel.name}</strong>
                    <span>{hotel.nights}박 · {hotel.region}</span>
                  </div>
                  <span className="trip-panel__item-price">{won(hotel.price * hotel.nights)}</span>
                </div>
              ))}
              {trip.hotels.length === 0 && (
                <div className="trip-panel__item-placeholder">
                  <span>🏨</span>
                  <span>숙소 선택 시 갱신</span>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <div className="trip-panel__footer">
        <div className="trip-panel__total-row">
          <span className="trip-panel__total-label">{isDone ? '결제 완료' : '현재 합계'}</span>
          <span className="trip-panel__total-value">{won(trip.total)}</span>
        </div>
        <button type="button" className="btn btn-accent btn-block" disabled={empty} onClick={onProceed}>
          {isDone ? '새 여행 시작' : '예약 진행 →'}
        </button>
        {!empty && !isDone && <div className="trip-panel__hint">👆 버튼 또는 💬 채팅 입력으로 진행</div>}
      </div>
    </aside>
  )
}

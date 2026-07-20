import { useState } from 'react'
import { won } from '../../lib/format'
import FlightDetailModal from './FlightDetailModal'

function isSameFlight(selected, candidate, date) {
  if (!selected) return false
  if (selected.air !== candidate.air || selected.dep !== candidate.dep || selected.price !== candidate.price) return false
  if (date !== undefined && selected.date !== date) return false
  return true
}

function FlightCard({ item, selected, locked, onSelect, onDetail }) {
  return (
    <div className={`flight-card${selected ? ' flight-card--selected' : ''}${locked && !selected ? ' flight-card--disabled' : ''}`}>
      <div className="flight-card__air">
        <span>{item.air}</span>
        <span>🛫</span>
      </div>
      <div className="flight-card__route">
        <div className="flight-card__time">
          <div>{item.dep}</div>
          <div>출발</div>
        </div>
        <div className="flight-card__dur">
          <span>{item.dur}</span>
          <span>──✈──</span>
          <span>{item.stops ? `${item.stops}경유` : '직항'}</span>
        </div>
        <div className="flight-card__time">
          <div>{item.arr}</div>
          <div>도착</div>
        </div>
      </div>
      <div className="flight-card__price-col">
        {item.tag && !selected && <span className="tag">{item.tag}</span>}
        <span className="flight-card__price">{won(item.price)}</span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <button type="button" className="card-detail-btn" onClick={onDetail}>상세</button>
          {selected ? (
            <span className="flight-card__selected-tag">✓ 선택됨</span>
          ) : (
            <button type="button" className="flight-card__select-btn" disabled={locked} onClick={onSelect}>
              {locked ? '예약 완료' : '예약'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default function FlightResults({ payload, selectedFlight, dispatch }) {
  const { mode, dates, flightsByDate, options } = payload
  const locked = Boolean(selectedFlight)
  const lowestKey = dates?.find((d) => d.low)?.key ?? dates?.[0]?.key
  const [selectedDate, setSelectedDate] = useState(selectedFlight?.date ?? lowestKey)
  const [detailFlight, setDetailFlight] = useState(null)
  const route = payload.route

  const selectFlight = (item, date, wd, isoDate) => {
    if (locked) return
    dispatch({ type: 'SELECT_FLIGHT', flight: { ...item, date, wd, isoDate } })
  }

  if (mode === 'byDate') {
    const activeDate = dates.find((d) => d.key === selectedDate) ?? dates[0]
    const flights = flightsByDate[activeDate.key] ?? []

    return (
      <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div className="card" style={{ padding: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 11 }}>
            <span style={{ fontSize: 12.5, fontWeight: 800 }}>📅 날짜별 최저가</span>
            <span style={{ fontSize: 11, color: 'var(--muted)' }}>편도 · 1인</span>
          </div>
          <div className="date-pills scroll-thin">
            {dates.map((d) => (
              <button
                key={d.key}
                type="button"
                className={`date-pill${d.key === activeDate.key ? ' date-pill--active' : ''}`}
                onClick={() => setSelectedDate(d.key)}
                disabled={locked && d.key !== selectedFlight?.date}
              >
                <span className="date-pill__wd">{d.wd}</span>
                <span className="date-pill__day">{d.key}</span>
                <span className="date-pill__price">{won(d.price)}</span>
                {d.low && <span className="tag">최저가</span>}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12.5, fontWeight: 800, color: 'var(--primary)' }}>
            {activeDate.key} ({activeDate.wd}요일)
          </span>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>항공편</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {flights.map((item) => (
            <FlightCard
              key={`${item.air}-${item.dep}`}
              item={item}
              selected={isSameFlight(selectedFlight, item, activeDate.key)}
              locked={locked}
              onSelect={() => selectFlight(item, activeDate.key, activeDate.wd, activeDate.isoDate)}
              onDetail={() => setDetailFlight(item)}
            />
          ))}
        </div>
        {detailFlight && <FlightDetailModal flight={detailFlight} route={route} onClose={() => setDetailFlight(null)} />}
      </div>
    )
  }

  // mode === 'simple' — 단일 목적지 리스트 (국제선 등 날짜 구분 없음)
  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
      {options.map((item) => (
        <FlightCard
          key={`${item.air}-${item.dep}`}
          item={item}
          selected={isSameFlight(selectedFlight, item)}
          locked={locked}
          onSelect={() => selectFlight(item)}
          onDetail={() => setDetailFlight(item)}
        />
      ))}
      {detailFlight && <FlightDetailModal flight={detailFlight} route={route} onClose={() => setDetailFlight(null)} />}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { won } from '../../lib/format'

// 왕복(가는 편+오는 편이 한 옵션) 항공 카드. 한 옵션을 고르면 왕복이 선택된다.
function isSameFlight(sel, f) {
  return (
    Boolean(sel) &&
    sel.air === f.air &&
    sel.outDep === f.outDep &&
    sel.inDep === f.inDep &&
    sel.price === f.price
  )
}

export default function FlightResults({ payload, selectedFlight, locked = false, dispatch }) {
  const { flights = [], route, depLabel, returnLabel, depDate } = payload
  // 이미 선택한 항공편이 있으면(예약 완료 재마운트) 그 항목이 보이도록 펼친 채로 시작
  const [showAll, setShowAll] = useState(Boolean(selectedFlight))
  useEffect(() => {
    if (selectedFlight) setShowAll(true)
  }, [selectedFlight])

  const INITIAL = 3
  const shown = showAll ? flights : flights.slice(0, INITIAL)

  const select = (f) => {
    if (locked) return
    dispatch({ type: 'SELECT_FLIGHT', flight: { ...f, route, isoDate: depDate } })
  }

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div className="card" style={{ padding: 14 }}>
        <div style={{ fontSize: 12.5, fontWeight: 800 }}>✈️ {route} · 왕복</div>
        <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 4 }}>
          가는 편 <b>{depLabel || '미정'}</b> · 오는 편 <b>{returnLabel || '미정'}</b> · 1인 왕복 요금
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {shown.map((f, i) => {
          const selected = isSameFlight(selectedFlight, f)
          return (
            <div
              key={`${f.air}-${f.outDep}-${i}`}
              className={`flight-card flight-card--rt${selected ? ' flight-card--selected' : ''}${locked && !selected ? ' flight-card--disabled' : ''}`}
            >
              <div className="flight-rt__head">
                <span className="flight-rt__air">{f.air}</span>
                {f.tag && !selected && <span className="tag">{f.tag}</span>}
              </div>
              <div className="flight-rt__legs">
                <div className="flight-rt__leg">
                  <span className="flight-rt__dir">가는 편</span>
                  <span className="flight-rt__time">{f.outDep} → {f.outArr}</span>
                </div>
                <div className="flight-rt__leg">
                  <span className="flight-rt__dir">오는 편</span>
                  <span className="flight-rt__time">{f.inDep || '-'} → {f.inArr || '-'}</span>
                </div>
              </div>
              <div className="flight-rt__foot">
                <span className="flight-card__price">{won(f.price)}</span>
                {selected ? (
                  <span className="flight-card__selected-tag">✓ 선택됨</span>
                ) : (
                  <button type="button" className="flight-card__select-btn" disabled={locked} onClick={() => select(f)}>
                    {locked ? '선택 불가' : '선택'}
                  </button>
                )}
              </div>
            </div>
          )
        })}
        {!locked && flights.length > INITIAL && (
          <button type="button" className="show-more-btn" onClick={() => setShowAll((v) => !v)}>
            {showAll ? '접기 ▴' : `항공편 ${flights.length - INITIAL}개 더보기 ▾`}
          </button>
        )}
      </div>
    </div>
  )
}

import { useEffect } from 'react'
import { won } from '../../lib/format'

// 항공 상세 모달 — 카드 데이터 기반(간단). 항공사·구간·소요·직항/경유·좌석·수하물·요금.
export default function FlightDetailModal({ flight, route, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose])

  const stops = Number(flight.stops) || 0
  const rows = [
    ['구간', route || flight.route || '항공편'],
    ['출발 → 도착', `${flight.dep} → ${flight.arr}`],
    ['소요 시간', `${flight.dur || '-'} · ${stops === 0 ? '직항' : `${stops}회 경유`}`],
    ['좌석 등급', '이코노미'],
    ['수하물', '위탁 1개(15~20kg) · 기내 1개(10kg)'],
  ]

  return (
    <div className="detail-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="detail-dialog" style={{ maxWidth: 420 }} role="dialog" aria-modal="true" aria-label={`${flight.air} 상세`}>
        <div className="detail-head">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span style={{ fontSize: 16, fontWeight: 800 }}>✈️ {flight.air}</span>
            <span style={{ fontSize: 12, color: 'var(--muted)' }}>{route || flight.route}</span>
          </div>
          <button type="button" className="detail-close" onClick={onClose} aria-label="닫기">✕</button>
        </div>

        <div className="detail-body" style={{ padding: 20 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {rows.map(([k, v]) => (
              <div key={k} style={{ display: 'flex', gap: 12, fontSize: 13.5 }}>
                <span style={{ color: 'var(--muted)', width: 84, flex: 'none' }}>{k}</span>
                <span style={{ fontWeight: 600 }}>{v}</span>
              </div>
            ))}
            <div style={{ borderTop: '1px solid var(--border)', marginTop: 4, paddingTop: 12, display: 'flex', alignItems: 'baseline', gap: 10 }}>
              <span style={{ color: 'var(--muted)', fontSize: 13.5, width: 84 }}>1인 요금</span>
              <span style={{ fontSize: 19, fontWeight: 800, color: 'var(--primary)' }}>{won(flight.price)}</span>
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--faint)', lineHeight: 1.5 }}>
              * 좌석·수하물 정책은 데모 기준이며 실제 항공사 규정이 우선합니다.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

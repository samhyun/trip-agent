import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { tripsApi } from '../lib/auth'
import { won } from '../lib/format'

// 내 예약 내역 — 로그인 유저의 저장된 여행(/me/trips). 디자인: Trip Agent.dc.html isBookings.

const BOOKING_ICON = { flight: '✈️', hotel: '🏨', activity: '🎟' }

function statusBadge(status) {
  if (status === 'booked') return { label: '예약완료', ink: 'oklch(0.42 0.15 150)', bg: 'oklch(0.72 0.16 150 / 0.14)' }
  if (status === 'completed') return { label: '완료', ink: 'var(--muted)', bg: 'var(--panel)' }
  return { label: '계획중', ink: 'var(--primary)', bg: 'var(--primary-soft)' }
}

export default function BookingsView({ onClose }) {
  const { token } = useAuth()
  const [trips, setTrips] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    tripsApi(token)
      .then((data) => alive && setTrips(Array.isArray(data) ? data : []))
      .catch(() => alive && setError('예약 내역을 불러오지 못했어요.'))
    return () => {
      alive = false
    }
  }, [token])

  return (
    <div className="tastream" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button type="button" onClick={onClose} aria-label="뒤로" style={{ width: 32, height: 32, borderRadius: 9, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', cursor: 'pointer', fontSize: 15 }}>←</button>
        <span style={{ fontSize: 16, fontWeight: 800 }}>내 예약 내역</span>
        {trips && <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--muted)' }}>총 {trips.length}건</span>}
      </div>

      {error && <div style={{ fontSize: 13, color: 'var(--muted)' }}>{error}</div>}
      {!trips && !error && <div style={{ fontSize: 13, color: 'var(--muted)' }}>불러오는 중…</div>}
      {trips && trips.length === 0 && (
        <div style={{ textAlign: 'center', color: 'var(--muted)', padding: '48px 0', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span style={{ fontSize: 30 }}>🧳</span>
          <span style={{ fontSize: 13.5 }}>아직 저장된 예약이 없어요.<br />여행을 계획하고 결제까지 진행해 보세요.</span>
        </div>
      )}

      {trips && trips.map((t) => {
        const badge = statusBadge(t.status)
        const bookings = Array.isArray(t.bookings) ? t.bookings : []
        return (
          <div key={t.id} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, boxShadow: 'var(--shadow-sm)', overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '13px 15px', borderBottom: '1px solid var(--border)' }}>
              <span style={{ fontSize: 18 }}>🧳</span>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontSize: 14, fontWeight: 800 }}>{t.title || '여행'}</span>
                <span style={{ fontSize: 11.5, color: 'var(--muted)' }}>
                  {(t.destinations || []).join(' · ') || '여행'} · {t.travelers}명
                </span>
              </div>
              <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 800, padding: '4px 10px', borderRadius: 999, color: badge.ink, background: badge.bg }}>{badge.label}</span>
            </div>

            {bookings.length > 0 && (
              <div style={{ padding: '10px 15px', display: 'flex', flexDirection: 'column', gap: 6, borderBottom: '1px solid var(--border)' }}>
                {bookings.map((b) => (
                  <div key={b.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--muted)' }}>
                    <span>{BOOKING_ICON[b.type] || '•'}</span>
                    <span style={{ color: 'var(--text)' }}>{b.title}</span>
                  </div>
                ))}
              </div>
            )}

            <div style={{ padding: '11px 15px', display: 'flex', alignItems: 'center', gap: 12 }}>
              {t.confirmation_no && (
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>확정번호 <b style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{t.confirmation_no}</b></span>
              )}
              <span style={{ marginLeft: 'auto', fontSize: 15, fontWeight: 800, color: 'var(--primary)', fontVariantNumeric: 'tabular-nums' }}>{won(t.total)}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

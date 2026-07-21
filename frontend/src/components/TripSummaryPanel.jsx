import { useAuth } from '../context/AuthContext'
import { won } from '../lib/format'

function statusInfo(stage, trip) {
  if (stage === 'welcome') return null
  if (stage.endsWith(':done')) return { label: '예약 확정', done: true }
  if (trip.hotels.length > 0 && trip.flight) return { label: '결제 대기', done: false }
  if (trip.flight) return { label: '항공 선택됨', done: false }
  return { label: '선택 대기', done: false }
}

// 게스트 CTA / 로그인 환영 (패널 상단)
function AuthPanelBlock({ user, onOpenAuth, onOpenBookings }) {
  if (!user) {
    return (
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: 16, boxShadow: 'var(--shadow-sm)', display: 'flex', flexDirection: 'column', gap: 11, textAlign: 'center' }}>
        <span style={{ fontSize: 26 }}>🧳</span>
        <span style={{ fontSize: 13.5, fontWeight: 800, lineHeight: 1.45 }}>로그인하면 예약과<br />여행이 저장돼요</span>
        <span style={{ fontSize: 11.5, color: 'var(--muted)', lineHeight: 1.5 }}>여러 기기에서 이어보고, 예약 내역을 한곳에서 관리하세요.</span>
        <button type="button" onClick={() => onOpenAuth('login')} style={{ marginTop: 3, width: '100%', background: 'var(--primary)', color: 'var(--primary-ink)', border: 'none', fontFamily: 'inherit', fontSize: 13.5, fontWeight: 800, padding: 11, borderRadius: 11, cursor: 'pointer' }}>로그인</button>
        <button type="button" onClick={() => onOpenAuth('signup')} style={{ width: '100%', background: 'none', color: 'var(--primary)', border: '1px solid var(--border)', fontFamily: 'inherit', fontSize: 13, fontWeight: 700, padding: 10, borderRadius: 11, cursor: 'pointer' }}>회원가입</button>
      </div>
    )
  }
  const name = (user.name || '').trim() || user.email || '사용자'
  const initials = (name.charAt(0) || '?').toUpperCase()
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
      <div style={{ background: 'linear-gradient(160deg, var(--primary-soft), var(--surface))', border: '1px solid var(--border)', borderRadius: 16, padding: 15, boxShadow: 'var(--shadow-sm)', display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ width: 42, height: 42, flex: 'none', borderRadius: '50%', background: 'var(--primary)', color: 'var(--primary-ink)', display: 'grid', placeItems: 'center', fontSize: 18, fontWeight: 800 }}>{initials}</span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ fontSize: 14, fontWeight: 800 }}>{name}님, 안녕하세요 👋</span>
          <span style={{ fontSize: 11.5, color: 'var(--muted)' }}>예약과 여행이 자동 저장돼요</span>
        </div>
      </div>
      <button type="button" onClick={onOpenBookings} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 13, padding: '13px 14px', fontFamily: 'inherit', cursor: 'pointer', color: 'var(--text)', boxShadow: 'var(--shadow-sm)' }}>
        <span style={{ fontSize: 17 }}>🧳</span>
        <span style={{ fontSize: 13.5, fontWeight: 700 }}>내 예약 내역</span>
        <span style={{ marginLeft: 'auto', color: 'var(--faint)' }}>›</span>
      </button>
    </div>
  )
}

export default function TripSummaryPanel({ trip, stage, onProceed, onOpenAuth, onOpenBookings }) {
  const { user } = useAuth()
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
        <AuthPanelBlock user={user} onOpenAuth={onOpenAuth} onOpenBookings={onOpenBookings} />

        {empty ? (
          user ? (
            <div className="trip-panel__empty">✈️
              <br />
              여행을 시작해 보세요
            </div>
          ) : null
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
              <span className="trip-panel__section-label">선택 항목</span>
              {trip.flight ? (
                <div className="trip-panel__item">
                  <span className="trip-panel__item-icon">✈️</span>
                  <div className="trip-panel__item-meta">
                    <strong>{trip.flight.route}</strong>
                    <span>
                      {trip.flight.air} · 왕복 {trip.flight.outDep}
                      {trip.flight.inDep ? ` / ${trip.flight.inDep}` : ''}
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
                <div key={`${hotel.cardKey || ""}-${hotel.id}`} className="trip-panel__item">
                  <span className="trip-panel__item-icon">🏨</span>
                  <div className="trip-panel__item-meta">
                    <strong>{hotel.name}</strong>
                    <span>{hotel.stay ? `${hotel.stay} · ` : ''}{hotel.nights}박 · {hotel.region}</span>
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
          {isDone ? '새 여행 시작' : trip.flight && trip.hotels.length > 0 ? '결제 진행 →' : '항공·숙소 보기 →'}
        </button>
        {!empty && !isDone && <div className="trip-panel__hint">👆 버튼 또는 💬 채팅 입력으로 진행</div>}
      </div>
    </aside>
  )
}

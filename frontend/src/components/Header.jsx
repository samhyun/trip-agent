import { useState } from 'react'
import { useAuth } from '../context/AuthContext'

// 헤더 — 게스트: "로그인" 버튼 / 로그인: 아바타 + 드롭다운(내 예약·로그아웃). 테마 토글 유지.

const loginBtnStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 7,
  background: 'var(--primary)',
  color: 'var(--primary-ink)',
  border: 'none',
  fontFamily: 'inherit',
  fontSize: 13,
  fontWeight: 700,
  padding: '9px 16px',
  borderRadius: 10,
  cursor: 'pointer',
  boxShadow: 'var(--shadow-sm)',
}

const avatar = (size, font) => ({
  width: size,
  height: size,
  flex: 'none',
  borderRadius: '50%',
  background: 'var(--primary)',
  color: 'var(--primary-ink)',
  display: 'grid',
  placeItems: 'center',
  fontSize: font,
  fontWeight: 800,
})

export default function Header({ theme, onToggleTheme, onOpenAuth, onOpenBookings }) {
  const { user, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const name = user ? (user.name || '').trim() || user.email || '사용자' : ''
  const initials = (name.charAt(0) || '?').toUpperCase()

  return (
    <header className="app-header">
      <div className="app-header__logo">✈️</div>
      <div className="app-header__title">
        <strong>Trip Agent</strong>
        <span>여행 플래닝 어시스턴트</span>
      </div>
      <span className="app-header__status">
        <span className="app-header__status-dot" /> 온라인
      </span>

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
        <button type="button" className="icon-btn" onClick={onToggleTheme} aria-label="테마 전환">
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>

        {!user ? (
          <button type="button" style={loginBtnStyle} onClick={() => onOpenAuth('login')}>
            로그인
          </button>
        ) : (
          <div style={{ position: 'relative' }}>
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 9, background: 'var(--bg)', border: '1px solid var(--border)', fontFamily: 'inherit', padding: '5px 12px 5px 6px', borderRadius: 999, cursor: 'pointer', color: 'var(--text)' }}
            >
              <span style={avatar(28, 13)}>{initials}</span>
              <span style={{ fontSize: 13, fontWeight: 700 }}>{name}</span>
              <span style={{ color: 'var(--faint)', fontSize: 11 }}>▾</span>
            </button>

            {menuOpen && (
              <>
                <div style={{ position: 'fixed', inset: 0, zIndex: 39 }} onClick={() => setMenuOpen(false)} />
                <div role="menu" style={{ position: 'absolute', top: 46, right: 0, width: 222, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, boxShadow: 'var(--shadow)', overflow: 'hidden', zIndex: 40, animation: 'ta-fadeup 0.18s ease both' }}>
                  <div style={{ padding: '13px 15px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={avatar(34, 15)}>{initials}</span>
                    <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                      <span style={{ fontSize: 13, fontWeight: 800 }}>{name}</span>
                      <span style={{ fontSize: 11, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user.email}</span>
                    </div>
                  </div>
                  <button type="button" className="auth-menu-item" role="menuitem" onClick={() => { setMenuOpen(false); onOpenBookings() }}>
                    🧳 <span>내 예약 내역</span>
                  </button>
                  <div style={{ height: 1, background: 'var(--border)' }} />
                  <button type="button" className="auth-menu-item" role="menuitem" onClick={() => { setMenuOpen(false); logout() }} style={{ color: 'oklch(0.55 0.16 25)', fontWeight: 600 }}>
                    ↩ <span>로그아웃</span>
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </header>
  )
}

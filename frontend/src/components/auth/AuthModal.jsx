import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../../context/AuthContext'

// 중앙 인증 모달 (로그인/회원가입 탭 · 에러/로딩/성공). 디자인: Trip Agent.dc.html 3a.

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const RED = 'oklch(0.55 0.17 25)'

const tabStyle = (active) => ({
  flex: 1,
  padding: '12px 0',
  background: 'none',
  border: 'none',
  borderBottom: `2px solid ${active ? 'var(--primary)' : 'transparent'}`,
  color: active ? 'var(--primary)' : 'var(--muted)',
  fontFamily: 'inherit',
  fontSize: 14,
  fontWeight: active ? 800 : 700,
  cursor: 'pointer',
})

const submitStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 8,
  width: '100%',
  background: 'var(--primary)',
  color: 'var(--primary-ink)',
  border: 'none',
  fontFamily: 'inherit',
  fontSize: 14,
  fontWeight: 800,
  padding: 12,
  borderRadius: 11,
  cursor: 'pointer',
}

const labelStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  fontSize: 12.5,
  fontWeight: 700,
  color: 'var(--text)',
}

const fieldErr = { fontSize: 11.5, fontWeight: 500, color: RED }

export default function AuthModal({ open, initialTab = 'login', onClose }) {
  const { login, register } = useAuth()
  const [tab, setTab] = useState(initialTab)
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  // 로그인 필드
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPw, setLoginPw] = useState('')
  const [loginError, setLoginError] = useState('')

  // 회원가입 필드
  const [su, setSu] = useState({ name: '', email: '', pw: '', pw2: '' })
  const [suErr, setSuErr] = useState({})

  const closeTimer = useRef(null)

  useEffect(() => {
    if (open) {
      clearTimeout(closeTimer.current) // 재오픈 시 이전 성공 타이머가 새 모달을 닫지 않게
      setTab(initialTab)
      setLoading(false)
      setSuccess(false)
      setLoginEmail('')
      setLoginPw('')
      setLoginError('')
      setSu({ name: '', email: '', pw: '', pw2: '' })
      setSuErr({})
    }
  }, [open, initialTab])

  // 로딩(요청 진행) 중에는 닫기를 막아, 취소한 줄 알았는데 로그인되는 상황 방지
  const requestClose = () => {
    if (!loading) onClose()
  }

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === 'Escape' && !loading) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose, loading])

  useEffect(() => () => clearTimeout(closeTimer.current), [])

  if (!open) return null

  const finishSuccess = () => {
    setSuccess(true)
    closeTimer.current = setTimeout(onClose, 900)
  }

  const doLogin = async (e) => {
    e.preventDefault()
    if (loading) return
    setLoginError('')
    setLoading(true)
    try {
      await login(loginEmail.trim(), loginPw)
      finishSuccess()
    } catch (err) {
      setLoginError(err.message || '로그인에 실패했어요.')
      setLoading(false)
    }
  }

  const validateSignup = () => {
    const e = {}
    if (!su.name.trim()) e.name = '이름을 입력해 주세요.'
    if (!EMAIL_RE.test(su.email.trim())) e.email = '올바른 이메일을 입력해 주세요.'
    if (su.pw.length < 6) e.pw = '비밀번호는 6자 이상이어야 해요.'
    if (su.pw2 !== su.pw) e.pw2 = '비밀번호가 일치하지 않아요.'
    return e
  }

  const doSignup = async (e) => {
    e.preventDefault()
    if (loading) return
    const errs = validateSignup()
    setSuErr(errs)
    if (Object.keys(errs).length) return
    setLoading(true)
    try {
      await register(su.name.trim(), su.email.trim(), su.pw)
      finishSuccess()
    } catch (err) {
      // 409(이메일 중복)는 이메일 필드로, 그 외는 공통 에러
      if (err.status === 409) setSuErr({ email: err.message })
      else setSuErr({ email: err.message || '회원가입에 실패했어요.' })
      setLoading(false)
    }
  }

  const onOverlay = (e) => {
    if (e.target === e.currentTarget) requestClose()
  }

  // 링크처럼 보이는 버튼 (키보드 접근성)
  const linkBtn = { background: 'none', border: 'none', padding: 0, font: 'inherit', color: 'var(--primary)', fontWeight: 700, cursor: 'pointer' }

  return (
    <div className="auth-overlay" onClick={onOverlay}>
      <div className="auth-dialog" role="dialog" aria-modal="true" aria-label="로그인 또는 회원가입">
        {success ? (
          <div style={{ padding: '44px 30px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, textAlign: 'center' }}>
            <span style={{ width: 60, height: 60, borderRadius: '50%', background: 'oklch(0.72 0.16 150 / 0.16)', color: 'oklch(0.55 0.15 150)', display: 'grid', placeItems: 'center', fontSize: 30 }}>✓</span>
            <span style={{ fontSize: 17, fontWeight: 800 }}>환영합니다!</span>
            <span style={{ fontSize: 13, color: 'var(--muted)' }}>잠시 후 이동할게요…</span>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '18px 20px 0' }}>
              <div style={{ width: 30, height: 30, borderRadius: 9, background: 'var(--primary)', color: 'var(--primary-ink)', display: 'grid', placeItems: 'center', fontSize: 16 }}>✈️</div>
              <span style={{ fontSize: 15, fontWeight: 800 }}>Trip Agent</span>
              <button type="button" onClick={requestClose} aria-label="닫기" style={{ marginLeft: 'auto', width: 30, height: 30, borderRadius: 8, border: 'none', background: 'var(--bg)', color: 'var(--muted)', cursor: 'pointer', fontSize: 15 }}>✕</button>
            </div>

            <div role="tablist" style={{ display: 'flex', margin: '14px 20px 0', borderBottom: '1px solid var(--border)' }}>
              <button type="button" role="tab" aria-selected={tab === 'login'} style={tabStyle(tab === 'login')} onClick={() => setTab('login')}>로그인</button>
              <button type="button" role="tab" aria-selected={tab === 'signup'} style={tabStyle(tab === 'signup')} onClick={() => setTab('signup')}>회원가입</button>
            </div>

            {tab === 'login' ? (
              <form onSubmit={doLogin} style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
                <label style={labelStyle}>이메일
                  <input className="auth-input" type="email" autoComplete="email" placeholder="you@example.com" value={loginEmail} onChange={(e) => setLoginEmail(e.target.value)} />
                </label>
                <label style={labelStyle}>비밀번호
                  <input className="auth-input" type="password" autoComplete="current-password" placeholder="비밀번호" value={loginPw} onChange={(e) => setLoginPw(e.target.value)} />
                </label>
                {loginError && (
                  <div role="alert" style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: RED, background: 'oklch(0.55 0.17 25 / 0.09)', border: '1px solid oklch(0.55 0.17 25 / 0.22)', padding: '9px 11px', borderRadius: 10 }}>⚠ {loginError}</div>
                )}
                <button type="submit" disabled={loading} style={{ ...submitStyle, opacity: loading ? 0.7 : 1 }}>
                  {loading && <span className="auth-spinner" />}
                  로그인
                </button>
                <div style={{ textAlign: 'center', fontSize: 12.5, color: 'var(--muted)' }}>
                  계정이 없으신가요? <button type="button" onClick={() => setTab('signup')} style={linkBtn}>회원가입</button>
                </div>
              </form>
            ) : (
              <form onSubmit={doSignup} style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 13 }}>
                <label style={labelStyle}>이름
                  <input className="auth-input" autoComplete="name" placeholder="홍길동" value={su.name} onChange={(e) => setSu({ ...su, name: e.target.value })} />
                  {suErr.name && <span style={fieldErr}>{suErr.name}</span>}
                </label>
                <label style={labelStyle}>이메일
                  <input className="auth-input" type="email" autoComplete="email" placeholder="you@example.com" value={su.email} onChange={(e) => setSu({ ...su, email: e.target.value })} />
                  {suErr.email && <span style={fieldErr}>{suErr.email}</span>}
                </label>
                <label style={labelStyle}>비밀번호
                  <input className="auth-input" type="password" autoComplete="new-password" placeholder="6자 이상" value={su.pw} onChange={(e) => setSu({ ...su, pw: e.target.value })} />
                  {suErr.pw && <span style={fieldErr}>{suErr.pw}</span>}
                </label>
                <label style={labelStyle}>비밀번호 확인
                  <input className="auth-input" type="password" autoComplete="new-password" placeholder="비밀번호 재입력" value={su.pw2} onChange={(e) => setSu({ ...su, pw2: e.target.value })} />
                  {suErr.pw2 && <span style={fieldErr}>{suErr.pw2}</span>}
                </label>
                <button type="submit" disabled={loading} style={{ ...submitStyle, opacity: loading ? 0.7 : 1 }}>
                  {loading && <span className="auth-spinner" />}
                  회원가입
                </button>
                <div style={{ textAlign: 'center', fontSize: 12.5, color: 'var(--muted)' }}>
                  이미 계정이 있으신가요? <button type="button" onClick={() => setTab('login')} style={linkBtn}>로그인</button>
                </div>
              </form>
            )}

            <div style={{ padding: '0 20px 18px', textAlign: 'center' }}>
              <button type="button" onClick={requestClose} style={{ ...linkBtn, color: 'var(--faint)', fontWeight: 400, fontSize: 12 }}>로그인 없이 계속 →</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

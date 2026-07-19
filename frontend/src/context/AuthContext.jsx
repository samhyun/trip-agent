import { createContext, useContext, useEffect, useState } from 'react'
import { TOKEN_KEY, loginApi, meApi, registerApi } from '../lib/auth'

// 인증 상태(토큰·유저)를 앱 전역에 제공. 토큰은 localStorage에 유지하고,
// 앱 로드 시 /auth/me 로 로그인 상태를 복원한다.

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!token) {
      setReady(true)
      return undefined
    }
    const validated = token // 검증 대상 토큰 스냅샷
    let alive = true
    meApi(validated)
      .then((u) => alive && setUser(u))
      .catch(() => {
        // 늦게 도착한 실패가 그 사이 새로 로그인한 토큰을 지우지 않도록, 여전히 같은 토큰일 때만 정리
        if (alive && localStorage.getItem(TOKEN_KEY) === validated) {
          localStorage.removeItem(TOKEN_KEY)
          setToken(null)
        }
      })
      .finally(() => alive && setReady(true))
    return () => {
      alive = false
    }
    // 최초 마운트 시 1회만 복원
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const persist = (data) => {
    localStorage.setItem(TOKEN_KEY, data.access_token)
    setToken(data.access_token)
    setUser(data.user)
  }

  const login = async (email, password) => persist(await loginApi({ email, password }))
  const register = async (name, email, password) => persist(await registerApi({ name, email, password }))
  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, ready, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

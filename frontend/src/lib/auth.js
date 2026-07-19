// 인증/유저 API 클라이언트 (백엔드 /auth·/me).
// 토큰은 localStorage에 저장하고, /chat 을 포함한 요청에 Bearer로 싣는다.

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
export const TOKEN_KEY = 'trip-agent-token'

async function request(path, { method = 'GET', body, token } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = new Error(data.detail || `요청 실패 (${res.status})`)
    err.status = res.status
    throw err
  }
  return data
}

export const registerApi = ({ name, email, password }) =>
  request('/auth/register', { method: 'POST', body: { name, email, password } })

export const loginApi = ({ email, password }) =>
  request('/auth/login', { method: 'POST', body: { email, password } })

export const meApi = (token) => request('/auth/me', { token })

export const tripsApi = (token) => request('/me/trips', { token })

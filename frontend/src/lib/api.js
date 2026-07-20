// 백엔드 /chat API 클라이언트.
// VITE_API_BASE_URL 이 없으면 로컬 개발 백엔드(localhost:8000)로 붙는다.

import { TOKEN_KEY } from './auth'

export const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

/**
 * 사용자 메시지를 백엔드 에이전트에 전달하고 구조화 응답을 받는다.
 * @param {{ message: string, conversationId?: string|null }} params
 * @returns {Promise<{answer: string, conversation_id: string, agent: string|null, turns: Array}>}
 */
export async function sendChat({ message, conversationId }) {
  const headers = { 'Content-Type': 'application/json' }
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) headers.Authorization = `Bearer ${token}` // 로그인 시 대화가 계정에 연결됨
  const res = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, conversation_id: conversationId ?? null }),
  })
  if (!res.ok) {
    throw new Error(`chat 요청 실패: ${res.status}`)
  }
  return res.json()
}

/** 호텔 상세 조회 (ID 기반). 사진·편의시설·주소·체크인아웃·설명. */
export async function fetchHotelDetail(id, city, signal) {
  const res = await fetch(
    `${BASE_URL}/details/hotel?id=${encodeURIComponent(id)}&city=${encodeURIComponent(city)}`,
    { signal },
  )
  if (!res.ok) throw new Error(`상세 조회 실패: ${res.status}`)
  return res.json()
}

/**
 * 스트리밍 채팅 (SSE). 텍스트는 토큰 단위, 카드는 완성 이벤트로 onEvent 에 전달된다.
 * @param {{ message: string, conversationId?: string|null, onEvent: (ev:object)=>void, signal?: AbortSignal }} params
 */
export async function streamChat({ message, conversationId, onEvent, signal }) {
  const headers = { 'Content-Type': 'application/json' }
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${BASE_URL}/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, conversation_id: conversationId ?? null }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`chat 스트림 실패: ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() ?? '' // 마지막 미완성 조각 보관
      for (const chunk of chunks) {
        const line = chunk.trim()
        if (!line.startsWith('data:')) continue
        try {
          onEvent(JSON.parse(line.slice(5).trim()))
        } catch {
          // 파싱 실패한 조각은 무시
        }
      }
    }
  } finally {
    try {
      reader.releaseLock()
    } catch {
      // 이미 해제됨
    }
  }
}

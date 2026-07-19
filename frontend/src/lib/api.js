// 백엔드 /chat API 클라이언트.
// VITE_API_BASE_URL 이 없으면 로컬 개발 백엔드(localhost:8000)로 붙는다.

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

/**
 * 사용자 메시지를 백엔드 에이전트에 전달하고 구조화 응답을 받는다.
 * @param {{ message: string, conversationId?: string|null }} params
 * @returns {Promise<{answer: string, conversation_id: string, agent: string|null, turns: Array}>}
 */
export async function sendChat({ message, conversationId }) {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId ?? null }),
  })
  if (!res.ok) {
    throw new Error(`chat 요청 실패: ${res.status}`)
  }
  return res.json()
}

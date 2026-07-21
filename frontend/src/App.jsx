import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import Header from './components/Header'
import ChatColumn from './components/ChatColumn'
import TripSummaryPanel from './components/TripSummaryPanel'
import MobileSummaryBar from './components/MobileSummaryBar'
import AuthModal from './components/auth/AuthModal'
import BookingsView from './components/BookingsView'
import {
  conversationReducer,
  createInitialState,
  findCarouselItem,
  findQuickReplyOption,
} from './lib/conversationReducer'
import { streamChat } from './lib/api'

function useTheme() {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('trip-agent-theme')
    if (saved) return saved
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })

  useEffect(() => {
    localStorage.setItem('trip-agent-theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  return [theme, toggleTheme]
}

// 실 API 대화 훅: 순수 reducer 위에 비동기 /chat 호출을 얹은 스마트 dispatch를 제공한다.
// 카드 액션(담기/선택/예약/결제)은 로컬 선택 상태를 즉시 갱신하고, 해당 의미의
// 한국어 텍스트를 /chat 으로 전송해 응답 turns 를 메시지로 렌더한다.
function useConversation() {
  const [state, raw] = useReducer(conversationReducer, undefined, createInitialState)
  const stateRef = useRef(state)
  stateRef.current = state
  const convId = useRef(null)
  const busy = useRef(false)
  const abortRef = useRef(null)

  const send = useCallback(async (text) => {
    const trimmed = (text || '').trim()
    if (!trimmed || busy.current) return
    busy.current = true
    raw({ type: 'USER_MESSAGE', text: trimmed })
    // 카드에서 고른 항공·숙소는 로컬 상태라 백엔드가 모른다 → 매 발화에 선택 상태를 붙여 전달.
    // ("이걸로 예약하고싶어" 같은 지칭을 에이전트가 이해하고 다음 단계로 넘어가게.) 화면엔 원문만 표시.
    // NOTE(데모 스코프): 별도 API 필드 대신 메시지 접두를 사용 — 위조해도 자기 대화 라우팅에만 영향.
    const t = stateRef.current.trip
    const ctx = []
    if (t.flight) ctx.push(`항공 ${t.flight.air} ${t.flight.outDep} 출발(왕복 ${t.flight.price?.toLocaleString?.() || t.flight.price}원) 선택됨`)
    if (t.hotels.length > 0) ctx.push(`숙소 ${t.hotels.map((h) => `${h.name} ${h.nights ?? ''}박`.trim()).join(', ')} 선택됨`)
    const message = ctx.length ? `[화면 선택 상태: ${ctx.join(' / ')}]\n${trimmed}` : trimmed
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await streamChat({
        message,
        conversationId: convId.current,
        signal: controller.signal,
        onEvent: (ev) => {
          switch (ev.type) {
            case 'meta':
              convId.current = ev.conversation_id || convId.current
              break
            case 'text_start':
              raw({ type: 'STREAM_TEXT_START', cardType: ev.card_type })
              break
            case 'text_delta':
              raw({ type: 'STREAM_TEXT_DELTA', text: ev.text })
              break
            case 'text_end':
              raw({ type: 'STREAM_TEXT_END', payload: ev.payload, content: ev.content })
              break
            case 'card':
              raw({ type: 'STREAM_CARD', turn: { type: ev.card_type, content: ev.content, payload: ev.payload } })
              break
            case 'text':
              raw({ type: 'STREAM_TEXT', turn: { type: 'text', content: ev.content, payload: null } })
              break
            case 'done':
              raw({ type: 'STREAM_DONE' })
              break
            case 'error':
              raw({ type: 'AGENT_ERROR' })
              break
            default:
              break
          }
        },
      })
    } catch (err) {
      if (err?.name !== 'AbortError') raw({ type: 'AGENT_ERROR' }) // 의도적 취소는 에러 아님
    } finally {
      busy.current = false
      abortRef.current = null
    }
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort() // 진행 중 스트림 취소
    convId.current = null
    raw({ type: 'RESET' })
  }, [])

  const dispatch = useCallback(
    (action) => {
      const s = stateRef.current
      // 요청 처리 중에는 결제 금액에 영향 없는 로컬 미리보기(동선·명소 담기)만 허용.
      // 항공·숙소 선택은 잠근다 — 결제 요청 중 변경 시 저장액과 화면이 어긋나는 레이스 방지.
      const LOCAL_PREVIEW = ['SELECT_ROUTE_PREVIEW', 'TOGGLE_SPOT']
      if (busy.current && !LOCAL_PREVIEW.includes(action.type)) {
        return undefined
      }
      switch (action.type) {
        case 'SEND_TEXT':
          return send(action.text)

        case 'QUICK_REPLY': {
          const opt = findQuickReplyOption(s.messages, action.msgId, action.optionId)
          raw({ type: 'DISABLE_QUICK_REPLY', msgId: action.msgId, optionId: action.optionId })
          if (action.optionId === 'restart') return reset()
          return send(opt?.send || opt?.label || '')
        }

        case 'TOGGLE_SPOT': {
          // 담기/빼기는 로컬 상태만 토글한다(에이전트 호출 없음) → 여러 명소를 자유롭게 담을 수 있다.
          const item = findCarouselItem(s.messages, action.spotId)
          if (!item) return undefined
          return raw({ type: 'TOGGLE_SPOT', spot: item })
        }

        // 항공·숙소 선택은 로컬 상태만 바꾼다(에이전트 호출 없음) → 결제 전까지 자유롭게 바꾸고 이어서 선택
        case 'SELECT_FLIGHT':
          return raw(action)

        case 'SELECT_HOTEL':
          return raw(action)

        case 'SELECT_ROUTE_PREVIEW':
          return raw(action)

        case 'PAY':
          return send('결제까지 진행할게요')

        case 'PANEL_PROCEED': {
          if (s.stage === 'api:done') return reset()
          // 항공·숙소를 골랐으면 결제로 진행 — 로컬 선택 내역을 파싱 가능한 형식으로 함께 보내 저장되게 한다
          if (s.trip.flight && s.trip.hotels.length > 0) {
            const f = s.trip.flight
            const lines = [
              `${f.air} ${f.outDep} 항공편으로 예약할게요`,
              ...s.trip.hotels.map((h) => `${h.name} 숙소로 예약할게요`),
              `총 ${s.trip.total}원, 결제까지 진행할게요`,
            ]
            return send(lines.join('\n'))
          }
          if (s.trip.destination) return send('항공·숙소 예약 진행해줘')
          return undefined
        }

        default:
          return raw(action)
      }
    },
    [send, reset],
  )

  return [state, dispatch]
}

export default function App() {
  const [state, dispatch] = useConversation()
  const [theme, toggleTheme] = useTheme()
  const [mobileSummaryOpen, setMobileSummaryOpen] = useState(false)
  const [auth, setAuth] = useState({ open: false, tab: 'login' })
  const [bookingsOpen, setBookingsOpen] = useState(false)
  const openAuth = (tab = 'login') => setAuth({ open: true, tab })

  return (
    <div className="app-shell" data-theme={theme}>
      <Header
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenAuth={openAuth}
        onOpenBookings={() => setBookingsOpen(true)}
      />
      <MobileSummaryBar
        trip={state.trip}
        stage={state.stage}
        open={mobileSummaryOpen}
        onToggle={() => setMobileSummaryOpen((v) => !v)}
        onProceed={() => dispatch({ type: 'PANEL_PROCEED' })}
      />
      <div className="app-main">
        {bookingsOpen ? (
          <div className="chat-column">
            <BookingsView onClose={() => setBookingsOpen(false)} />
          </div>
        ) : (
          <ChatColumn state={state} dispatch={dispatch} />
        )}
        <TripSummaryPanel
          trip={state.trip}
          stage={state.stage}
          onProceed={() => dispatch({ type: 'PANEL_PROCEED' })}
          onOpenAuth={openAuth}
          onOpenBookings={() => setBookingsOpen(true)}
        />
      </div>
      <AuthModal open={auth.open} initialTab={auth.tab} onClose={() => setAuth((a) => ({ ...a, open: false }))} />
    </div>
  )
}

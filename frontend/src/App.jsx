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
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await streamChat({
        message: trimmed,
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
              raw({ type: 'STREAM_TEXT_END', payload: ev.payload })
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
      // 요청 처리 중에는 순수 로컬 미리보기 외 모든 카드 액션을 잠근다 (상태-대화 불일치 방지)
      if (busy.current && action.type !== 'SELECT_ROUTE_PREVIEW') return undefined
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
          const item = findCarouselItem(s.messages, action.spotId)
          if (!item) return undefined
          const adding = !s.trip.spots.some((sp) => sp.id === item.id)
          raw({ type: 'TOGGLE_SPOT', spot: item })
          return send(adding ? `${item.name} 담아줘` : `${item.name} 뺄게`)
        }

        case 'SELECT_FLIGHT':
          raw(action)
          return send(`${action.flight.air} ${action.flight.dep} 항공편으로 예약할게요`)

        case 'SELECT_HOTEL':
          raw(action)
          return send(`${action.hotel.name} 숙소로 예약할게요`)

        case 'SELECT_ROUTE_PREVIEW':
          return raw(action)

        case 'PAY':
          return send('결제까지 진행할게요')

        case 'PANEL_PROCEED': {
          if (s.stage === 'api:done') return reset()
          if (s.trip.flight && s.trip.hotels.length > 0) return send('결제까지 진행할게요')
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

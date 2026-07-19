import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import Header from './components/Header'
import ChatColumn from './components/ChatColumn'
import TripSummaryPanel from './components/TripSummaryPanel'
import MobileSummaryBar from './components/MobileSummaryBar'
import {
  conversationReducer,
  createInitialState,
  findCarouselItem,
  findQuickReplyOption,
} from './lib/conversationReducer'
import { sendChat } from './lib/api'

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

  const send = useCallback(async (text) => {
    const trimmed = (text || '').trim()
    if (!trimmed || busy.current) return
    busy.current = true
    raw({ type: 'USER_MESSAGE', text: trimmed })
    try {
      const data = await sendChat({ message: trimmed, conversationId: convId.current })
      convId.current = data.conversation_id || convId.current
      // turns가 비어 있으면 answer 를 텍스트 메시지로 폴백 렌더 (되묻기 등이 사라지지 않도록)
      const turns =
        data.turns && data.turns.length
          ? data.turns
          : data.answer
            ? [{ agent: null, content: data.answer, type: 'text', payload: null }]
            : []
      raw({ type: 'AGENT_REPLY', turns })
    } catch (err) {
      raw({ type: 'AGENT_ERROR' })
    } finally {
      busy.current = false
    }
  }, [])

  const reset = useCallback(() => {
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

  return (
    <div className="app-shell" data-theme={theme}>
      <Header theme={theme} onToggleTheme={toggleTheme} />
      <MobileSummaryBar
        trip={state.trip}
        stage={state.stage}
        open={mobileSummaryOpen}
        onToggle={() => setMobileSummaryOpen((v) => !v)}
        onProceed={() => dispatch({ type: 'PANEL_PROCEED' })}
      />
      <div className="app-main">
        <ChatColumn state={state} dispatch={dispatch} />
        <TripSummaryPanel trip={state.trip} stage={state.stage} onProceed={() => dispatch({ type: 'PANEL_PROCEED' })} />
      </div>
    </div>
  )
}

// 대화 상태 머신 (실 API 모드).
// reducer는 순수 함수. 비동기 /chat 호출은 App.jsx 의 useConversation 훅이 맡고,
// 이 reducer 는 그 결과(turns)를 메시지로 반영하고 카드 액션의 로컬 선택 상태
// (우측 "내 여행" 패널용 trip)를 관리한다.
//
// 백엔드 turns 계약: [{ agent, content, type, payload }]
//   type: text | destination_carousel | itinerary | flight_results | hotel_results | confirmation
// 각 카드 payload 는 프론트 컴포넌트 계약에 맞춰 백엔드에서 정형화되어 온다.
//
// 참고: 스크립트 mock 시나리오(scenarios/jeju.js, bohol.js)는 데모/레퍼런스로
// 파일만 남겨두고, 런타임 기본 동작은 실 API 다.

import { nextId } from './id'
import { dateRangeLabel } from './format'

// ---------- 메시지/상태 헬퍼 ----------

function bot(type, payload) {
  return { id: nextId('a'), role: 'assistant', type, payload }
}

function userText(text) {
  return { id: nextId('u'), role: 'user', type: 'text', payload: { text } }
}

function append(state, messages) {
  return { ...state, messages: [...state.messages, ...messages] }
}

function appendUserBubble(state, text) {
  return append(state, [userText(text)])
}

function patchTrip(state, patch) {
  return { ...state, trip: { ...state.trip, ...patch } }
}

function status(agent, text) {
  return bot('agent_status', { agent, text })
}

function dropTrailingStatus(state) {
  const last = state.messages[state.messages.length - 1]
  if (last && last.type === 'agent_status') {
    return { ...state, messages: state.messages.slice(0, -1) }
  }
  return state
}

function disableQuickReply(state, msgId, optionId) {
  return {
    ...state,
    messages: state.messages.map((m) =>
      m.id === msgId ? { ...m, payload: { ...m.payload, disabled: true, selectedId: optionId } } : m,
    ),
  }
}

// 선택된 항공/숙소로 실시간 합계 계산 (우측 패널 즉시 갱신용)
function computeTotal(trip) {
  const flightTotal = trip.flight ? trip.flight.price * (trip.travelers || 1) : 0
  const hotelsTotal = trip.hotels.reduce((sum, h) => sum + h.price * (h.nights || 1), 0)
  return flightTotal + hotelsTotal
}

// 사용자 발화에서 인원/박수 추출 (패널 표기·합계용)
function parsePeople(text) {
  const m = text.match(/(\d+)\s*(명|인|사람)/)
  if (m) return Number(m[1])
  if (/혼자/.test(text)) return 1
  if (/둘이|두\s*명|두명/.test(text)) return 2
  return null
}

function parseNights(text) {
  const m = text.match(/(\d+)\s*박/)
  return m ? Number(m[1]) : null
}

// ---------- 탐색 헬퍼 (App 의 스마트 dispatch 가 사용) ----------

export function findCarouselItem(messages, spotId) {
  for (const m of messages) {
    if (m.type === 'destination_carousel') {
      const item = (m.payload.items || []).find((it) => it.id === spotId)
      if (item) return item
    }
  }
  return null
}

export function findQuickReplyOption(messages, msgId, optionId) {
  const msg = messages.find((m) => m.id === msgId)
  if (!msg) return null
  return (msg.payload.options || []).find((o) => o.id === optionId) || null
}

// ---------- 초기 상태 ----------

export function createInitialState() {
  return {
    stage: 'welcome', // welcome → active → api:done
    loading: false,
    streamingId: null, // 현재 토큰 스트리밍 중인 메시지 id
    messages: [
      bot('text', {
        text: '안녕하세요! 어디로 떠나고 싶으세요? 목적지와 일정을 알려주시면 명소부터 항공·숙소·예약까지 여기서 바로 도와드려요. ✈️',
      }),
      bot('quick_replies', {
        options: [
          { id: 'start_jeju', label: '🏝 제주 3박4일', send: '제주 3박4일 2명 여행 계획 짜줘. 항공·숙소 예약까지 도와줘' },
          { id: 'start_bohol', label: '🏖 보홀 여행', send: '보홀 3박4일 2명 여행 계획 짜줘. 명소랑 항공·숙소 예약까지 도와줘' },
          { id: 'start_busan', label: '🌊 부산 2박3일', send: '부산 2박3일 2명 여행 계획 짜줘. 항공·숙소 예약까지 도와줘' },
        ],
      }),
    ],
    trip: {
      destination: null,
      dateLabel: null,
      travelers: 1,
      nights: null,
      spots: [],
      flight: null,
      hotels: [],
      routePlan: null,
      total: 0,
      confirmation: null,
    },
  }
}

// ---------- 사용자 발화 → 로딩 ----------

function handleUserMessage(state, text) {
  let s = appendUserBubble(state, text)
  const people = parsePeople(text)
  const nights = parseNights(text)
  const patch = {}
  if (people != null) patch.travelers = people
  if (nights != null) patch.nights = nights
  if (Object.keys(patch).length) s = patchTrip(s, patch)
  s = append(s, [status('Trip Agent', '생각하는 중…')])
  return { ...s, loading: true, stage: s.stage === 'welcome' ? 'active' : s.stage }
}

// ---------- 백엔드 turns → 메시지 + 패널 반영 ----------

// 카드가 스스로 본문 텍스트를 렌더하는 타입 (별도 텍스트 버블 생략)
const CARD_SELF_TEXT = new Set(['itinerary'])

// 결제 확정 시, 이번 턴(마지막 사용자 발화 이후)에 재방출된 재플랜 결과를 통째로 걷어내는 기준.
function lastUserIndex(messages) {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'user') return i
  }
  return -1
}

// 턴(카드/텍스트) 하나를 상태에 반영 (비스트리밍·스트리밍 카드 공용)
function applyTurn(state, turn) {
  const type = turn.type || 'text'
  const content = (turn.content || '').trim()
  const trip = { ...state.trip }

  if (type === 'text' || !turn.payload) {
    return content ? append({ ...state, trip }, [bot('text', { text: content })]) : { ...state, trip }
  }

  const msgs = []
  if (!CARD_SELF_TEXT.has(type) && content && type !== 'confirmation') {
    msgs.push(bot('text', { text: content }))
  }

  if (type === 'destination_carousel') {
    if (!trip.destination && turn.payload.city) trip.destination = turn.payload.city
    msgs.push(bot('destination_carousel', turn.payload))
  } else if (type === 'itinerary') {
    msgs.push(bot('itinerary', { ...turn.payload, markdown: turn.payload.markdown || content }))
  } else if (type === 'hotel_results') {
    if (!trip.destination && turn.payload.cityLabel) trip.destination = turn.payload.cityLabel
    msgs.push(bot('hotel_results', turn.payload))
  } else if (type === 'confirmation') {
    const total = trip.total || turn.payload.total || 0
    const dateLabel = trip.dateLabel || turn.payload.dateLabel || ''
    trip.confirmation = { code: turn.payload.code, total }
    trip.total = total
    // 이번 턴에 재방출된 재플랜 카드·캡션(고아 텍스트 포함)을 통째로 제거하고 확정서만 남긴다
    const kept = state.messages.slice(0, lastUserIndex(state.messages) + 1)
    return {
      ...state,
      messages: [...kept, bot('confirmation', { ...turn.payload, total, dateLabel })],
      trip,
      stage: 'api:done',
    }
  } else {
    msgs.push(bot(type, turn.payload))
  }
  return append({ ...state, trip }, msgs)
}

// 비스트리밍 응답(폴백): turns 전체를 순서대로 반영
function handleAgentReply(state, turns) {
  let s = { ...dropTrailingStatus(state), loading: false }
  for (const t of turns) s = applyTurn(s, t)
  return s
}

// ---------- 스트리밍 (SSE) ----------

function handleStreamTextStart(state, cardType) {
  const s = dropTrailingStatus(state)
  const isItin = cardType === 'itinerary'
  const msg = bot(isItin ? 'itinerary' : 'text', isItin ? { markdown: '' } : { text: '' })
  return { ...s, messages: [...s.messages, msg], streamingId: msg.id, loading: true }
}

function handleStreamDelta(state, text) {
  if (!state.streamingId) return state
  return {
    ...state,
    messages: state.messages.map((m) => {
      if (m.id !== state.streamingId) return m
      const key = m.type === 'itinerary' ? 'markdown' : 'text'
      return { ...m, payload: { ...m.payload, [key]: (m.payload[key] || '') + text } }
    }),
  }
}

function handleStreamTextEnd(state, payload) {
  if (!state.streamingId) return state
  const messages = payload
    ? state.messages.map((m) => (m.id === state.streamingId ? { ...m, payload: { ...m.payload, ...payload } } : m))
    : state.messages
  return { ...state, messages, streamingId: null }
}

function handleAgentError(state) {
  const s = { ...dropTrailingStatus(state), loading: false, streamingId: null }
  return append(s, [
    bot('text', {
      text: '연결에 문제가 있어요. 백엔드 서버(localhost:8000)가 켜져 있는지 확인하고 잠시 후 다시 시도해 주세요. 🙏',
    }),
  ])
}

// ---------- 카드 액션(로컬 선택 상태) ----------

function handleToggleSpot(state, spot) {
  const already = state.trip.spots.some((sp) => sp.id === spot.id)
  const spots = already ? state.trip.spots.filter((sp) => sp.id !== spot.id) : [...state.trip.spots, spot]
  return patchTrip(state, { spots })
}

function handleSelectFlight(state, flight) {
  let s = patchTrip(state, {
    flight: { ...flight, route: flight.route || `${state.trip.destination ?? '여행지'} 항공` },
  })
  if (flight.date) s = patchTrip(s, { dateLabel: dateRangeLabel(flight.isoDate || flight.date, s.trip.nights || 3) })
  return patchTrip(s, { total: computeTotal(s.trip) })
}

function handleSelectHotel(state, hotel) {
  const nights = state.trip.nights || 3
  const hotels = [...state.trip.hotels, { ...hotel, nights }]
  const s = patchTrip(state, { hotels })
  return patchTrip(s, { total: computeTotal(s.trip) })
}

// ---------- 루트 리듀서 ----------

export function conversationReducer(state, action) {
  switch (action.type) {
    case 'USER_MESSAGE':
      return handleUserMessage(state, action.text)
    case 'AGENT_REPLY':
      return handleAgentReply(state, action.turns || [])
    case 'STREAM_TEXT_START':
      return handleStreamTextStart(state, action.cardType)
    case 'STREAM_TEXT_DELTA':
      return handleStreamDelta(state, action.text)
    case 'STREAM_TEXT_END':
      return handleStreamTextEnd(state, action.payload)
    case 'STREAM_CARD':
    case 'STREAM_TEXT':
      return applyTurn({ ...dropTrailingStatus(state), streamingId: null }, action.turn)
    case 'STREAM_DONE':
      return { ...dropTrailingStatus(state), loading: false, streamingId: null }
    case 'AGENT_ERROR':
      return handleAgentError(state)
    case 'DISABLE_QUICK_REPLY':
      return disableQuickReply(state, action.msgId, action.optionId)
    case 'TOGGLE_SPOT':
      return handleToggleSpot(state, action.spot)
    case 'SELECT_FLIGHT':
      return handleSelectFlight(state, action.flight)
    case 'SELECT_HOTEL':
      return handleSelectHotel(state, action.hotel)
    case 'SELECT_ROUTE_PREVIEW':
      return patchTrip(state, { routePlan: action.routeId })
    case 'RESET':
      return createInitialState()
    default:
      return state
  }
}

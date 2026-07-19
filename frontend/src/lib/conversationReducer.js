// 대화 상태 머신 — 두 개의 스크립트된 시나리오(제주 / 보홀+세부)를 진행시킨다.
// 원칙: reducer는 순수 함수로 유지하고, "생각 중" 딜레이는 pendingAdvance 토큰을
// App.jsx의 useEffect가 감시하다가 AUTO_ADVANCE를 dispatch하는 방식으로 처리한다.

import { nextId } from './id'
import { dateRangeLabel, addDaysLabel } from './format'
import { jeju } from './scenarios/jeju'
import { bohol } from './scenarios/bohol'

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

function dropTrailingStatus(state) {
  const last = state.messages[state.messages.length - 1]
  if (last && last.type === 'agent_status') {
    return { ...state, messages: state.messages.slice(0, -1) }
  }
  return state
}

let tokenCounter = 0
function withPending(state, stage, delay = 700) {
  tokenCounter += 1
  return { ...state, pendingAdvance: { token: tokenCounter, stage, delay } }
}

function disableQuickReply(state, msgId, optionId) {
  return {
    ...state,
    messages: state.messages.map((m) =>
      m.id === msgId ? { ...m, payload: { ...m.payload, disabled: true, selectedId: optionId } } : m,
    ),
  }
}

function disableInlineForm(state, msgId) {
  return {
    ...state,
    messages: state.messages.map((m) => (m.id === msgId ? { ...m, payload: { ...m.payload, confirmed: true } } : m)),
  }
}

function randomConfirmationCode() {
  const n = Math.floor(1000 + Math.random() * 9000)
  return `TA-2607-${n}`
}

// 선택된 항공/숙소를 바탕으로 실시간 합계를 계산 (우측 패널이 선택할 때마다 즉시 갱신되도록)
function computeTotal(trip) {
  const flightTotal = trip.flight ? trip.flight.price * (trip.travelers || 1) : 0
  const hotelsTotal = trip.hotels.reduce((sum, h) => sum + h.price * (h.nights || 1), 0)
  return flightTotal + hotelsTotal
}

function status(agent, text) {
  return bot('agent_status', { agent, text })
}

// ---------- 초기 상태 ----------

export function createInitialState() {
  return {
    scenario: null,
    stage: 'welcome',
    messages: [
      bot('text', {
        text: '안녕하세요! 어디로 떠나고 싶으세요? 목적지와 일정을 알려주시면 명소부터 항공·숙소·예약까지 여기서 바로 도와드려요. ✈️',
      }),
      bot('quick_replies', {
        options: [
          { id: 'start_jeju', label: '🏝 제주 3박4일' },
          { id: 'start_bohol', label: '🏖 보홀+세부 동선' },
          { id: 'start_busan', label: '🌊 부산 2박3일' },
        ],
      }),
    ],
    trip: {
      destination: null,
      dateLabel: null,
      travelers: null,
      spots: [],
      flight: null,
      hotels: [],
      routePlan: null,
      routeInfo: null,
      total: 0,
      confirmation: null,
    },
    pendingAdvance: null,
  }
}

// ---------- 시나리오 A: 제주 ----------

function startJeju(state) {
  let s = { ...state, scenario: 'jeju' }
  s = patchTrip(s, { destination: jeju.destination, travelers: jeju.travelers })
  s = append(s, [
    bot('text', { text: `좋아요, 제주 3박4일 · ${jeju.travelers}명이군요! 언제 떠나세요?` }),
    bot('inline_form', { kind: 'dates', startLabel: '2026.07.25', endLabel: '2026.07.28' }),
  ])
  return { ...s, stage: 'jeju:dates', pendingAdvance: null }
}

function handleConfirmDates(state, msgId) {
  let s = disableInlineForm(state, msgId)
  s = appendUserBubble(s, '2026.07.25 – 07.28 좋아요')
  s = patchTrip(s, { dateLabel: jeju.requestedDateLabel })
  s = append(s, [status('명소 에이전트', '제주 인기 명소 찾는 중…')])
  return withPending(s, 'jeju:spots-reveal', 900)
}

function jejuSpotsReveal(state) {
  const s = dropTrailingStatus(state)
  const msgs = [
    bot('text', { text: '제주에서 놓치면 아쉬운 명소들이에요 👇 마음에 들면 **담기**를 눌러주세요.' }),
    bot('destination_carousel', { items: jeju.spots }),
    bot('quick_replies', { options: [{ id: 'proceed_spots', label: '이 정도면 일정 짜줘' }] }),
  ]
  return { ...append(s, msgs), stage: 'jeju:spots', pendingAdvance: null }
}

function handleToggleSpot(state, spotId) {
  const already = state.trip.spots.some((sp) => sp.id === spotId)
  let spots
  if (already) {
    spots = state.trip.spots.filter((sp) => sp.id !== spotId)
  } else {
    const spot = jeju.spots.find((sp) => sp.id === spotId)
    spots = spot ? [...state.trip.spots, spot] : state.trip.spots
  }
  return patchTrip(state, { spots })
}

function jejuProceedToItinerary(state) {
  const s = append(state, [status('일정 에이전트', '일정 구성 중…')])
  return withPending(s, 'jeju:itinerary-reveal', 900)
}

function jejuItineraryReveal(state) {
  const s = dropTrailingStatus(state)
  const msgs = [
    bot('text', { text: '담아주신 명소로 **3박4일 일정 초안**을 짜봤어요 📅' }),
    bot('itinerary', { days: jeju.itinerary }),
    bot('quick_replies', {
      options: [
        { id: 'edit_itinerary', label: '✏️ 일정 수정' },
        { id: 'proceed_booking', label: '✈️ 항공·숙소 예약' },
      ],
    }),
  ]
  return { ...append(s, msgs), stage: 'jeju:itinerary', pendingAdvance: null }
}

function jejuFlightReveal(state) {
  const s = dropTrailingStatus(state)
  const msgs = [
    bot('text', { text: '김포 → 제주, **날짜별 최저가**예요. 저렴한 날을 고르면 그 날 항공편을 보여드릴게요 👇' }),
    bot('flight_results', {
      mode: 'byDate',
      routeLabel: '김포 → 제주',
      dates: jeju.flightDates,
      flightsByDate: jeju.flightsByDate,
    }),
  ]
  return { ...append(s, msgs), stage: 'jeju:flight', pendingAdvance: null }
}

function jejuHotelReveal(state) {
  const s = dropTrailingStatus(state)
  const flightDate = s.trip.flight.date
  const checkout = addDaysLabel(flightDate, 3)
  const banner = `체크인 ${flightDate} → 체크아웃 ${checkout} · 3박 (항공 일정 자동 반영)`
  const msgs = [
    bot('text', { text: `✅ **${flightDate} 항공**을 잡았어요. 이제 그 일정에 맞춰 숙소를 찾아볼게요 🏨` }),
    bot('hotel_results', { cityLabel: '제주', banner, regions: jeju.regions, hotels: jeju.hotels }),
  ]
  return { ...append(s, msgs), stage: 'jeju:hotel', pendingAdvance: null }
}

function jejuPayReveal(state) {
  const s = dropTrailingStatus(state)
  const flight = s.trip.flight
  const hotel = s.trip.hotels[0]
  const flightTotal = flight.price * jeju.travelers
  const hotelTotal = hotel.price * hotel.nights
  const total = flightTotal + hotelTotal
  const rows = [
    {
      icon: '✈️',
      label: `김포 → 제주 · ${flight.air}`,
      meta: `${jeju.travelers}명 · ${flight.price.toLocaleString('ko-KR')}원 × ${jeju.travelers}`,
      price: flightTotal,
    },
    { icon: '🏨', label: `${hotel.name} · ${hotel.nights}박`, meta: `${s.trip.dateLabel} · ${hotel.meta}`, price: hotelTotal },
  ]
  const msgs = [bot('booking_summary', { rows, total }), bot('payment', { total })]
  return { ...patchTrip(append(s, msgs), { total }), stage: 'jeju:pay', pendingAdvance: null }
}

function jejuDoneReveal(state) {
  const s = dropTrailingStatus(state)
  const code = randomConfirmationCode()
  const msgs = [
    bot('text', { text: '🎉 예약이 확정됐어요! 즐거운 제주 여행 되세요.' }),
    bot('confirmation', { code, title: `제주 3박4일 · ${jeju.travelers}명`, dateLabel: s.trip.dateLabel, total: s.trip.total }),
    bot('quick_replies', { options: [{ id: 'restart', label: '🔄 새 여행 시작하기' }] }),
  ]
  return {
    ...patchTrip(append(s, msgs), { confirmation: { code, total: s.trip.total } }),
    stage: 'jeju:done',
    pendingAdvance: null,
  }
}

// ---------- 시나리오 B: 보홀+세부 ----------

function startBohol(state) {
  let s = { ...state, scenario: 'bohol' }
  s = patchTrip(s, {
    destination: bohol.destination,
    travelers: bohol.travelers,
    dateLabel: bohol.requestedDateLabel,
    routePlan: 'A',
  })
  s = append(s, [status('동선 에이전트', '최적 동선 설계 중…')])
  return withPending(s, 'bohol:route-reveal', 900)
}

function boholRouteReveal(state) {
  const s = dropTrailingStatus(state)
  const msgs = [
    bot('text', {
      text: '보홀과 세부 둘 다 가시는군요! 두 지역을 **어떤 순서로 도는 게 좋을지** 두 가지 동선으로 짜봤어요 🗺',
    }),
    bot('route_plan', { routes: bohol.routePlans, compareStrip: bohol.compareStrip }),
    bot('quick_replies', {
      options: [
        { id: 'confirm_route', label: '이 동선으로 진행' },
        { id: 'route_more_bohol', label: '보홀 더 길게' },
      ],
    }),
  ]
  return { ...append(s, msgs), stage: 'bohol:route', pendingAdvance: null }
}

function routeMoreFallback(state) {
  return append(state, [
    bot('text', { text: '지금 데모에서는 기간 커스터마이징은 준비 중이에요. A안 / B안 중 하나로 진행해볼까요? 🙂' }),
  ])
}

function confirmRoute(state, routeId) {
  const route = bohol.routePlans[routeId]
  let s = patchTrip(state, { routePlan: routeId, routeInfo: route, destination: `보홀+세부 (${routeId}안)` })
  s = append(s, [
    bot('text', { text: `${routeId}안 기준 일정 짜볼게요 →` }),
    status('일정 에이전트', '일정 구성 중…'),
  ])
  return withPending(s, 'bohol:itinerary-reveal', 900)
}

function boholItineraryReveal(state) {
  const s = dropTrailingStatus(state)
  const days = bohol.itineraryFor(s.trip.routePlan)
  const msgs = [
    bot('text', { text: `${s.trip.routePlan}안으로 4박5일 일정 초안을 짜봤어요 📅` }),
    bot('itinerary', { days }),
    bot('quick_replies', {
      options: [
        { id: 'edit_itinerary', label: '✏️ 일정 수정' },
        { id: 'proceed_booking', label: '✈️ 항공·숙소 예약' },
      ],
    }),
  ]
  return { ...append(s, msgs), stage: 'bohol:itinerary', pendingAdvance: null }
}

function boholFlightReveal(state) {
  const s = dropTrailingStatus(state)
  const route = s.trip.routeInfo
  const flightInfo = bohol.flightsFor(route.first.city)
  const msgs = [
    bot('text', { text: `${flightInfo.label} 항공편이에요. 하나 골라주세요 ✈️` }),
    bot('flight_results', { mode: 'simple', routeLabel: flightInfo.label, options: flightInfo.options }),
  ]
  return { ...append(s, msgs), stage: 'bohol:flight', pendingAdvance: null }
}

function boholHotelReveal(state, stage) {
  const s = dropTrailingStatus(state)
  const route = s.trip.routeInfo
  const city = stage === 'bohol:hotel1' ? route.first.city : route.second.city
  const nightsLabel = stage === 'bohol:hotel1' ? '3.15 – 3.17 · 2박' : '3.17 – 3.19 · 2박'
  const hotels = bohol.hotelsByCity[city]
  const msgs = [bot('hotel_results', { cityLabel: city, banner: `${city} 숙소 · ${nightsLabel}`, hotels })]
  return { ...append(s, msgs), stage, pendingAdvance: null }
}

function boholPayReveal(state) {
  const s = dropTrailingStatus(state)
  const flight = s.trip.flight
  const hotels = s.trip.hotels
  const flightTotal = flight.price * bohol.travelers
  const hotelTotals = hotels.map((h) => h.price * h.nights)
  const total = flightTotal + hotelTotals.reduce((a, b) => a + b, 0)
  const rows = [
    {
      icon: '✈️',
      label: `${flight.route} · ${flight.air}`,
      meta: `${bohol.travelers}명 · ${flight.price.toLocaleString('ko-KR')}원 × ${bohol.travelers}`,
      price: flightTotal,
    },
    ...hotels.map((h, i) => ({ icon: '🏨', label: `${h.name} · ${h.nights}박`, meta: h.meta, price: hotelTotals[i] })),
  ]
  const msgs = [bot('booking_summary', { rows, total }), bot('payment', { total })]
  return { ...patchTrip(append(s, msgs), { total }), stage: 'bohol:pay', pendingAdvance: null }
}

function boholDoneReveal(state) {
  const s = dropTrailingStatus(state)
  const code = randomConfirmationCode()
  const msgs = [
    bot('text', { text: '🎉 예약이 확정됐어요! 즐거운 보홀·세부 여행 되세요.' }),
    bot('confirmation', {
      code,
      title: `보홀+세부 4박5일 · ${bohol.travelers}명`,
      dateLabel: s.trip.dateLabel,
      total: s.trip.total,
    }),
    bot('quick_replies', { options: [{ id: 'restart', label: '🔄 새 여행 시작하기' }] }),
  ]
  return {
    ...patchTrip(append(s, msgs), { confirmation: { code, total: s.trip.total } }),
    stage: 'bohol:done',
    pendingAdvance: null,
  }
}

// ---------- 공통 ----------

function busanFallback(state) {
  return append(state, [
    bot('text', {
      text: '아쉽지만 지금 데모에서는 부산 시나리오는 준비 중이에요. 대신 제주 3박4일이나 보홀+세부 동선을 체험해보시겠어요?',
    }),
    bot('quick_replies', {
      options: [
        { id: 'start_jeju', label: '🏝 제주 3박4일' },
        { id: 'start_bohol', label: '🏖 보홀+세부 동선' },
      ],
    }),
  ])
}

function editItineraryFallback(state) {
  return append(state, [
    bot('text', { text: '지금 데모에서는 일정 수정 기능은 준비 중이에요. 대신 예약을 계속 진행해볼까요? 😊' }),
    bot('quick_replies', { options: [{ id: 'proceed_booking', label: '✈️ 항공·숙소 예약' }] }),
  ])
}

function proceedToBooking(state) {
  if (state.scenario === 'jeju') {
    const s = append(state, [status('항공 에이전트', '김포→제주 항공권 찾는 중…')])
    return withPending(s, 'jeju:flight-reveal', 900)
  }
  const route = state.trip.routeInfo
  const s = append(state, [status('항공 에이전트', `인천→${route.first.city} 항공권 찾는 중…`)])
  return withPending(s, 'bohol:flight-reveal', 900)
}

function handleSelectFlight(state, flight) {
  const isJeju = state.scenario === 'jeju'
  let s = patchTrip(state, {
    flight: {
      ...flight,
      route: isJeju ? '김포 → 제주' : bohol.flightsFor(state.trip.routeInfo.first.city).label,
    },
  })
  if (isJeju) {
    s = patchTrip(s, { dateLabel: dateRangeLabel(flight.date, 3) })
  }
  s = patchTrip(s, { total: computeTotal(s.trip) })
  if (isJeju) {
    s = append(s, [status('숙소 에이전트', '제주 숙소 찾는 중…')])
    return withPending(s, 'jeju:hotel-reveal', 800)
  }
  const city1 = state.trip.routeInfo.first.city
  s = append(s, [status('숙소 에이전트', `${city1} 숙소 찾는 중…`)])
  return withPending(s, 'bohol:hotel1-reveal', 800)
}

function handleSelectHotel(state, hotel) {
  const nights = state.stage === 'jeju:hotel' ? 3 : 2
  const bookedHotel = { ...hotel, nights }
  const hotels = [...state.trip.hotels, bookedHotel]
  let s = patchTrip(state, { hotels })
  s = patchTrip(s, { total: computeTotal(s.trip) })

  if (state.stage === 'jeju:hotel') {
    s = append(s, [status('예약 에이전트', '예약 내용 정리하는 중…')])
    return withPending(s, 'jeju:pay-reveal', 600)
  }
  if (state.stage === 'bohol:hotel1') {
    const city2 = state.trip.routeInfo.second.city
    s = append(s, [
      bot('text', { text: `✅ **${hotel.name}** 예약을 담았어요. 이제 ${city2} 숙소를 찾아볼게요 🏨` }),
      status('숙소 에이전트', `${city2} 숙소 찾는 중…`),
    ])
    return withPending(s, 'bohol:hotel2-reveal', 800)
  }
  if (state.stage === 'bohol:hotel2') {
    s = append(s, [status('예약 에이전트', '예약 내용 정리하는 중…')])
    return withPending(s, 'bohol:pay-reveal', 600)
  }
  return s
}

function handlePay(state) {
  const s = append(state, [status('결제 에이전트', '결제 처리 중…')])
  const nextStage = state.scenario === 'jeju' ? 'jeju:done-reveal' : 'bohol:done-reveal'
  return withPending(s, nextStage, 900)
}

// optionId -> 클릭 시 채팅에 남길 사용자 발화 (echo)
const QUICK_REPLY_ECHO = {
  start_jeju: '제주 3박4일, 2명이서 갈래',
  start_bohol: '필리핀 3월중순, 보홀이랑 세부 다 갈래',
  start_busan: '부산 2박3일 가고 싶어',
  proceed_spots: '이 정도면 충분해요, 일정 짜줘',
  edit_itinerary: '일정을 조금 수정하고 싶어요',
  proceed_booking: '항공·숙소 예약할게요',
  route_more_bohol: '보홀 더 길게 있을까요?',
}

function handleIntent(state, optionId) {
  switch (optionId) {
    case 'start_jeju':
      return startJeju(state)
    case 'start_bohol':
      return startBohol(state)
    case 'start_busan':
      return busanFallback(state)
    case 'proceed_spots':
      return jejuProceedToItinerary(state)
    case 'edit_itinerary':
      return editItineraryFallback(state)
    case 'proceed_booking':
      return proceedToBooking(state)
    case 'confirm_route':
      return confirmRoute(state, state.trip.routePlan || 'A')
    case 'route_more_bohol':
      return routeMoreFallback(state)
    case 'do_pay':
      return handlePay(state)
    case 'restart':
      return createInitialState()
    default:
      return state
  }
}

// ---------- 자유 텍스트 의도 매칭 (dual entry) ----------

function matchIntent(state, rawText) {
  const t = rawText.replace(/\s/g, '')
  switch (state.stage) {
    case 'welcome':
      if (t.includes('제주')) return 'start_jeju'
      if (t.includes('보홀') || t.includes('세부') || t.includes('필리핀')) return 'start_bohol'
      if (t.includes('부산') || t.includes('도쿄')) return 'start_busan'
      return null
    case 'jeju:spots':
      if (t.includes('일정') || t.includes('다음') || t.includes('짜줘') || t.includes('완료')) return 'proceed_spots'
      return null
    case 'jeju:itinerary':
    case 'bohol:itinerary':
      if (t.includes('예약') || t.includes('항공') || t.includes('숙소')) return 'proceed_booking'
      if (t.includes('수정')) return 'edit_itinerary'
      return null
    case 'bohol:route':
      if (t.includes('진행') || t.includes('확정') || t.includes('좋아') || /[ab]안?/i.test(t)) return 'confirm_route'
      return null
    case 'jeju:pay':
    case 'bohol:pay':
      if (t.includes('결제')) return 'do_pay'
      return null
    case 'jeju:done':
    case 'bohol:done':
      if (t.includes('처음') || t.includes('다시') || t.includes('새여행')) return 'restart'
      return null
    default:
      return null
  }
}

function fallbackReplyFor(stage) {
  switch (stage) {
    case 'welcome':
      return '제주 3박4일 또는 보홀+세부 동선으로 시작해볼까요? 위 칩을 눌러도 되고, "제주" 또는 "보홀"이라고 입력해도 돼요 🙂'
    case 'jeju:spots':
      return '마음에 드는 명소를 담고 "일정 짜줘"라고 말해주세요 🙂'
    case 'jeju:flight':
    case 'bohol:flight':
      return '카드에서 원하는 항공편의 [예약]을 눌러주세요 👆'
    case 'jeju:hotel':
    case 'bohol:hotel1':
    case 'bohol:hotel2':
      return '카드에서 원하는 숙소의 [예약]을 눌러주세요 👆'
    case 'jeju:pay':
    case 'bohol:pay':
      return '아래 [결제하기] 버튼을 눌러주세요 💳'
    default:
      return '네, 확인했어요 🙂'
  }
}

function handleText(state, text) {
  const trimmed = text.trim()
  if (!trimmed) return state
  let s = appendUserBubble(state, trimmed)
  const intent = matchIntent(state, trimmed)
  if (intent === 'confirm_route') {
    if (/b안?/i.test(trimmed)) s = patchTrip(s, { routePlan: 'B' })
    else if (/a안?/i.test(trimmed)) s = patchTrip(s, { routePlan: 'A' })
    return handleIntent(s, 'confirm_route')
  }
  if (intent) return handleIntent(s, intent)
  return append(s, [bot('text', { text: fallbackReplyFor(state.stage) })])
}

function handlePanelProceed(state) {
  switch (state.stage) {
    case 'jeju:itinerary':
      return handleIntent(appendUserBubble(state, '항공·숙소 예약할게요'), 'proceed_booking')
    case 'bohol:route': {
      const routeId = state.trip.routePlan || 'A'
      const s = appendUserBubble(state, `${routeId}안으로 진행할게요`)
      return handleIntent(s, 'confirm_route')
    }
    case 'bohol:itinerary':
      return handleIntent(appendUserBubble(state, '항공·숙소 예약할게요'), 'proceed_booking')
    case 'jeju:done':
    case 'bohol:done':
      return createInitialState()
    case 'welcome':
      return state
    default:
      return append(state, [bot('text', { text: '지금은 채팅 카드에서 선택해주세요 👆' })])
  }
}

// ---------- 지연된(자동 진행) 단계 실행 ----------

function runStage(state, stageKey) {
  switch (stageKey) {
    case 'jeju:spots-reveal':
      return jejuSpotsReveal(state)
    case 'jeju:itinerary-reveal':
      return jejuItineraryReveal(state)
    case 'jeju:flight-reveal':
      return jejuFlightReveal(state)
    case 'jeju:hotel-reveal':
      return jejuHotelReveal(state)
    case 'jeju:pay-reveal':
      return jejuPayReveal(state)
    case 'jeju:done-reveal':
      return jejuDoneReveal(state)
    case 'bohol:route-reveal':
      return boholRouteReveal(state)
    case 'bohol:itinerary-reveal':
      return boholItineraryReveal(state)
    case 'bohol:flight-reveal':
      return boholFlightReveal(state)
    case 'bohol:hotel1-reveal':
      return boholHotelReveal(state, 'bohol:hotel1')
    case 'bohol:hotel2-reveal':
      return boholHotelReveal(state, 'bohol:hotel2')
    case 'bohol:pay-reveal':
      return boholPayReveal(state)
    case 'bohol:done-reveal':
      return boholDoneReveal(state)
    default:
      return { ...state, pendingAdvance: null }
  }
}

// ---------- 루트 리듀서 ----------

export function conversationReducer(state, action) {
  switch (action.type) {
    case 'QUICK_REPLY': {
      if (action.optionId === 'proceed_spots' && state.trip.spots.length === 0) {
        return append(state, [bot('text', { text: '명소를 1개 이상 담아주시면 일정을 짜드릴게요 🙂' })])
      }
      let s = disableQuickReply(state, action.msgId, action.optionId)
      if (action.optionId === 'confirm_route') {
        const routeId = state.trip.routePlan || 'A'
        s = appendUserBubble(s, `${routeId}안으로 진행할게요`)
        return handleIntent(s, 'confirm_route')
      }
      const echo = QUICK_REPLY_ECHO[action.optionId]
      if (echo) s = appendUserBubble(s, echo)
      return handleIntent(s, action.optionId)
    }
    case 'SEND_TEXT':
      return handleText(state, action.text)
    case 'TOGGLE_SPOT':
      return handleToggleSpot(state, action.spotId)
    case 'CONFIRM_DATES':
      return handleConfirmDates(state, action.msgId)
    case 'SELECT_FLIGHT':
      return handleSelectFlight(state, action.flight)
    case 'SELECT_HOTEL':
      return handleSelectHotel(state, action.hotel)
    case 'SELECT_ROUTE_PREVIEW':
      return patchTrip(state, { routePlan: action.routeId })
    case 'PAY':
      return handlePay(state)
    case 'PANEL_PROCEED':
      return handlePanelProceed(state)
    case 'AUTO_ADVANCE': {
      if (!state.pendingAdvance || state.pendingAdvance.token !== action.token) return state
      return runStage(state, state.pendingAdvance.stage)
    }
    case 'RESET':
      return createInitialState()
    default:
      return state
  }
}

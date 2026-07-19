// 시나리오 B — 필리핀 보홀+세부 (멀티 목적지 동선 A/B안 → 확정 후 순차 예약으로 연결)

export const bohol = {
  destination: '보홀+세부',
  travelers: 2,
  requestedDateLabel: '3월 중순 · 4박',

  routePlans: {
    A: {
      id: 'A',
      label: '세부 먼저',
      first: { city: '세부', icon: '✈️', arriveLabel: '세부 도착 · 2박', sub: '시티투어 · 다이빙' },
      transferLabel: '🚤 페리 2시간 · 세부→보홀',
      second: { city: '보홀', icon: '🏝', arriveLabel: '보홀 · 2박', sub: '초콜릿힐 · 해변' },
      endNote: '✈️ 보홀에서 출국',
      highlight: '이동 동선 깔끔 · 자연 마무리',
    },
    B: {
      id: 'B',
      label: '보홀 먼저',
      first: { city: '보홀', icon: '✈️', arriveLabel: '보홀 도착 · 2박', sub: '해변 · 호핑투어' },
      transferLabel: '🚤 페리 2시간 · 보홀→세부',
      second: { city: '세부', icon: '🏙', arriveLabel: '세부 · 2박', sub: '쇼핑 · 맛집' },
      endNote: '✈️ 세부에서 출국 (공항 5분)',
      highlight: '마지막날 공항 접근 편리',
    },
  },

  compareStrip: {
    totalMove: '항공 2 · 페리 1',
    lastDayAirport: 'A 보홀 / B 세부',
  },

  // route 확정 후 4박 일정 (첫 도시 2박 + 이동 + 둘째 도시 2박)
  itineraryFor(routeId) {
    const route = bohol.routePlans[routeId]
    const [city1, city2] = [route.first.city, route.second.city]
    return [
      {
        day: 1,
        dateLabel: '3.15 일',
        title: `${city1} 도착 · 시내`,
        items: [
          { time: '11:20', text: `인천 → ${city1} 도착` },
          { time: '14:00', text: '호텔 체크인 · 휴식' },
          { time: '19:00', text: `${city1} 시내 야시장 투어`, accent: true },
        ],
      },
      {
        day: 2,
        dateLabel: '3.16 월',
        title: `${city1} 액티비티`,
        items: [
          { time: '09:00', text: city1 === '세부' ? '아일랜드 호핑 투어' : '알로나비치 스노클링' },
          { time: '14:00', text: city1 === '세부' ? '오슬롭 고래상어 투어' : '팡라오 돌핀 와칭' },
          { time: '19:00', text: '해산물 저녁 🦐', accent: true },
        ],
      },
      {
        day: 3,
        dateLabel: '3.17 화',
        title: `${route.transferLabel.replace('🚤 ', '')} · ${city2} 도착`,
        items: [
          { time: '09:00', text: '페리터미널 이동' },
          { time: '10:00', text: `⛴ 페리 2시간 · ${city1} → ${city2}` },
          { time: '15:00', text: `${city2} 호텔 체크인` },
          { time: '18:00', text: city2 === '보홀' ? '알로나비치 선셋' : '세부 시내 맛집 투어', accent: true },
        ],
      },
      {
        day: 4,
        dateLabel: '3.18 수',
        title: `${city2} · 출국`,
        items: [
          { time: '09:00', text: city2 === '보홀' ? '초콜릿힐 · 로보크 리버크루즈' : 'IT파크 쇼핑' },
          { time: '13:00', text: '공항 이동 · 수하물 위탁' },
          { time: '16:40', text: `${city2} → 인천 귀국편`, accent: true },
        ],
      },
    ]
  },

  // 국제선은 첫 도시의 국제공항으로 (세부=막탄세부, 보홀=팡라오)
  flightsFor(firstCity) {
    const dest = firstCity === '세부' ? '막탄세부(CEB)' : '팡라오(TAG)'
    return {
      label: `인천 → ${dest}`,
      options: [
        { air: '필리핀항공', dep: '09:20', arr: '13:10', dur: '4시간 50분', price: 412000 },
        { air: '세부퍼시픽', dep: '19:05', arr: '22:55', dur: '4시간 50분', price: 358000, tag: '최저가' },
      ],
    }
  },

  hotelsByCity: {
    세부: [
      { id: 'radisson-cebu', name: '래디슨 블루 세부', region: '세부', meta: '시내 · 루프탑풀', price: 98000, rating: 4.5, gradient: 4 },
      { id: 'crimson-cebu', name: '크림슨 리조트 막탄', region: '세부', meta: '막탄 · 프라이빗비치', price: 165000, rating: 4.7, gradient: 0 },
    ],
    보홀: [
      { id: 'amorita', name: '아모리타 리조트', region: '보홀', meta: '알로나비치 · 인피니티풀', price: 142000, rating: 4.8, gradient: 1 },
      { id: 'bluewater-panglao', name: '블루워터 팡라오', region: '보홀', meta: '프라이빗비치 · 가족형', price: 118000, rating: 4.6, gradient: 3 },
    ],
  },
}

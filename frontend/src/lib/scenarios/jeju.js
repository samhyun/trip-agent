// 시나리오 A — 제주 3박4일 (단일 목적지 + 순차 예약: 항공 날짜별 가격 → 숙소 지역별)

export const jeju = {
  destination: '제주',
  travelers: 2,
  requestedDateLabel: '7.25 – 7.28',

  spots: [
    { id: 'seongsan', name: '성산일출봉', tags: ['#자연', '#일출'], gradient: 0 },
    { id: 'udo', name: '우도', tags: ['#섬', '#드라이브'], gradient: 1 },
    { id: 'hallasan', name: '한라산', tags: ['#등산', '#절경'], gradient: 2 },
    { id: 'hyeopjae', name: '협재해변', tags: ['#해변', '#석양'], gradient: 3 },
  ],

  itinerary: [
    {
      day: 1,
      dateLabel: '7.25 금',
      title: '성산 · 우도 · 흑돼지',
      items: [
        { time: '09:30', text: '성산일출봉 등반 · 정상 전망' },
        { time: '12:30', text: '성산 흑돼지 점심 🍖' },
        { time: '14:00', text: '우도 페리 · 섬 한바퀴 드라이브' },
        { time: '18:00', text: '숙소 체크인 · 휴식', accent: true },
      ],
    },
    {
      day: 2,
      dateLabel: '7.26 토',
      title: '한라산 · 카페거리',
      items: [
        { time: '08:00', text: '한라산 성판악 코스 트레킹' },
        { time: '13:00', text: '애월 카페거리 브런치 ☕' },
        { time: '16:00', text: '애월 해안도로 드라이브 · 노을', accent: true },
      ],
    },
    {
      day: 3,
      dateLabel: '7.27 일',
      title: '협재 · 곽지 해변',
      items: [
        { time: '10:00', text: '협재해변 · 에메랄드빛 바다' },
        { time: '13:00', text: '곽지해수욕장 산책' },
        { time: '19:00', text: '흑돼지 근고기 저녁 🍖', accent: true },
      ],
    },
    {
      day: 4,
      dateLabel: '7.28 월',
      title: '공항 근처 · 출국',
      items: [
        { time: '10:00', text: '동문시장 기념품 쇼핑' },
        { time: '13:00', text: '공항 이동 · 수하물 위탁' },
        { time: '15:20', text: '제주 → 김포 귀국편', accent: true },
      ],
    },
  ],

  // 날짜별 최저가 (편도 · 1인)
  flightDates: [
    { key: '7.24', wd: '목', price: 89000, low: true },
    { key: '7.25', wd: '금', price: 112000 },
    { key: '7.26', wd: '토', price: 134000 },
    { key: '7.27', wd: '일', price: 98000 },
  ],

  flightsByDate: {
    '7.24': [
      { air: '대한항공', dep: '07:30', arr: '08:40', dur: '1시간 10분', price: 89000, tag: '최저가' },
      { air: '진에어', dep: '11:20', arr: '12:25', dur: '1시간 05분', price: 94000 },
      { air: '제주항공', dep: '19:10', arr: '20:20', dur: '1시간 10분', price: 112000 },
    ],
    '7.25': [
      { air: '대한항공', dep: '09:00', arr: '10:10', dur: '1시간 10분', price: 112000 },
      { air: '아시아나', dep: '13:40', arr: '14:50', dur: '1시간 10분', price: 124000 },
    ],
    '7.26': [
      { air: '티웨이', dep: '08:15', arr: '09:25', dur: '1시간 10분', price: 134000 },
      { air: '대한항공', dep: '16:50', arr: '18:00', dur: '1시간 10분', price: 142000 },
    ],
    '7.27': [
      { air: '진에어', dep: '10:05', arr: '11:10', dur: '1시간 05분', price: 98000 },
      { air: '제주항공', dep: '18:30', arr: '19:40', dur: '1시간 10분', price: 108000 },
    ],
  },

  regions: ['전체', '제주시', '서귀포', '애월'],

  hotels: [
    { id: 'shilla', name: '제주신라호텔', region: '서귀포', meta: '오션뷰 · 조식 포함', price: 138000, rating: 4.8, gradient: 3 },
    { id: 'lotte', name: '롯데호텔 제주', region: '서귀포', meta: '중문 · 인피니티풀', price: 152000, rating: 4.7, gradient: 4 },
    { id: 'hyatt', name: '그랜드 하얏트 제주', region: '제주시', meta: '공항 15분 · 시티뷰', price: 121000, rating: 4.6, gradient: 5 },
    { id: 'aewol-pension', name: '애월 오션 펜션', region: '애월', meta: '해안도로 · 카페거리 도보', price: 95000, rating: 4.5, gradient: 1 },
  ],
}

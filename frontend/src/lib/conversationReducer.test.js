import { describe, it, expect } from 'vitest'

import { conversationReducer, createInitialState } from './conversationReducer'

// 액션들을 초기 상태부터 순서대로 reduce
function reduce(actions, initial = createInitialState()) {
  return actions.reduce((s, a) => conversationReducer(s, a), initial)
}

describe('createInitialState', () => {
  it('welcome 단계 + 기본 trip', () => {
    const s = createInitialState()
    expect(s.stage).toBe('welcome')
    expect(s.trip.travelers).toBe(1)
    expect(s.trip.hotels).toEqual([])
    expect(s.trip.total).toBe(0)
  })
})

describe('USER_MESSAGE — 인원/박수 추출', () => {
  it('둘이 → 2명, 2박', () => {
    const s = reduce([{ type: 'USER_MESSAGE', text: '둘이서 2박 3일 가려고' }])
    expect(s.trip.travelers).toBe(2)
    expect(s.trip.nights).toBe(2)
    expect(s.stage).toBe('active')
  })

  it('스플릿 스테이 박수 합산 (1박 + 1박 = 2)', () => {
    const s = reduce([{ type: 'USER_MESSAGE', text: '제주시 1박, 서귀포 1박' }])
    expect(s.trip.nights).toBe(2)
  })

  it('혼자 → 1명', () => {
    const s = reduce([{ type: 'USER_MESSAGE', text: '혼자 3박 갈래' }])
    expect(s.trip.travelers).toBe(1)
    expect(s.trip.nights).toBe(3)
  })

  it('숫자 인원 (4명)', () => {
    const s = reduce([{ type: 'USER_MESSAGE', text: '4명이서 갈래' }])
    expect(s.trip.travelers).toBe(4)
  })
})

describe('SELECT_FLIGHT — computeTotal', () => {
  it('항공 합계 = 가격 × 인원', () => {
    const s = reduce([
      { type: 'USER_MESSAGE', text: '둘이서 갈래' }, // travelers 2
      { type: 'SELECT_FLIGHT', flight: { id: 'f1', price: 150000 } },
    ])
    expect(s.trip.flight.price).toBe(150000)
    expect(s.trip.total).toBe(300000) // 150000 × 2
  })
})

describe('SELECT_HOTEL — cardKey 토글/교체/합계', () => {
  const hotelA = {
    id: 'h1',
    cardKey: '제주:제주시:0',
    price: 100000,
    cardNights: 2,
    cardStay: '8.15–8.17',
    cardOrder: 0,
  }
  const hotelB = {
    id: 'h2',
    cardKey: '제주:서귀포:1',
    price: 80000,
    cardNights: 1,
    cardStay: '8.17–8.18',
    cardOrder: 1,
  }

  it('숙소 선택 → 추가 + cardNights 기준 합계', () => {
    const s = reduce([{ type: 'SELECT_HOTEL', hotel: hotelA }])
    expect(s.trip.hotels).toHaveLength(1)
    expect(s.trip.hotels[0].nights).toBe(2)
    expect(s.trip.total).toBe(200000) // 100000 × 2박
  })

  it('같은 (id + cardKey) 재선택 → 해제', () => {
    const s = reduce([
      { type: 'SELECT_HOTEL', hotel: hotelA },
      { type: 'SELECT_HOTEL', hotel: hotelA },
    ])
    expect(s.trip.hotels).toHaveLength(0)
    expect(s.trip.total).toBe(0)
  })

  it('다른 cardKey → 추가 (스플릿 스테이)', () => {
    const s = reduce([
      { type: 'SELECT_HOTEL', hotel: hotelA },
      { type: 'SELECT_HOTEL', hotel: hotelB },
    ])
    expect(s.trip.hotels).toHaveLength(2)
    expect(s.trip.total).toBe(280000) // 100000×2 + 80000×1
  })

  it('같은 cardKey 다른 숙소 → 제자리 교체', () => {
    const hotelA2 = { ...hotelA, id: 'h9', price: 120000 }
    const s = reduce([
      { type: 'SELECT_HOTEL', hotel: hotelA },
      { type: 'SELECT_HOTEL', hotel: hotelA2 },
    ])
    expect(s.trip.hotels).toHaveLength(1)
    expect(s.trip.hotels[0].id).toBe('h9')
    expect(s.trip.total).toBe(240000) // 120000 × 2박
  })
})

describe('RESET', () => {
  it('초기 상태로 되돌림', () => {
    const s = reduce([
      { type: 'USER_MESSAGE', text: '4명 3박 갈래' },
      { type: 'RESET' },
    ])
    expect(s.trip.travelers).toBe(1)
    expect(s.stage).toBe('welcome')
  })
})

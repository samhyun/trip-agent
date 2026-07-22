import { describe, it, expect } from 'vitest'

import { won, addDaysLabel, dateRangeLabel } from './format'

describe('won', () => {
  it('천 단위 구분 포맷', () => {
    expect(won(1350000)).toBe('₩1,350,000')
  })

  it('null은 ₩0', () => {
    expect(won(null)).toBe('₩0')
  })

  it('반올림', () => {
    expect(won(1000.6)).toBe('₩1,001')
  })
})

describe('addDaysLabel', () => {
  it('ISO 날짜에 일수 더하기 (월 넘김)', () => {
    expect(addDaysLabel('2026-08-30', 3)).toBe('9.2')
  })

  it('같은 달 안에서', () => {
    expect(addDaysLabel('2026-08-15', 2)).toBe('8.17')
  })

  it('연 넘김', () => {
    expect(addDaysLabel('2026-12-31', 1)).toBe('1.1')
  })

  it('"M.D" 라벨 폴백 (같은 달 가정)', () => {
    expect(addDaysLabel('8.15', 2)).toBe('8.17')
  })
})

describe('dateRangeLabel', () => {
  it('ISO 범위 라벨', () => {
    // "8.15 – 8.18" (구분자는 en-dash)
    expect(dateRangeLabel('2026-08-15', 3)).toMatch(/^8\.15 . 8\.18$/)
  })

  it('시작일 null이면 빈 문자열', () => {
    expect(dateRangeLabel(null, 3)).toBe('')
  })
})

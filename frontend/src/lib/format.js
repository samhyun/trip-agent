// 통화·날짜 포맷 유틸

export function won(amount) {
  if (amount == null) return '₩0'
  return `₩${Math.round(amount).toLocaleString('ko-KR')}`
}

const ISO_RE = /^\d{4}-\d{2}-\d{2}$/

function labelFromDate(d) {
  return `${d.getMonth() + 1}.${d.getDate()}`
}

// 시작일에 일수를 더해 "M.D" 라벨로 반환.
// ISO("2026-07-24")면 실제 날짜 계산(월/연 넘어감 정확), "M.D" 라벨이면 같은 달 가정 폴백.
export function addDaysLabel(start, days) {
  if (ISO_RE.test(start)) {
    const d = new Date(`${start}T00:00:00`)
    d.setDate(d.getDate() + days)
    return labelFromDate(d)
  }
  const [month, day] = String(start).split('.').map(Number)
  return `${month}.${day + days}`
}

// 시작일(ISO 우선) ~ nights 후 라벨 범위. 표시는 "M.D – M.D".
export function dateRangeLabel(start, nights) {
  if (start == null) return ''
  const startLabel = ISO_RE.test(start)
    ? labelFromDate(new Date(`${start}T00:00:00`))
    : String(start)
  return `${startLabel} – ${addDaysLabel(start, nights)}`
}

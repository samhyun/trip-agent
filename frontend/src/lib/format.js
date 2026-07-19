// 통화·날짜 포맷 유틸

export function won(amount) {
  if (amount == null) return '₩0'
  return `₩${Math.round(amount).toLocaleString('ko-KR')}`
}

// "7.24" 형태의 날짜 문자열에 일수를 더해 "7.27" 형태로 반환 (같은 달 가정, 데모 범위)
export function addDaysLabel(dateStr, days) {
  const [month, day] = dateStr.split('.').map(Number)
  return `${month}.${day + days}`
}

export function dateRangeLabel(startStr, nights) {
  return `${startStr} – ${addDaysLabel(startStr, nights)}`
}

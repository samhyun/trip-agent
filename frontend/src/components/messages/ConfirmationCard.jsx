import { won } from '../../lib/format'

function downloadConfirmation(payload) {
  const content = `Trip Agent 예약 확정서
확정번호: ${payload.code}
여행: ${payload.title}
일정: ${payload.dateLabel}
결제금액: ${won(payload.total)}
`
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${payload.code}.txt`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export default function ConfirmationCard({ payload }) {
  return (
    <div className="confirmation-card fade-up">
      <div className="confirmation-card__qr">
        <div className="confirmation-card__qr-pattern" />
      </div>
      <div className="confirmation-card__meta">
        <span>예약 확정서</span>
        <span className="confirmation-card__title">{payload.title}</span>
        <span>확정번호 {payload.code}</span>
        <span>
          {payload.dateLabel} · {won(payload.total)}
        </span>
      </div>
      <button type="button" className="confirmation-card__save" onClick={() => downloadConfirmation(payload)}>
        확정서 저장
      </button>
    </div>
  )
}

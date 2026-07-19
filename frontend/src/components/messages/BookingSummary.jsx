import { won } from '../../lib/format'

export default function BookingSummary({ rows, total }) {
  return (
    <div className="card card-lg fade-up" style={{ overflow: 'hidden' }}>
      <div className="booking-summary__header">예약 요약</div>
      <div className="booking-summary__rows">
        {rows.map((row) => (
          <div key={row.label} className="booking-summary__row">
            <span className="booking-summary__icon">{row.icon}</span>
            <div className="booking-summary__meta">
              <strong>{row.label}</strong>
              <span>{row.meta}</span>
            </div>
            <span className="booking-summary__price">{won(row.price)}</span>
          </div>
        ))}
      </div>
      <div className="booking-summary__total">
        <strong>합계</strong>
        <span className="booking-summary__total-value">{won(total)}</span>
      </div>
    </div>
  )
}

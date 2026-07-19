import { won } from '../../lib/format'

export default function PaymentCard({ total, dispatch, stage }) {
  const paid = stage.endsWith(':done')

  return (
    <div className="card payment-card fade-up">
      <div className="payment-card__method">
        <div className="payment-card__logo" />
        <div className="payment-card__method-meta">
          <strong>신한카드</strong>
          <span>•••• •••• •••• 1234</span>
        </div>
        <button type="button" className="payment-card__change" disabled={paid}>
          변경
        </button>
      </div>
      <button type="button" className="btn btn-accent btn-block" disabled={paid} onClick={() => dispatch({ type: 'PAY' })}>
        {paid ? '✓ 결제 완료' : `${won(total)} 결제하기`}
      </button>
      {!paid && <div className="payment-card__note">데모 결제입니다 · 실제로 청구되지 않아요</div>}
    </div>
  )
}

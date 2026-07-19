export default function InlineForm({ message, dispatch }) {
  const { startLabel, endLabel, confirmed } = message.payload

  return (
    <div className="inline-form">
      <div className="inline-form__field">
        <span>📅 출발</span>
        <strong>{startLabel}</strong>
      </div>
      <span className="inline-form__arrow">→</span>
      <div className="inline-form__field">
        <span>도착</span>
        <strong>{endLabel}</strong>
      </div>
      <button
        type="button"
        className="btn btn-primary"
        style={{ marginLeft: 'auto' }}
        disabled={confirmed}
        onClick={() => dispatch({ type: 'CONFIRM_DATES', msgId: message.id })}
      >
        {confirmed ? '✓ 확인됨' : '확인'}
      </button>
    </div>
  )
}

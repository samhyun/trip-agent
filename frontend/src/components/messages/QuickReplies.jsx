export default function QuickReplies({ message, dispatch }) {
  const { options, disabled, selectedId } = message.payload

  return (
    <div className="quick-replies">
      {options.map((opt) => {
        const isSelected = selectedId === opt.id
        return (
          <button
            key={opt.id}
            type="button"
            className={`pill${isSelected ? ' pill--solid' : ''}`}
            disabled={disabled}
            onClick={() => dispatch({ type: 'QUICK_REPLY', msgId: message.id, optionId: opt.id })}
          >
            {isSelected ? '✓ ' : ''}
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}

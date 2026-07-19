import { gradientFor } from '../../lib/gradients'

export default function DestinationCarousel({ items, selectedIds, dispatch }) {
  return (
    <div className="carousel scroll-thin">
      {items.map((item) => {
        const added = selectedIds.includes(item.id)
        return (
          <div key={item.id} className="dest-card">
            <div className="dest-card__thumb" style={{ backgroundImage: `${gradientFor(item.gradient)}, repeating-linear-gradient(45deg, oklch(1 0 0 / 0.06) 0 8px, transparent 8px 16px)` }}>
              [ {item.name} 사진 ]
            </div>
            <div className="dest-card__body">
              <span className="dest-card__title">{item.name}</span>
              <div className="dest-card__tags">
                {item.tags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
              <button
                type="button"
                className={`dest-card__add${added ? ' dest-card__add--added' : ''}`}
                onClick={() => dispatch({ type: 'TOGGLE_SPOT', spotId: item.id })}
              >
                {added ? '✓ 담음' : '＋ 담기'}
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

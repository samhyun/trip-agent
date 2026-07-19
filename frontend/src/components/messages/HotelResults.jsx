import { useState } from 'react'
import { won } from '../../lib/format'
import { gradientFor } from '../../lib/gradients'

export default function HotelResults({ payload, selectedHotel, dispatch }) {
  const { banner, regions, hotels, cityLabel } = payload
  const locked = Boolean(selectedHotel)
  const [region, setRegion] = useState('전체')

  const visibleHotels = regions && region !== '전체' ? hotels.filter((h) => h.region === region) : hotels

  return (
    <div className="card card-lg fade-up" style={{ overflow: 'hidden' }}>
      <div className="hotel-banner">
        <span>📅</span>
        <span>{banner}</span>
      </div>

      {regions && (
        <div className="region-filter scroll-thin">
          {regions.map((r) => (
            <button
              key={r}
              type="button"
              className={`chip${r === region ? ' chip--active' : ''}`}
              onClick={() => setRegion(r)}
            >
              {r}
            </button>
          ))}
        </div>
      )}

      <div className="hotel-list">
        {visibleHotels.map((hotel) => {
          const isSelected = selectedHotel?.id === hotel.id
          return (
            <div
              key={hotel.id}
              className={`hotel-card${isSelected ? ' hotel-card--selected' : ''}${locked && !isSelected ? ' hotel-card--disabled' : ''}`}
            >
              <div className="hotel-card__thumb" style={{ backgroundImage: `${gradientFor(hotel.gradient ?? 0)}, repeating-linear-gradient(45deg, oklch(1 0 0 / 0.06) 0 7px, transparent 7px 14px)` }}>
                [ 호텔 ]
              </div>
              <div className="hotel-card__body">
                <div className="hotel-card__name-row">
                  <span className="hotel-card__name">{hotel.name}</span>
                  <span className="hotel-card__rating">★ {hotel.rating}</span>
                </div>
                <span className="hotel-card__meta">📍 {hotel.region} · {hotel.meta}</span>
                <div className="hotel-card__footer">
                  <span className="hotel-card__price">{won(hotel.price)}</span>
                  <span className="hotel-card__price-unit">/ 박</span>
                  {isSelected ? (
                    <span className="flight-card__selected-tag" style={{ marginLeft: 'auto' }}>
                      ✓ 선택됨
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="hotel-card__book-btn"
                      disabled={locked}
                      onClick={() => dispatch({ type: 'SELECT_HOTEL', hotel })}
                    >
                      {locked ? '예약 완료' : '예약'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          )
        })}
        {visibleHotels.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--muted)', fontSize: 13, padding: '16px 8px' }}>
            {region} 지역에는 조건에 맞는 숙소가 없어요. 다른 지역을 선택해보세요.
          </div>
        )}
      </div>
    </div>
  )
}

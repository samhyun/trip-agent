import { useEffect, useState } from 'react'
import { won } from '../../lib/format'
import CardThumb from './CardThumb'
import HotelDetailModal from './HotelDetailModal'

export default function HotelResults({ payload, selectedHotel, locked = false, dispatch }) {
  const { banner, regions, hotels, cityLabel } = payload
  const city = payload.city || cityLabel
  // locked = 결제 완료(그 전엔 자유롭게 변경/재선택 가능)
  const [region, setRegion] = useState('전체')
  const [detailHotel, setDetailHotel] = useState(null)
  // 이미 선택한 숙소가 있으면(예약 완료 상태로 재마운트) 그 항목이 보이도록 펼친 채로 시작
  const [showAll, setShowAll] = useState(Boolean(selectedHotel))

  const INITIAL = 4
  // 선택이 마운트 후에 설정돼도 그 항목이 보이도록 펼침 동기화
  useEffect(() => {
    if (selectedHotel) setShowAll(true)
  }, [selectedHotel])
  const visibleHotels = regions && region !== '전체' ? hotels.filter((h) => h.region === region) : hotels
  const shownHotels = showAll ? visibleHotels : visibleHotels.slice(0, INITIAL)

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
              disabled={locked}
              style={locked ? { opacity: 0.5, cursor: 'not-allowed' } : undefined}
              onClick={() => { setRegion(r); setShowAll(false) }}
            >
              {r}
            </button>
          ))}
        </div>
      )}

      <div className="hotel-list">
        {shownHotels.map((hotel) => {
          const isSelected = selectedHotel?.id === hotel.id
          return (
            <div
              key={hotel.id}
              className={`hotel-card${isSelected ? ' hotel-card--selected' : ''}${locked && !isSelected ? ' hotel-card--disabled' : ''}`}
            >
              <CardThumb
                image={hotel.image}
                gradient={hotel.gradient ?? 0}
                label="[ 호텔 ]"
                className="hotel-card__thumb"
                stripe={7}
              />
              <div className="hotel-card__body">
                <div className="hotel-card__name-row">
                  <span className="hotel-card__name">{hotel.name}</span>
                  <span className="hotel-card__rating">★ {hotel.rating}</span>
                </div>
                <span className="hotel-card__meta">📍 {hotel.region} · {hotel.meta}</span>
                <div className="hotel-card__footer">
                  <span className="hotel-card__price">{won(hotel.price)}</span>
                  <span className="hotel-card__price-unit">/ 박</span>
                  <button type="button" className="card-detail-btn" style={{ marginLeft: 'auto' }} onClick={() => setDetailHotel(hotel)}>
                    상세
                  </button>
                  {isSelected ? (
                    <button
                      type="button"
                      className="flight-card__selected-tag"
                      disabled={locked}
                      title="선택 해제"
                      onClick={() =>
                        // 재클릭=해제 (리듀서가 id+cardKey 일치 시 토글) — 스플릿 숙소 하나만 빼는 것도 가능
                        dispatch({
                          type: 'SELECT_HOTEL',
                          hotel: { ...hotel, cardKey: payload.cardKey || `${cityLabel}:all` },
                        })
                      }
                    >
                      ✓ 선택됨
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="hotel-card__book-btn"
                      disabled={locked}
                      onClick={() =>
                        dispatch({
                          type: 'SELECT_HOTEL',
                          // cardKey: 같은 카드에선 교체, 다른 카드(스플릿 스테이 지역별)면 누적 선택.
                          // 구버전 카드(payload.cardKey 없음)는 cityLabel로 묶어 기존 단일 선택 유지.
                          hotel: { ...hotel, cardKey: payload.cardKey || `${cityLabel}:all` },
                        })
                      }
                    >
                      {locked ? '선택 불가' : '선택'}
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
        {!locked && visibleHotels.length > INITIAL && (
          <button type="button" className="show-more-btn" onClick={() => setShowAll((v) => !v)}>
            {showAll ? '접기 ▴' : `숙소 ${visibleHotels.length - INITIAL}개 더보기 ▾`}
          </button>
        )}
      </div>

      {detailHotel && <HotelDetailModal hotel={detailHotel} city={city} onClose={() => setDetailHotel(null)} />}
    </div>
  )
}

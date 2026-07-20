import { useState } from 'react'
import CardThumb from './CardThumb'
import { BASE_URL } from '../../lib/api'

export default function DestinationCarousel({ items, mapPath, weather, city, selectedIds, dispatch }) {
  const [mapBroken, setMapBroken] = useState(false)
  const mapUrl = mapPath ? `${BASE_URL}${mapPath}` : null
  return (
    <>
      {weather && (
        <div className="dest-weather">
          <span className="dest-weather__emoji">{weather.emoji}</span>
          <span className="dest-weather__temp">{weather.temp}°C</span>
          <span className="dest-weather__desc">{weather.desc}</span>
          <span className="dest-weather__now">현재</span>
        </div>
      )}
      {mapUrl && !mapBroken && (
        <div className="dest-map">
          <img
            src={mapUrl}
            alt={`${city || ''} 명소 지도`}
            className="dest-map__img"
            loading="lazy"
            onError={() => setMapBroken(true)}
          />
          <span className="dest-map__cap">📍 {city ? `${city} 명소 위치` : '명소 위치'}</span>
        </div>
      )}
      <div className="carousel scroll-thin">
      {items.map((item) => {
        const added = selectedIds.includes(item.id)
        return (
          <div key={item.id} className="dest-card">
            <CardThumb
              image={item.image}
              gradient={item.gradient}
              label={`[ ${item.name} 사진 ]`}
              className="dest-card__thumb"
              stripe={8}
            />
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
    </>
  )
}

// 목적지 추천 후보 카드 — 조건에 맞는 여행지 후보 목록. 고르면 해당 도시로 계획 흐름 시작.
export default function DestinationReco({ payload, dispatch }) {
  const items = payload.candidates || []
  return (
    <div className="reco-list">
      {items.map((c, i) => (
        <div key={c.cityEn || c.city || i} className="reco-card">
          <div className="reco-card__head">
            <span className="reco-card__city">{c.city}</span>
            {c.cityEn && <span className="reco-card__en">{c.cityEn}</span>}
          </div>
          <div className="reco-card__chips">
            {c.budget && <span className="reco-chip">💰 {c.budget}</span>}
            {c.weather && <span className="reco-chip reco-chip--wx">🌤 {c.weather}</span>}
          </div>
          {c.reason && <p className="reco-card__reason">{c.reason}</p>}
          {c.highlight && <p className="reco-card__hi">📍 {c.highlight}</p>}
          <button
            type="button"
            className="reco-card__btn"
            onClick={() => dispatch({ type: 'SEND_TEXT', text: `${c.city} 여행 계획 짜줘` })}
          >
            이 도시로 계획하기
          </button>
        </div>
      ))}
    </div>
  )
}

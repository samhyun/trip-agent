function RouteCard({ route, id, active, onSelect }) {
  return (
    <div
      className={`route-plan-card${active ? ' route-plan-card--active' : ''}`}
      onClick={() => onSelect(id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onSelect(id)
      }}
    >
      <div className="route-plan-card__badge-row">
        <span className={`route-plan-card__badge${id === 'B' ? ' route-plan-card__badge--b' : ''}`}>{id}안</span>
        <span style={{ fontSize: 11.5, fontWeight: 700 }}>{route.label}</span>
      </div>
      <div>
        <div className="route-plan-card__step">
          <span>{route.first.icon}</span>
          <div className="route-plan-card__step-meta">
            <span className="route-plan-card__step-title">{route.first.arriveLabel}</span>
            <span className="route-plan-card__step-sub">{route.first.sub}</span>
          </div>
        </div>
        <div className="route-plan-card__transfer">{route.transferLabel}</div>
        <div className="route-plan-card__step">
          <span>{route.second.icon}</span>
          <div className="route-plan-card__step-meta">
            <span className="route-plan-card__step-title">{route.second.arriveLabel}</span>
            <span className="route-plan-card__step-sub">{route.second.sub}</span>
          </div>
        </div>
        <div className="route-plan-card__end">{route.endNote}</div>
      </div>
      <div className={`route-plan-card__highlight${id === 'B' ? ' route-plan-card__highlight--b' : ''}`}>
        {route.highlight}
      </div>
    </div>
  )
}

export default function RoutePlan({ payload, activeRoute, dispatch }) {
  const { routes, compareStrip } = payload
  const select = (id) => dispatch({ type: 'SELECT_ROUTE_PREVIEW', routeId: id })

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div className="route-plans">
        <RouteCard route={routes.A} id="A" active={activeRoute === 'A'} onSelect={select} />
        <RouteCard route={routes.B} id="B" active={activeRoute === 'B'} onSelect={select} />
      </div>

      <div className="compare-strip">
        <div className="compare-strip__col">
          <span className="compare-strip__label">총 이동</span>
          <span className="compare-strip__value">{compareStrip.totalMove}</span>
        </div>
        <div className="compare-strip__col">
          <span className="compare-strip__label">마지막날 공항</span>
          <span className="compare-strip__value">{compareStrip.lastDayAirport}</span>
        </div>
        <div className="compare-strip__col">
          <span className="compare-strip__label">선택</span>
          <span className="compare-strip__value text-primary">{activeRoute}안 선택됨</span>
        </div>
      </div>

      <div className="quick-replies">
        <button type="button" className="pill" onClick={() => select('A')}>
          A안으로
        </button>
        <button type="button" className="pill" onClick={() => select('B')}>
          B안으로
        </button>
      </div>
    </div>
  )
}

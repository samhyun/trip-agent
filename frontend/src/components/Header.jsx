export default function Header({ theme, onToggleTheme }) {
  return (
    <header className="app-header">
      <div className="app-header__logo">✈️</div>
      <div className="app-header__title">
        <strong>Trip Agent</strong>
        <span>여행 플래닝 어시스턴트</span>
      </div>
      <span className="app-header__status">
        <span className="app-header__status-dot" /> 온라인
      </span>
      <button type="button" className="icon-btn" onClick={onToggleTheme} aria-label="테마 전환">
        {theme === 'dark' ? '☀️' : '🌙'}
      </button>
    </header>
  )
}

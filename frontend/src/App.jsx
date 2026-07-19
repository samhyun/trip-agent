import { useEffect, useReducer, useState } from 'react'
import Header from './components/Header'
import ChatColumn from './components/ChatColumn'
import TripSummaryPanel from './components/TripSummaryPanel'
import MobileSummaryBar from './components/MobileSummaryBar'
import { conversationReducer, createInitialState } from './lib/conversationReducer'

function useTheme() {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('trip-agent-theme')
    if (saved) return saved
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })

  useEffect(() => {
    localStorage.setItem('trip-agent-theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  return [theme, toggleTheme]
}

export default function App() {
  const [state, dispatch] = useReducer(conversationReducer, undefined, createInitialState)
  const [theme, toggleTheme] = useTheme()
  const [mobileSummaryOpen, setMobileSummaryOpen] = useState(false)

  // 예약된 자동 진행(생각 중 딜레이)이 있으면 타이머 후 AUTO_ADVANCE를 dispatch
  useEffect(() => {
    if (!state.pendingAdvance) return undefined
    const { token, stage, delay } = state.pendingAdvance
    const timer = setTimeout(() => {
      dispatch({ type: 'AUTO_ADVANCE', token, stage })
    }, delay)
    return () => clearTimeout(timer)
  }, [state.pendingAdvance])

  return (
    <div className="app-shell" data-theme={theme}>
      <Header theme={theme} onToggleTheme={toggleTheme} />
      <MobileSummaryBar
        trip={state.trip}
        stage={state.stage}
        open={mobileSummaryOpen}
        onToggle={() => setMobileSummaryOpen((v) => !v)}
        onProceed={() => dispatch({ type: 'PANEL_PROCEED' })}
      />
      <div className="app-main">
        <ChatColumn state={state} dispatch={dispatch} />
        <TripSummaryPanel trip={state.trip} stage={state.stage} onProceed={() => dispatch({ type: 'PANEL_PROCEED' })} />
      </div>
    </div>
  )
}

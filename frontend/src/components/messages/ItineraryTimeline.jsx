import { useState } from 'react'
import { renderRich } from '../../lib/richText'

// 백엔드 itinerary 는 LLM 이 서술한 자유 텍스트(markdown)라 day/시간 구조로 안정적
// 파싱이 어렵다. 그래서 정합성은 "프론트가 markdown 도 렌더" 하는 쪽으로 맞춘다.
// payload.days(구조화)가 있으면 접이식 타임라인, 없으면 payload.markdown 을 렌더한다.

// 표의 한 줄을 셀 배열로. 이스케이프되지 않은 | 로만 분리하고, \| 는 리터럴 | 로 복원.
function tableCells(line) {
  let s = line.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1) // 이스케이프 아닌 외곽 | 만 제거
  return s.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'))
}

// 표 구분선(|---|:--:|---|)인지 — 셀마다 대시(옵션 콜론)만, 헤더와 열 개수 일치
function isTableSeparator(line, columns) {
  if (!line.includes('|')) return false
  const cells = tableCells(line)
  return cells.length === columns && cells.every((c) => /^:?-{3,}:?$/.test(c))
}

// 새 블록(제목·인용·구분선·목록·빈 줄)의 시작이면 표 행이 아니다
function startsNewBlock(line) {
  const t = line.trim()
  return t === '' || t.startsWith('#') || t.startsWith('>') || /^-{3,}$/.test(t) || /^([-*]|\d+\.)\s+/.test(t)
}

// 가벼운 markdown → 블록 파싱 (제목/리스트/굵게 + 표·인용구·구분선). 외부 의존성 없음.
function parseBlocks(text) {
  const lines = (text || '').split('\n')
  const blocks = []
  let i = 0
  while (i < lines.length) {
    const trimmed = lines[i].trim()

    // 표: 현재 줄에 |, 다음 줄이 (같은 열 개수의) 구분선
    const headerCells = trimmed.includes('|') ? tableCells(trimmed) : null
    if (headerCells && i + 1 < lines.length && isTableSeparator(lines[i + 1], headerCells.length)) {
      i += 2
      const rows = []
      // 다음 블록 시작 전까지, 열 개수가 헤더와 같은 | 줄만 표 행으로
      while (
        i < lines.length &&
        lines[i].includes('|') &&
        !startsNewBlock(lines[i]) &&
        tableCells(lines[i]).length === headerCells.length &&
        // 이 줄이 새 표의 헤더(다음 줄이 구분선)면 중단 — 연속 표 흡수 방지
        !(i + 1 < lines.length && isTableSeparator(lines[i + 1], tableCells(lines[i]).length))
      ) {
        rows.push(tableCells(lines[i]))
        i += 1
      }
      blocks.push({ kind: 'table', header: headerCells, rows })
      continue
    }
    // 인용구: > 로 시작하는 연속 줄
    if (trimmed.startsWith('>')) {
      const quote = []
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        quote.push(lines[i].trim().replace(/^>\s?/, ''))
        i += 1
      }
      blocks.push({ kind: 'quote', lines: quote })
      continue
    }
    if (/^-{3,}$/.test(trimmed)) { blocks.push({ kind: 'hr' }); i += 1; continue }
    if (!trimmed) { blocks.push({ kind: 'gap' }); i += 1; continue }
    const heading = trimmed.match(/^#{1,6}\s+(.*)$/)
    if (heading) { blocks.push({ kind: 'heading', text: heading[1] }); i += 1; continue }
    const bullet = trimmed.match(/^([-*]|\d+\.)\s+(.*)$/)
    if (bullet) { blocks.push({ kind: 'bullet', text: bullet[2] }); i += 1; continue }
    blocks.push({ kind: 'line', text: trimmed })
    i += 1
  }
  return blocks
}

function ItineraryMarkdown({ text }) {
  const blocks = parseBlocks(text)
  return (
    <div className="card card-lg fade-up itinerary-md">
      {blocks.map((b, i) => {
        if (b.kind === 'table') {
          return (
            <div key={i} className="itinerary-md__table-wrap scroll-thin">
              <table className="itinerary-md__table">
                <thead>
                  <tr>{b.header.map((c, k) => <th key={k}>{renderRich(c)}</th>)}</tr>
                </thead>
                <tbody>
                  {b.rows.map((r, ri) => (
                    <tr key={ri}>{r.map((c, k) => <td key={k}>{renderRich(c)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
        if (b.kind === 'quote') {
          return (
            <blockquote key={i} className="itinerary-md__quote">
              {b.lines.map((l, k) => <div key={k}>{renderRich(l)}</div>)}
            </blockquote>
          )
        }
        if (b.kind === 'hr') return <hr key={i} className="itinerary-md__hr" />
        if (b.kind === 'gap') return <div key={i} className="itinerary-md__gap" />
        if (b.kind === 'heading') return <div key={i} className="itinerary-md__heading">{renderRich(b.text)}</div>
        if (b.kind === 'bullet') {
          return (
            <div key={i} className="itinerary-md__item">
              <span className="itinerary-md__dot">•</span>
              <span>{renderRich(b.text)}</span>
            </div>
          )
        }
        return <div key={i} className="itinerary-md__line">{renderRich(b.text)}</div>
      })}
    </div>
  )
}

function ItineraryDays({ days }) {
  const [openDay, setOpenDay] = useState(days[0]?.day)

  return (
    <div className="fade-up" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {days.map((day) => {
        const isOpen = openDay === day.day
        return (
          <div key={day.day} className="itinerary-day">
            <button
              type="button"
              className="itinerary-day__toggle"
              onClick={() => setOpenDay(isOpen ? null : day.day)}
            >
              <span className="itinerary-day__badge">DAY {day.day}</span>
              <span className="itinerary-day__title">{day.title}</span>
              <span className="itinerary-day__date">{day.dateLabel}</span>
              <span className="itinerary-day__chevron">{isOpen ? '▾' : '▸'}</span>
            </button>
            {isOpen && (
              <div className="itinerary-day__items">
                {day.items.map((item) => (
                  <div key={item.time + item.text} className="itinerary-item">
                    <span className="itinerary-item__time">{item.time}</span>
                    <span className={`itinerary-item__dot${item.accent ? ' itinerary-item__dot--accent' : ''}`} />
                    <span className="itinerary-item__text">{item.text}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function ItineraryTimeline({ payload = {} }) {
  const { days, markdown } = payload
  if (Array.isArray(days) && days.length > 0) {
    return <ItineraryDays days={days} />
  }
  return <ItineraryMarkdown text={markdown || ''} />
}

// 경량 리치텍스트 렌더러 (외부 의존성 없음). 챗 버블·일정 등에 공용.
// 인라인: **굵게**, [텍스트](url), 맨 URL 링크.  블록: 제목/불릿/번호/문단/줄바꿈.

const INLINE_RE = /(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)|https?:\/\/[^\s)]+)/g

// http/https만 링크로 허용 (javascript:·data: 등 위험 스킴 차단).
function safeUrl(url) {
  return /^https?:\/\//i.test(url) ? url : null
}

function Link({ href, children }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="rich-link">
      {children}
    </a>
  )
}

// 인라인 서식 (굵게·링크)만 처리. 한 줄 텍스트용.
export function renderRich(text) {
  const parts = String(text ?? '').split(INLINE_RE)
  return parts.map((part, i) => {
    if (!part) return null
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (link) {
      const url = safeUrl(link[2].trim())
      return url ? <Link key={i} href={url}>{link[1]}</Link> : <span key={i}>{part}</span>
    }
    if (/^https?:\/\//.test(part)) {
      // 맨 URL 끝의 문장부호(.,!?;:)는 링크에서 제외
      const m = part.match(/^(https?:\/\/[^\s)]*?)([.,!?;:]*)$/)
      const url = m ? m[1] : part
      const trail = m ? m[2] : ''
      return (
        <span key={i}>
          <Link href={url}>{url}</Link>
          {trail}
        </span>
      )
    }
    return <span key={i}>{part}</span>
  })
}

// 블록 단위 마크다운 렌더 (제목·불릿·번호목록·문단·빈줄). 챗 버블 가독성용.
export function renderMarkdown(text) {
  const lines = String(text ?? '').split('\n')
  return (
    <div className="chat-md">
      {lines.map((line, i) => {
        const t = line.trim()
        if (!t) return <div key={i} className="chat-md__gap" />
        const heading = t.match(/^#{1,6}\s+(.*)$/)
        if (heading) {
          return (
            <div key={i} className="chat-md__h">
              {renderRich(heading[1])}
            </div>
          )
        }
        const numbered = t.match(/^(\d+)[.)]\s+(.*)$/)
        if (numbered) {
          return (
            <div key={i} className="chat-md__item">
              <span className="chat-md__num">{numbered[1]}.</span>
              <span>{renderRich(numbered[2])}</span>
            </div>
          )
        }
        const bullet = t.match(/^[-*•]\s+(.*)$/)
        if (bullet) {
          return (
            <div key={i} className="chat-md__item">
              <span className="chat-md__dot">•</span>
              <span>{renderRich(bullet[1])}</span>
            </div>
          )
        }
        return (
          <div key={i} className="chat-md__p">
            {renderRich(t)}
          </div>
        )
      })}
    </div>
  )
}

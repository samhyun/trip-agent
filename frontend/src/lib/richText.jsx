// "**굵게**" 마크다운 스타일 굵게 표시만 지원하는 경량 렌더러 (챗 버블 텍스트용)
export function renderRich(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    return <span key={i}>{part}</span>
  })
}

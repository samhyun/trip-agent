import { renderMarkdown } from '../../lib/richText'

// 봇 텍스트 버블 — 마크다운(제목/목록/굵게/링크/문단)으로 렌더해 가독성 확보.
export default function TextBubble({ text }) {
  return <div className="bubble bubble-bot">{renderMarkdown(text)}</div>
}

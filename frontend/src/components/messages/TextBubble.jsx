import { renderRich } from '../../lib/richText'

export default function TextBubble({ text }) {
  return <div className="bubble bubble-bot">{renderRich(text)}</div>
}

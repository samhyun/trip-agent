export default function AgentStatus({ agent, text }) {
  return (
    <div className="agent-status fade-up">
      <span className="agent-status__dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="agent-status__label">{agent}</span> {text}
    </div>
  )
}

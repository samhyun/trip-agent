import MessageList from './MessageList'
import Composer from './Composer'

export default function ChatColumn({ state, dispatch }) {
  return (
    <div className="chat-column">
      <MessageList messages={state.messages} trip={state.trip} stage={state.stage} dispatch={dispatch} />
      <Composer stage={state.stage} dispatch={dispatch} loading={state.loading} />
    </div>
  )
}

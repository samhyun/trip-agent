import TextBubble from './messages/TextBubble'
import AgentStatus from './messages/AgentStatus'
import QuickReplies from './messages/QuickReplies'
import InlineForm from './messages/InlineForm'
import DestinationCarousel from './messages/DestinationCarousel'
import DestinationReco from './messages/DestinationReco'
import FlightResults from './messages/FlightResults'
import HotelResults from './messages/HotelResults'
import RoutePlan from './messages/RoutePlan'
import ItineraryTimeline from './messages/ItineraryTimeline'
import BookingSummary from './messages/BookingSummary'
import PaymentCard from './messages/PaymentCard'
import ConfirmationCard from './messages/ConfirmationCard'

export default function MessageRenderer({ message, trip, stage, dispatch }) {
  const { type, role, payload } = message

  if (role === 'user') {
    return (
      <div className="msg-row msg-row--user fade-up">
        <div className="bubble-user">{payload.text}</div>
      </div>
    )
  }

  if (type === 'agent_status') {
    return <AgentStatus agent={payload.agent} text={payload.text} />
  }

  if (type === 'text') {
    return (
      <div className="msg-row fade-up">
        <div className="msg-avatar">🤖</div>
        <TextBubble text={payload.text} />
      </div>
    )
  }

  return (
    <div className="msg-row msg-row--wide fade-up">
      <div className="msg-avatar">🤖</div>
      <div className="msg-body">
        {type === 'quick_replies' && <QuickReplies message={message} dispatch={dispatch} />}

        {type === 'inline_form' && <InlineForm message={message} dispatch={dispatch} />}

        {type === 'destination_reco' && <DestinationReco payload={payload} dispatch={dispatch} />}

        {type === 'destination_carousel' && (
          <DestinationCarousel
            items={payload.items}
            mapPath={payload.mapPath}
            weather={payload.weather}
            city={payload.city}
            selectedIds={trip.spots.map((s) => s.id)}
            dispatch={dispatch}
          />
        )}

        {type === 'flight_results' && (
          <FlightResults payload={payload} selectedFlight={trip.flight} dispatch={dispatch} />
        )}

        {type === 'hotel_results' && (
          <HotelResults
            payload={payload}
            selectedHotel={trip.hotels.find((h) => (payload.hotels || []).some((ph) => ph.id === h.id)) || null}
            dispatch={dispatch}
          />
        )}

        {type === 'route_plan' && (
          <RoutePlan payload={payload} activeRoute={trip.routePlan} dispatch={dispatch} />
        )}

        {type === 'itinerary' && <ItineraryTimeline payload={payload} />}

        {type === 'booking_summary' && <BookingSummary rows={payload.rows} total={payload.total} />}

        {type === 'payment' && <PaymentCard total={payload.total} dispatch={dispatch} stage={stage} />}

        {type === 'confirmation' && <ConfirmationCard payload={payload} />}
      </div>
    </div>
  )
}

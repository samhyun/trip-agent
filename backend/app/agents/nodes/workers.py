"""워커 노드 (destination · itinerary · booking · payment).

각 워커는 travel_service로 데이터를 조회해 프론트 렌더용 구조화 응답(card_type/payload)을
만든다. itinerary는 LLM으로 일정을 서술한다. 카드 데이터는 AIMessage.additional_kwargs 의
card_type/payload 로 전달돼 응답 turns 에 담긴다.
"""

from langchain_core.messages import AIMessage
from langgraph.types import Command

from app.agents.llm import get_llm
from app.agents.state import State
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services import travel_service as ts

logger = get_logger(__name__)


def _all_text(messages) -> str:
    """대화 전체 텍스트 (목적지 추출용)."""
    return " ".join(m.content for m in messages if isinstance(getattr(m, "content", None), str))


def _card(content: str, name: str, card_type: str, payload: dict, visited: list) -> Command:
    """구조화 카드 1개를 담아 supervisor로 돌아가는 Command."""
    return Command(
        update={
            "messages": [
                AIMessage(
                    content=content,
                    name=name,
                    additional_kwargs={"card_type": card_type, "payload": payload},
                )
            ],
            "visited": visited + [name],
        },
        goto="supervisor",
    )


def destination_node(state: State) -> Command:
    """여행지 명소를 카드(destination_carousel)로."""
    visited = state.get("visited", [])
    cities = ts.find_cities(_all_text(state["messages"]))
    if not cities:
        return _card("여행지를 파악하지 못했어요. 도시를 알려주세요.", "destination", "text", {}, visited)
    city = cities[0]
    attractions = ts.get_attractions(city)
    payload = {
        "city": city,
        "items": [
            {"name": a["name"], "area": a.get("area"), "tags": a.get("tags", []), "desc": a.get("desc", "")}
            for a in attractions
        ],
    }
    logger.info("destination[%s] 명소 %d개", city, len(attractions))
    return _card(f"{city} 인기 명소를 골라봤어요 👇", "destination", "destination_carousel", payload, visited)


def itinerary_node(state: State) -> Command:
    """일자별 일정을 LLM으로 서술 (itinerary 카드)."""
    visited = state.get("visited", [])
    if not get_settings().llm_enabled:
        return _card("📅 Day1 주요 명소 / Day2 근교 코스 (mock)", "itinerary", "itinerary", {}, visited)
    system = (
        "너는 일정·동선 설계 전담이야. 예약·결제 얘기는 하지 말고, 대화에 나온 목적지·기간·명소로 "
        "Day별 일정표를 간결히 작성해. 여러 도시를 방문하면 방문 순서와 이동 동선도 제안해. 한국어로."
    )
    response = get_llm("itinerary").invoke([{"role": "system", "content": system}, *state["messages"]])
    return _card(response.content, "itinerary", "itinerary", {"markdown": response.content}, visited)


def booking_node(state: State) -> Command:
    """항공·숙소 검색 결과를 각각 카드(flight_results / hotel_results)로."""
    visited = state.get("visited", [])
    cities = ts.find_cities(_all_text(state["messages"]))
    if not cities:
        return Command(
            update={
                "messages": [AIMessage(content="여행지를 파악하지 못해 검색을 진행하지 못했어요.", name="booking")],
                "visited": visited + ["booking"],
            },
            goto="supervisor",
        )
    city = cities[0]
    flights = ts.search_flights(city)
    hotels = ts.search_hotels(city)

    messages = []
    if flights:
        messages.append(
            AIMessage(
                content=f"{flights['route_key']} 날짜별 가격이에요",
                name="booking",
                additional_kwargs={
                    "card_type": "flight_results",
                    "payload": {
                        "route": flights["route_key"],
                        "duration": flights.get("duration"),
                        "date_prices": flights["date_prices"],
                    },
                },
            )
        )
    if hotels:
        messages.append(
            AIMessage(
                content=f"{city} 숙소 옵션이에요",
                name="booking",
                additional_kwargs={"card_type": "hotel_results", "payload": {"city": city, "hotels": hotels}},
            )
        )
    if not messages:
        messages.append(AIMessage(content="항공·숙소를 찾지 못했어요.", name="booking"))
    logger.info("booking[%s] 항공=%s 숙소=%d", city, bool(flights), len(hotels))
    return Command(update={"messages": messages, "visited": visited + ["booking"]}, goto="supervisor")


def payment_node(state: State) -> Command:
    """더미 결제 확정서 카드(confirmation)."""
    visited = state.get("visited", [])
    confirmation = ts.make_confirmation()
    payload = {"confirmation_no": confirmation, "method": "dummy", "status": "paid"}
    return _card(f"💳 결제 완료! 확정번호 {confirmation}", "payment", "confirmation", payload, visited)

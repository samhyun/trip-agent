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
    """대화 전체 텍스트."""
    return " ".join(m.content for m in messages if isinstance(getattr(m, "content", None), str))


def _user_text(messages) -> str:
    """사용자 발화만 이어붙인다 (목적지 추출용).

    봇 메시지의 예시(예: '출발 공항은? 인천·부산 등')가 목적지로 오인되는 것을 막는다.
    """
    return " ".join(
        m.content
        for m in messages
        if getattr(m, "type", None) == "human" and isinstance(getattr(m, "content", None), str)
    )


_NEGATION_MARKERS = ("말고", "말구", "대신", "아니라", "보다는")


def _resolve_cities(messages) -> list[str]:
    """최신 사용자 발화부터 거슬러 올라가며 지원 도시를 찾는다.

    '제주 말고 부산'처럼 정정하면 부정어(말고·대신 등) 뒤의 도시를 우선한다. 없으면 [].
    """
    for m in reversed(messages):
        if getattr(m, "type", None) == "human" and isinstance(getattr(m, "content", None), str):
            text = m.content
            cities = ts.find_cities(text)
            if not cities:
                continue
            for marker in _NEGATION_MARKERS:
                if marker in text:
                    after = ts.find_cities(text.split(marker, 1)[1])
                    if after:
                        return after  # 부정어 뒤 도시가 실제 의도
            return cities
    return []


# 도시를 못 잡았을 때 안내 (지원 목적지 명시)
_NO_CITY_MSG = "여행지를 파악하지 못했어요. 현재는 제주·부산·세부·보홀을 도와드릴 수 있어요."


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
    cities = _resolve_cities(state["messages"])
    if not cities:
        return _card(_NO_CITY_MSG, "destination", "text", {}, visited)
    city = cities[0]
    attractions = ts.get_attractions(city)
    payload = ts.build_destination_payload(city, attractions)
    logger.info("destination[%s] 명소 %d개", city, len(attractions))
    return _card(f"{city} 인기 명소를 골라봤어요 👇", "destination", "destination_carousel", payload, visited)


def itinerary_node(state: State) -> Command:
    """일자별 일정을 LLM으로 서술 (itinerary 카드)."""
    visited = state.get("visited", [])
    if not get_settings().llm_enabled:
        mock = "### Day 1\n- 주요 명소 관광\n\n### Day 2\n- 근교 코스 (mock)"
        return _card(mock, "itinerary", "itinerary", {"markdown": mock}, visited)
    system = (
        "너는 일정·동선 설계 전담이야. 예약·결제 얘기는 하지 말고, 대화에 나온 목적지·기간·명소로 "
        "Day별 일정표를 간결히 작성해. 여러 도시를 방문하면 방문 순서와 이동 동선도 제안해. 한국어로."
    )
    response = get_llm("itinerary").invoke([{"role": "system", "content": system}, *state["messages"]])
    return _card(response.content, "itinerary", "itinerary", {"markdown": response.content}, visited)


def booking_node(state: State) -> Command:
    """항공·숙소 검색 결과를 각각 카드(flight_results / hotel_results)로."""
    visited = state.get("visited", [])
    cities = _resolve_cities(state["messages"])
    if not cities:
        return Command(
            update={
                "messages": [AIMessage(content=_NO_CITY_MSG, name="booking")],
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
                content=f"{flights.get('route', flights['route_key'])} 날짜별 최저가예요. 원하는 날짜를 골라주세요 ✈️",
                name="booking",
                additional_kwargs={
                    "card_type": "flight_results",
                    "payload": ts.build_flight_payload(flights),
                },
            )
        )
    if hotels:
        messages.append(
            AIMessage(
                content=f"{city} 숙소 옵션이에요. 마음에 드는 곳을 예약해 주세요 🏨",
                name="booking",
                additional_kwargs={
                    "card_type": "hotel_results",
                    "payload": ts.build_hotel_payload(city, hotels),
                },
            )
        )
    if not messages:
        messages.append(AIMessage(content="항공·숙소를 찾지 못했어요.", name="booking"))
    logger.info("booking[%s] 항공=%s 숙소=%d", city, bool(flights), len(hotels))
    return Command(update={"messages": messages, "visited": visited + ["booking"]}, goto="supervisor")


def payment_node(state: State) -> Command:
    """더미 결제 확정서 카드(confirmation) — 프론트 ConfirmationCard 계약."""
    visited = state.get("visited", [])
    text = _user_text(state["messages"])  # 인원·박수 파싱용 (사용자 발화만)
    cities = _resolve_cities(state["messages"])
    travelers = ts.parse_people(text)  # 대화에서 추출, 없으면 2
    nights = ts.parse_nights(text)  # 대화에서 추출, 없으면 3
    code = ts.make_confirmation()
    title = (" + ".join(cities) if cities else "여행") + " 예약"
    payload = {
        "code": code,
        "title": title,
        "dateLabel": "",  # 백엔드는 선택 날짜를 추적하지 않음 → 프론트가 로컬 선택값으로 덮어씀
        # 개략 합계(인원·박수·최저가 반영) → 프론트가 실제 선택 합계로 덮어씀
        # NOTE(보류): 무상태 구조라 서버측 선택 검증은 데모 스코프 밖. 프론트 선택값이 최종.
        "total": ts.estimate_total(cities, travelers, nights),
        "method": "dummy",
        "status": "paid",
    }
    return _card(f"💳 결제 완료! 확정번호 {code}", "payment", "confirmation", payload, visited)

"""워커 노드 (destination · itinerary · booking · payment).

각 워커는 travel_service로 데이터를 조회해 프론트 렌더용 구조화 응답(card_type/payload)을
만든다. itinerary는 LLM으로 일정을 서술한다. 카드 데이터는 AIMessage.additional_kwargs 의
card_type/payload 로 전달돼 응답 turns 에 담긴다.
"""

from langchain_core.messages import AIMessage
from langgraph.types import Command
from typing_extensions import TypedDict

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


# 도시를 못 잡았을 때 안내 (지원 목적지 명시)
_NO_CITY_MSG = "여행지를 파악하지 못했어요. 현재는 제주·부산·세부·보홀을 도와드릴 수 있어요."


def _scan_user_cities(messages) -> list[str]:
    """폴백/교차검증: 최신 사용자 발화부터 지원 도시를 스캔(LLM 미설정·오추출 대비)."""
    for m in reversed(messages):
        if getattr(m, "type", None) == "human" and isinstance(getattr(m, "content", None), str):
            cities = ts.find_cities(m.content)
            if cities:
                return cities
    return []


def _resolve_destination(state) -> tuple[list[str], str]:
    """(지원 도시 목록, 원시 목적지명).

    coordinator가 LLM으로 추출한 `trip.destination`을 우선한다(자연어·정정·오타 처리). 지원 도시로
    매칭되면 사용하고, 매칭 안 되면 해외 임의 도시로 자동 해석(영문명으로 좌표·공항 조회)을 시도한다.
    자동 해석도 안 되면 사용자 발화를 교차검증(LLM 오추출 대비), 그래도 없으면 미지원.
    LLM이 목적지를 못 냈으면(mock 등) 사용자 발화 스캔으로 폴백. raw는 미지원이어도 안내에 쓴다.
    """
    scan = _scan_user_cities(state["messages"])
    trip = state.get("trip") or {}
    dest = trip.get("destination", "").strip()
    if dest:
        cities = ts.find_cities(dest)
        if cities:
            return cities, dest
        # 큐레이션 도시가 아니면 영문명으로 실시간 해석 시도(랑카위·다낭 등)
        if ts.resolve_place(dest, trip.get("destination_en", "")):
            return [dest], dest
        if scan:  # 자동 해석도 실패 → 발화 교차검증 우선
            return scan, ""
        return [], dest  # 정말 미지원 → raw로 안내
    return (scan, "") if scan else ([], "")


def _resolve_destinations(state) -> list[str]:
    """방문할 모든 지원 도시(멀티 목적지). destinations 우선, 없으면 단일 destination로 폴백.

    각 도시를 지원 도시로 매칭하거나 해외 임의 도시로 자동 해석해 등록한다. 순서·중복 제거.
    """
    trip = state.get("trip") or {}
    dests = list(trip.get("destinations") or [])
    dests_en = list(trip.get("destinations_en") or [])
    if not dests:  # 멀티 목적지 목록이 없으면 단일 목적지로 폴백
        single = trip.get("destination", "").strip()
        if single:
            dests = [single]
            dests_en = [trip.get("destination_en", "")]
    out: list[str] = []
    seen: set = set()
    for i, raw in enumerate(dests):
        d = (raw or "").strip()
        if not d:
            continue
        cities = ts.find_cities(d)
        if not cities:  # 지원 도시 아님 → 해외 임의 도시 자동 해석 시도
            en = dests_en[i] if i < len(dests_en) else ""
            cities = [d] if ts.resolve_place(d, en) else []
        for c in cities:
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


def _pos_int(value, fallback: int, hi: int) -> int:
    """구조화 출력값을 1~hi 범위 정수로 검증(음수·문자열·과대값 방어). 아니면 fallback."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return fallback
    return n if 1 <= n <= hi else fallback


def _unsupported_msg(raw: str) -> str:
    """미지원/미파악 목적지 안내. raw가 있으면 그 도시명을 짚어준다."""
    if raw:
        return f"'{raw}'는 아직 지원하지 않는 여행지예요. 현재는 제주·부산·세부·보홀을 도와드릴 수 있어요."
    return _NO_CITY_MSG


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
    cities, raw = _resolve_destination(state)
    if not cities:
        return _card(_unsupported_msg(raw), "destination", "text", {}, visited)
    city = cities[0]
    attractions = ts.get_attractions(city)
    payload = ts.build_destination_payload(city, attractions)
    logger.info("destination[%s] 명소 %d개", city, len(attractions))
    return _card(f"{city} 인기 명소를 골라봤어요 👇", "destination", "destination_carousel", payload, visited)


class _RouteStep(TypedDict):
    icon: str  # 이모지 1개
    arriveLabel: str  # 예: "세부 도착 · 2박"
    sub: str  # 주요 활동, 예: "시티투어 · 다이빙"


class _RouteOption(TypedDict):
    label: str  # 예: "세부 먼저"
    first: _RouteStep
    transferLabel: str  # 두 도시 간 이동, 예: "🚤 페리 2시간 · 세부→보홀"
    second: _RouteStep
    endNote: str  # 마지막 도시 출국, 예: "✈️ 보홀에서 출국"
    highlight: str  # 이 안의 장점 한 줄


class _RoutePlanLLM(TypedDict):
    A: _RouteOption  # 첫 도시 먼저
    B: _RouteOption  # 둘째 도시 먼저
    totalMove: str  # 예: "항공 2 · 페리 1"
    lastDayAirport: str  # 예: "A 보홀 / B 세부"


ROUTE_SYSTEM = """너는 멀티 도시 여행의 방문 순서·이동 동선을 설계하는 전문가야.
두 도시를 방문하는 여행에 대해, 방문 순서가 다른 두 안(A/B)을 비교 제시해라.
- A안: 첫째 도시를 먼저, B안: 둘째 도시를 먼저 방문.
- 각 안의 first/second는 {icon(이모지 1개), arriveLabel(예: "세부 도착 · 2박"), sub(주요 활동 2개, 예: "시티투어 · 다이빙")}.
- transferLabel: 두 도시 간 실제 지리에 맞는 이동수단·소요(가까운 섬↔섬=페리, 먼 도시=국내선/기차/버스). 예: "🚤 페리 2시간 · 세부→보홀".
- endNote: 마지막 도시에서 출국(예: "✈️ 보홀에서 출국"). label은 예: "세부 먼저". highlight는 그 안의 장점 한 줄.
- 총 숙박 박수를 두 도시에 적절히 배분해 arriveLabel에 "N박"을 표기해.
- compareStrip용 totalMove(예: "항공 2 · 페리 1")와 lastDayAirport(예: "A 보홀 / B 세부")도 채워라.
- 모든 텍스트는 한국어, 이모지는 각 1개."""


def _route_payload(plan: _RoutePlanLLM) -> dict:
    """LLM 동선 출력 → 프론트 RoutePlan 계약 {routes:{A,B}, compareStrip}."""
    return {
        "routes": {"A": plan["A"], "B": plan["B"]},
        "compareStrip": {
            "totalMove": plan.get("totalMove", ""),
            "lastDayAirport": plan.get("lastDayAirport", ""),
        },
    }


def _mock_route(c1: str, c2: str, nights: int = 0) -> dict:
    """LLM 미설정 시 결정적 동선 카드(도시명·박수 반영). 총 박수를 두 도시에 배분(합=총박수)."""
    if not nights:  # 미지정 → 데모 기본(각 2박)
        n1, n2 = 2, 2
    else:  # 합이 총 박수와 일치하도록 배분(1박이면 1+0=당일치기)
        n1 = max(1, nights // 2)
        n2 = nights - n1

    def stay(city: str, n: int) -> str:
        return f"{city} 도착 · {n}박" if n > 0 else f"{city} 당일"

    def opt(a: str, na: int, b: str, nb: int) -> dict:
        return {
            "label": f"{a} 먼저",
            "first": {"icon": "✈️", "arriveLabel": stay(a, na), "sub": "도시 관광"},
            "transferLabel": f"🚗 {a} → {b} 이동",
            "second": {"icon": "🏝", "arriveLabel": stay(b, nb), "sub": "자연·휴양"},
            "endNote": f"✈️ {b}에서 출국",
            "highlight": "순환 동선",
        }
    return {
        "routes": {"A": opt(c1, n1, c2, n2), "B": opt(c2, n1, c1, n2)},
        "compareStrip": {"totalMove": "항공 2", "lastDayAirport": f"A {c2} / B {c1}"},
    }


def route_node(state: State) -> Command:
    """여러 도시 방문 시 방문 순서·이동 동선을 A/B안으로 비교(route_plan 카드).

    도시가 하나뿐이면 비교가 불필요하므로 카드 없이 조용히 통과한다.
    """
    visited = state.get("visited", [])
    cities = _resolve_destinations(state)
    if len(cities) < 2:  # 단일 도시 → 동선 비교 불필요
        return Command(update={"visited": visited + ["route"]}, goto="supervisor")
    c1, c2 = cities[0], cities[1]
    nights = _pos_int((state.get("trip") or {}).get("nights"), 0, 60)

    if not get_settings().llm_enabled:
        payload = _mock_route(c1, c2, nights)
    else:
        prompt = f"두 도시: {c1}, {c2}. 총 숙박 {nights or ''}박. A안은 {c1} 먼저, B안은 {c2} 먼저 방문."
        try:
            plan = get_llm("route").with_structured_output(_RoutePlanLLM).invoke(
                [{"role": "system", "content": ROUTE_SYSTEM}, {"role": "user", "content": prompt}]
            )
            payload = _route_payload(plan)
        except Exception as exc:  # noqa: BLE001 - 구조화 실패 시 mock 폴백
            logger.warning("route 동선 생성 실패: %s", exc)
            payload = _mock_route(c1, c2, nights)

    # UI는 두 도시 A/B 비교라, 3곳 이상이면 앞의 두 도시 기준임을 안내(나머지 누락 방지)
    extra = cities[2:]
    note = f" 나머지({', '.join(extra)})는 이어지는 일정에서 함께 다룰게요." if extra else ""
    logger.info("route[%s+%s] 동선 A/B 생성 (외 %d곳)", c1, c2, len(extra))
    content = f"{c1} + {c2}, 두 도시 방문 순서를 A안·B안으로 비교해봤어요 🗺️{note} 마음에 드는 동선을 골라주세요."
    return _card(content, "route", "route_plan", payload, visited)


def itinerary_node(state: State) -> Command:
    """일자별 일정을 LLM으로 서술 (itinerary 카드)."""
    visited = state.get("visited", [])
    if not get_settings().llm_enabled:
        mock = "### Day 1\n- 주요 명소 관광\n\n### Day 2\n- 근교 코스 (mock)"
        return _card(mock, "itinerary", "itinerary", {"markdown": mock}, visited)
    system = (
        "너는 여행 일정·동선 설계 전문가야. 대화의 목적지와 기간(며칠/몇 박)을 파악해 Day별 일정표를 짜라. "
        "사용자가 고른 명소가 대화에 있으면 반영하고, 없으면 그 목적지의 인기 명소로 채워라. "
        "여러 도시를 방문하면 방문 순서와 이동 동선도 넣어라.\n"
        "반드시 일정표만 출력한다. 인사말·자기소개·거절·되묻기·예약/결제 언급은 하지 말고, "
        "'### Day 1', '### Day 2' 형식으로 각 날의 오전·오후·저녁 활동과 이동을 간결히 적어라. 한국어로."
    )
    response = get_llm("itinerary").invoke([{"role": "system", "content": system}, *state["messages"]])
    return _card(response.content, "itinerary", "itinerary", {"markdown": response.content}, visited)


def booking_node(state: State) -> Command:
    """항공·숙소 검색 결과를 각각 카드(flight_results / hotel_results)로."""
    visited = state.get("visited", [])
    cities, raw = _resolve_destination(state)
    if not cities:
        return Command(
            update={
                "messages": [AIMessage(content=_unsupported_msg(raw), name="booking")],
                "visited": visited + ["booking"],
            },
            goto="supervisor",
        )
    city = cities[0]
    sort = (state.get("trip") or {}).get("sort")  # 'price' | 'rating' | None
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
        note = "가격 낮은순으로 정렬했어요." if sort == "price" else "마음에 드는 곳을 예약해 주세요."
        messages.append(
            AIMessage(
                content=f"{city} 숙소 옵션이에요. {note} 🏨",
                name="booking",
                additional_kwargs={
                    "card_type": "hotel_results",
                    "payload": ts.build_hotel_payload(city, hotels, sort=sort),
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
    trip = state.get("trip") or {}
    text = _user_text(state["messages"])  # 파싱 폴백용 (사용자 발화만)
    cities, _ = _resolve_destination(state)
    # LLM 추출 슬롯은 범위 검증 후 사용, 아니면 발화 파싱으로 폴백
    travelers = _pos_int(trip.get("travelers"), ts.parse_people(text), 30)
    nights = _pos_int(trip.get("nights"), ts.parse_nights(text), 60)
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

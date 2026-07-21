"""워커 노드 (destination · itinerary · booking · payment).

각 워커는 travel_service로 데이터를 조회해 프론트 렌더용 구조화 응답(card_type/payload)을
만든다. itinerary는 LLM으로 일정을 서술한다. 카드 데이터는 AIMessage.additional_kwargs 의
card_type/payload 로 전달돼 응답 turns 에 담긴다.
"""

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.types import Command
from typing_extensions import TypedDict

from app.agents.llm import get_llm
from app.agents.prompts import render
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


@tool
def get_attractions(interest: str = "") -> str:
    """목적지의 인기 명소를 조회한다.

    - interest: 특정 취향으로 좁히고 싶을 때(예: '자연', '바다', '역사', '쇼핑', '맛집'). 없으면 ''(전체)
    """
    return ""  # 실제 실행은 destination_node 가 처리


_DESTINATION_TOOLS = [get_attractions]


def _filter_attractions(attractions: list[dict], interest: str, city: str) -> tuple[list[dict], str]:
    """관심사(태그) 필터. 딱 맞는 태그가 없으면 전체 유지 + 노트(빈 카드 방지 — booking과 동일 원칙)."""
    key = interest.strip() if isinstance(interest, str) else ""  # 비문자열·공백 방어
    if not key:
        return attractions, ""

    def _match(a: dict) -> bool:
        tags = a.get("tags")
        if not isinstance(tags, (list, tuple)):  # tags가 None·비반복형이어도 안전
            return False
        return any(isinstance(t, str) and (key in t or t in key) for t in tags)

    hit = [a for a in attractions if _match(a)]
    if hit:
        return hit, ""
    return attractions, f"'{key}' 취향에 딱 맞는 태그는 없어 {city} 대표 명소를 보여줌"


def _destination_interest(state: State) -> str:
    """에이전트가 사용자 취향을 보고 명소 조회 관심사를 결정(get_attractions 툴콜). 항상 정규화된 문자열."""
    try:
        ai = get_llm("destination").bind_tools(_DESTINATION_TOOLS).invoke(
            [{"role": "system", "content": render("destination")}, *state["messages"]]
        )
        for tc in getattr(ai, "tool_calls", None) or []:
            if tc.get("name") == "get_attractions":
                val = (tc.get("args") or {}).get("interest", "")
                return val.strip() if isinstance(val, str) else ""
    except Exception as exc:  # noqa: BLE001 - 툴콜 미지원 등 → 관심사 없이 전체
        logger.warning("destination 에이전트 툴 호출 실패: %s", exc)
    return ""


def destination_node(state: State) -> Command:
    """여행지 에이전트: LLM이 사용자 취향을 보고 get_attractions(interest)를 호출하면,
    실제 조회·필터를 적용해 명소 카드(destination_carousel)로 후처리한다.
    """
    visited = state.get("visited", [])
    cities, raw = _resolve_destination(state)
    if not cities:
        return _card(_unsupported_msg(raw), "destination", "text", {}, visited)
    city = cities[0]
    attractions = ts.get_attractions(city)
    if not attractions:
        return _card(f"{city} 명소 정보를 찾지 못했어요.", "destination", "text", {}, visited)

    interest = _destination_interest(state) if get_settings().llm_enabled else ""
    picked, note = _filter_attractions(attractions, interest, city)
    payload = ts.build_destination_payload(city, picked)
    if note:
        caption = f"{note} 👇"
    elif interest:
        caption = f"{city} '{interest}' 명소를 골라봤어요 👇"
    else:
        caption = f"{city} 인기 명소를 골라봤어요 👇"
    logger.info("destination[%s] interest=%r 명소=%d", city, interest, len(picked))
    return _card(caption, "destination", "destination_carousel", payload, visited)


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
                [{"role": "system", "content": render("route")}, {"role": "user", "content": prompt}]
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


def _with_booking_cta(content: str, state: State) -> str:
    """예약 단계가 계획에 없으면 일정 끝에 예약 안내를 붙인다(예약으로 이어가기 쉽게)."""
    if "booking" not in (state.get("plan") or []):
        content += (
            "\n\n---\n이 일정이 마음에 드시면 **항공·숙소 예약**도 도와드릴게요. "
            '"항공·숙소 보여줘"라고 말씀해 주세요. ✈️🏨'
        )
    return content


def itinerary_node(state: State) -> Command:
    """일자별 일정을 LLM으로 서술 (itinerary 카드). 예약 미포함 계획이면 예약 CTA를 덧붙인다."""
    visited = state.get("visited", [])
    if not get_settings().llm_enabled:
        content = _with_booking_cta("### Day 1\n- 주요 명소 관광\n\n### Day 2\n- 근교 코스 (mock)", state)
        return _card(content, "itinerary", "itinerary", {"markdown": content}, visited)
    response = get_llm("itinerary").invoke([{"role": "system", "content": render("itinerary")}, *state["messages"]])
    content = _with_booking_cta(response.content, state)
    return _card(content, "itinerary", "itinerary", {"markdown": content}, visited)


def _last_user_text(messages) -> str:
    """가장 마지막 사용자 발화."""
    for m in reversed(messages):
        if getattr(m, "type", None) == "human" and isinstance(getattr(m, "content", None), str):
            return m.content
    return ""


# ── booking 에이전트: 툴 정의 ──────────────────────────────────────────────
# 에이전트가 '무엇을·어떤 조건으로 검색할지' 스스로 정해 호출한다. 실제 실행·필터·정렬·카드 생성은
# booking_node 가 한다(구조화 결과를 카드로 후처리). 목적지·날짜는 시스템이 맥락에서 채운다.


@tool
def search_flights(depart_time: str = "", sort: str = "") -> str:
    """왕복 항공편을 검색한다.

    - depart_time: 가는 편 출발 시간대 선호 — 'morning'(오전)|'afternoon'(오후)|'evening'(저녁/밤)|''(상관없음)
    - sort: 정렬 — 'price'(저렴한 순)|''(기본)
    """
    return ""  # 실제 실행은 booking_node 가 처리


@tool
def search_hotels(sort: str = "", region: str = "") -> str:
    """숙소를 검색한다.

    - sort: 정렬 — 'price'(저렴한 순)|'rating'(평점순)|''(기본)
    - region: 특정 지역/동네로 좁히고 싶을 때(없으면 '')
    """
    return ""  # 실제 실행은 booking_node 가 처리


_BOOKING_TOOLS = [search_flights, search_hotels]
_TIME_RANGES = {"morning": (0, 12), "afternoon": (12, 18), "evening": (18, 24)}
_TIME_LABEL = {"morning": "오전", "afternoon": "오후", "evening": "저녁"}


def _dep_hour(hhmm) -> int | None:
    """'07:30' → 7. 파싱 실패 시 None."""
    try:
        return int(str(hhmm).split(":")[0])
    except (ValueError, AttributeError, IndexError):
        return None


def _apply_flight_prefs(flights: dict, depart_time: str, sort: str) -> tuple[dict, str]:
    """시간대 필터·가격 정렬 적용 → (적용된 결과, 안내노트).

    시간대 요청이 0건이면 숨기지 않고 전체 유지하되 노트로 알린다(카드=전체, 캡션도 '해당 시간대 없음'을
    일관되게 안내 — 카드/설명 불일치 방지).
    """
    opts = list(flights.get("flights", []))
    note = ""
    rng = _TIME_RANGES.get(depart_time or "")
    if rng:
        hit = [f for f in opts if (h := _dep_hour(f.get("outDep"))) is not None and rng[0] <= h < rng[1]]
        if hit:
            opts = hit
        else:  # 요청 시간대 0건 → 전체 유지 + 노트(캡션이 정확히 안내하도록)
            note = f"요청하신 {_TIME_LABEL.get(depart_time, depart_time)} 시간대 항공은 없어 전체 시간대를 보여줌"
    if sort == "price":
        opts = sorted(opts, key=lambda f: f.get("price", 0))
    return {**flights, "flights": opts}, note


def _booking_caption(user_msg: str, summary: str) -> str:
    """사용자의 마지막 요청에 맞춘 결과 안내 한 문장(fast 티어). 실패/빈 응답이면 ""(호출부가 결정론 캡션)."""
    try:
        r = get_llm("places").invoke(  # 빠른 티어
            [
                {"role": "system", "content": render("booking_caption")},
                {"role": "user", "content": f"사용자의 마지막 요청: {user_msg}\n검색 결과: {summary}"},
            ]
        )
        return (r.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("booking 캡션 생성 실패: %s", exc)
        return ""


# 카드 = (card_type, payload, summary, note). note는 필터/지역 0건 등 '반드시 전달해야 할 사실'.


def _flight_card(state, city, trip, depart_time, sort) -> tuple[str, dict, str, str] | None:
    """왕복 항공 검색+선호 적용 → (card_type, payload, 요약, 노트). 결과 없으면 None."""
    data = ts.search_flights(city, start_date=trip.get("start_date"), nights=trip.get("nights"))
    if not (data and data.get("flights")):
        return None
    data, note = _apply_flight_prefs(data, depart_time, sort)
    times = [f.get("outDep") for f in data["flights"]]
    summary = f"{data.get('route', '항공')} 왕복 {len(times)}편, 가는 편 출발시각 {times}"
    return "flight_results", ts.build_flight_payload(data), summary, note


def _hotel_card(city, sort, region="") -> tuple[str, dict, str, str] | None:
    """숙소 검색+지역필터+정렬 → (card_type, payload, 요약, 노트). 결과 없으면 None.

    지역 필터로 0건이면 숨기지 않고 도시 전체로 폴백하고 노트로 알린다(빈 카드 방지).
    """
    hotels = ts.search_hotels(city, area=region or None)
    note = ""
    if region and not hotels:  # 해당 지역 숙소 없음 → 도시 전체로 폴백
        hotels = ts.search_hotels(city)
        note = f"'{region}' 지역 숙소는 없어 {city} 전체를 보여줌"
    if not hotels:
        return None
    label = "가격 낮은순" if sort == "price" else "평점 높은순"  # build_hotel_payload 정렬과 일치
    summary = f"{city} 숙소 {len(hotels)}곳 · 정렬 {label}"
    return "hotel_results", ts.build_hotel_payload(city, hotels, sort=sort), summary, note


def _det_caption(card_type: str, city: str, note: str) -> str:
    """카드별 결정론적 캡션. 노트(필터/지역 0건 등)가 있으면 그 사실을 우선 안내한다."""
    icon = "✈️" if card_type == "flight_results" else "🏨"
    if note:
        return f"{note} {icon}"
    return f"{city} 왕복 항공편이에요 {icon}" if card_type == "flight_results" else f"{city} 숙소예요 {icon}"


def _booking_fallback(state, city, trip, visited) -> Command:
    """LLM 미설정/툴 미호출 시: focus 슬롯 기반 결정론적 검색(가격 정렬은 적용)."""
    focus = trip.get("focus")
    sort = trip.get("sort") or ""
    cards = []
    if focus in (None, "", "flight"):
        fc = _flight_card(state, city, trip, "", sort)
        if fc:
            cards.append(fc)
    if focus in (None, "", "hotel"):
        hc = _hotel_card(city, sort)
        if hc:
            cards.append(hc)
    return _emit_booking(cards, _last_user_text(state["messages"]), city, visited, tag="fallback")


def _emit_booking(cards, user_msg, city, visited, tag) -> Command:
    """카드들을 캡션과 함께 supervisor로.

    노트(0건 폴백 등 반드시 전달할 사실)가 있는 카드는 '결정론적 캡션'으로 정확히 안내한다.
    노트 없는 대표(첫) 카드에만 LLM이 요청 맥락에 맞춘 캡션을 붙인다(맥락성 + 사실 보장 양립).
    """
    if not cards:
        return Command(
            update={
                "messages": [AIMessage(content="조건에 맞는 항공·숙소를 찾지 못했어요.", name="booking")],
                "visited": visited + ["booking"],
            },
            goto="supervisor",
        )
    # 대표 카드에 노트가 없을 때만 LLM 캡션(사실 누락 위험 없음). 실패 시 결정론 캡션으로.
    llm_caption = ""
    if get_settings().llm_enabled and not cards[0][3]:
        summary = " / ".join(c[2] for c in cards)
        llm_caption = _booking_caption(user_msg, summary)
    messages = []
    for i, (ct, pl, _summary, note) in enumerate(cards):
        content = llm_caption if (i == 0 and llm_caption) else _det_caption(ct, city, note)
        messages.append(
            AIMessage(content=content, name="booking", additional_kwargs={"card_type": ct, "payload": pl})
        )
    logger.info("booking[%s] %s 카드=%s", city, tag, [c[0] for c in cards])
    return Command(update={"messages": messages, "visited": visited + ["booking"]}, goto="supervisor")


def booking_node(state: State) -> Command:
    """예약 에이전트: LLM이 툴(search_flights/search_hotels)을 골라 조건까지 정해 호출하면,
    실제 검색·필터·정렬을 적용해 카드로 후처리한다. LLM 미설정/툴 미호출이면 focus 기반 폴백.
    """
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
    trip = state.get("trip") or {}

    if not get_settings().llm_enabled:
        return _booking_fallback(state, city, trip, visited)

    # 1) 에이전트가 어떤 툴을, 어떤 조건(시간대·정렬)으로 부를지 스스로 결정
    try:
        ai = get_llm("booking").bind_tools(_BOOKING_TOOLS).invoke(
            [{"role": "system", "content": render("booking")}, *state["messages"]]
        )
    except Exception as exc:  # noqa: BLE001 - 툴콜 미지원 등 → 폴백
        logger.warning("booking 에이전트 툴 호출 실패 → 폴백: %s", exc)
        return _booking_fallback(state, city, trip, visited)

    calls = getattr(ai, "tool_calls", None) or []
    if not calls:  # 툴을 안 부르면 focus 기반 기본 검색
        return _booking_fallback(state, city, trip, visited)

    # 2) 에이전트가 정한 파라미터로 실제 검색·필터·정렬 → 카드 후처리
    cards = []
    handled = 0  # 인식한(=처리한) 툴콜 수. 0이면 알 수 없는 툴만 호출된 것 → 폴백
    for tc in calls:
        name = tc.get("name")
        args = tc.get("args") or {}
        sort = args.get("sort", "") or trip.get("sort", "")
        if name == "search_flights":
            handled += 1
            if not any(c[0] == "flight_results" for c in cards):
                fc = _flight_card(state, city, trip, args.get("depart_time", ""), sort)
                if fc:
                    cards.append(fc)
        elif name == "search_hotels":
            handled += 1
            if not any(c[0] == "hotel_results" for c in cards):
                hc = _hotel_card(city, sort, args.get("region", ""))
                if hc:
                    cards.append(hc)

    if handled == 0:  # 알 수 없는 툴명만 반환됨 → focus 기반 폴백(빈 결과 방지)
        logger.warning("booking[%s] 처리 가능한 툴콜 없음 → 폴백: %s", city, [c.get("name") for c in calls])
        return _booking_fallback(state, city, trip, visited)

    logger.info("booking[%s] agent 툴=%s", city, [c.get("name") for c in calls])
    return _emit_booking(cards, _last_user_text(state["messages"]), city, visited, tag="agent")


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

"""워커 노드 (destination · itinerary · booking · payment).

각 워커는 travel_service로 데이터를 조회해 프론트 렌더용 구조화 응답(card_type/payload)을
만든다. itinerary는 LLM으로 일정을 서술한다. 카드 데이터는 AIMessage.additional_kwargs 의
card_type/payload 로 전달돼 응답 turns 에 담긴다.
"""

import re
from concurrent.futures import ThreadPoolExecutor

from langchain.agents import create_agent
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


# ── itinerary·route ReAct 에이전트가 쓰는 조회 툴 ──────────────────────────
# create_agent(ReAct)가 직접 호출한다. 실제 명소·액티비티를 돌려줘 일정·동선을 grounding(할루시네이션 방지).


@tool
def lookup_attractions(city: str, interest: str = "") -> str:
    """도시의 인기 명소를 조회한다. city=도시명(제주·부산·세부·보홀 또는 해외 도시). interest=취향(선택)."""
    cities = ts.find_cities(city)
    if not cities and ts.resolve_place(city, ""):
        cities = [city]
    if not cities:
        return f"'{city}'는 지원하지 않는 도시예요."
    c = cities[0]
    picked, _ = _filter_attractions(ts.get_attractions(c), interest, c)
    if not picked:
        return f"{c} 명소 정보를 찾지 못했어요."
    return f"[{c} 명소]\n" + "\n".join(f"- {a['name']}: {a.get('desc', '')[:50]}" for a in picked[:8])


@tool
def lookup_activities(city: str) -> str:
    """도시의 액티비티·투어(체험 프로그램)를 조회한다."""
    cities = ts.find_cities(city)
    if not cities:
        return f"'{city}' 액티비티 정보가 없어요."
    acts = ts.search_activities(cities[0])
    if not acts:
        return f"{cities[0]} 액티비티 정보가 없어요."
    return f"[{cities[0]} 액티비티]\n" + "\n".join(
        f"- {a['name']} ({a.get('duration', '')}, {a.get('price', 0):,}원)" for a in acts
    )


_TRIP_TOOLS = [lookup_attractions, lookup_activities]


def _attractions_context(cities: list[str]) -> str:
    """명소 데이터를 프롬프트 주입용 블록으로 만든다.

    에이전트가 '명소 조회' 툴 라운드(LLM 호출 1회 ≈ 5~15s)를 거치지 않고 바로 생성하도록 선주입한다.
    보통 destination 워커가 먼저 돌아 캐시가 데워져 있어 즉시 반환되고, 캐시가 비어도 여기서 직접
    조회(도시별 병렬)하는 편이 에이전트의 툴 라운드(LLM+API)보다 항상 싸다.
    """
    if not cities:
        return ""
    with ThreadPoolExecutor(max_workers=min(4, len(cities))) as ex:
        results = list(ex.map(ts.get_attractions, cities))
    parts = []
    for city, attractions in zip(cities, results):
        if attractions:
            names = "\n".join(f"- {a['name']}: {(a.get('desc') or '')[:50]}" for a in attractions[:8])
            parts.append(f"[{city} 명소]\n{names}")
    if not parts:
        return ""
    return (
        "\n\n# 이미 조회된 명소 데이터\n"
        "(아래에 있는 도시는 추가 조회 없이 이 안에서 골라 사용하고, 아래에 없는 도시만 lookup_attractions로 조회)\n"
        + "\n\n".join(parts)
    )


def _parse_route_option(parts: list[str]) -> _RouteOption | None:
    """'A | 라벨 | 아이콘 | 도착라벨 | 활동 | 이동 | 아이콘 | 도착라벨 | 활동 | 출국 | 하이라이트' 1행 파싱.

    핵심 필드(라벨·도착라벨·활동·이동)가 비면 실패 처리(빈 카드 방지). 하이라이트에 '|'가
    들어가 필드가 더 쪼개졌으면 나머지를 하이라이트로 도로 합친다(내용 유실 방지).
    """
    if len(parts) < 11:
        return None
    if not all(parts[i] for i in (1, 3, 4, 5, 7, 8)):  # 라벨·도착라벨·활동·이동은 필수
        return None
    return {
        "label": parts[1],
        "first": {"icon": parts[2], "arriveLabel": parts[3], "sub": parts[4]},
        "transferLabel": parts[5],
        "second": {"icon": parts[6], "arriveLabel": parts[7], "sub": parts[8]},
        "endNote": parts[9],
        "highlight": " | ".join(parts[10:]).strip(),
    }


def _parse_route(text: str) -> dict | None:
    """파이프 평문 3행(A/B/C) → route_plan payload. 형식이 안 맞으면 None(호출부가 mock 폴백)."""
    rows: dict[str, list[str]] = {}
    for line in (text or "").splitlines():
        parts = [p.strip() for p in line.split("|")]
        if parts and parts[0] in ("A", "B", "C"):
            rows[parts[0]] = parts
    a = _parse_route_option(rows.get("A", []))
    b = _parse_route_option(rows.get("B", []))
    c = rows.get("C", [])
    if not (a and b):
        return None
    return {
        "routes": {"A": a, "B": b},
        "compareStrip": {
            "totalMove": c[1] if len(c) > 1 else "",
            "lastDayAirport": c[2] if len(c) > 2 else "",
        },
    }


def _run_route_agent(state: State, c1: str, c2: str, nights: int) -> dict | None:
    """route: 선주입된 명소 데이터로 A/B 동선을 'LLM 1콜 평문'으로 생성해 파싱. 실패 시 None.

    구조화 출력(with_structured_output)은 elice에서 ~2.5배 느려(직전 측정 ~26s) 파이프 평문
    3행으로 받아 결정론적으로 파싱한다(recommend와 동일 패턴). grounding은 선주입 데이터가 보장.
    """
    task = f"방문 도시: {c1}, {c2}. 총 숙박 {nights or '미정'}박. A안은 {c1} 먼저, B안은 {c2} 먼저 방문."
    try:
        r = get_llm("route").invoke(
            [
                {"role": "system", "content": render("route") + _attractions_context([c1, c2])},
                *state["messages"],
                {"role": "user", "content": task},
            ]
        )
        payload = _parse_route(r.content or "")
        if payload is None:
            logger.warning("route 평문 파싱 실패: %r", (r.content or "")[:120])
        return payload
    except Exception as exc:  # noqa: BLE001 - 실패 → 호출부가 mock 폴백
        logger.warning("route 동선 생성 실패: %s", exc)
        return None


def route_node(state: State) -> Command:
    """여러 도시 방문 시 방문 순서·이동 동선을 A/B안으로 비교(route_plan 카드).

    ReAct 에이전트가 실제 명소를 조회해 동선을 grounding한다. 도시가 하나뿐이면 조용히 통과.
    """
    visited = state.get("visited", [])
    cities = _resolve_destinations(state)
    if len(cities) < 2:  # 단일 도시 → 동선 비교 불필요
        return Command(update={"visited": visited + ["route"]}, goto="supervisor")
    c1, c2 = cities[0], cities[1]
    nights = _pos_int((state.get("trip") or {}).get("nights"), 0, 60)

    payload = None
    if get_settings().llm_enabled:
        payload = _run_route_agent(state, c1, c2, nights)
    if payload is None:  # LLM 미설정·에이전트 실패 → 결정론적 mock
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


def _run_itinerary_agent(state: State, config=None) -> str:
    """itinerary 에이전트: 선주입된 명소 데이터(캐시)로 바로 일정을 생성한다 — grounding 유지하며
    '명소 조회' 툴 라운드를 생략해 LLM 호출을 줄인다. 부족하면 툴로 추가 조회(액티비티·타 도시).
    부모 config를 중첩 호출에 전달해 내부 LLM 토큰이 스트림으로 흐르게 한다(타이핑 효과).
    툴콜 미지원·실패 시 툴 없이 직접 생성으로 폴백."""
    try:
        system = render("itinerary") + _attractions_context(_resolve_destinations(state))
        agent = create_agent(get_llm("itinerary"), _TRIP_TOOLS, system_prompt=system)
        result = agent.invoke({"messages": state["messages"]}, config)
        # 이번 실행에서 '새로 생성된' 메시지만 본다(입력 히스토리의 과거 AI 답을 일정으로 오인 방지)
        new_msgs = result.get("messages", [])[len(state["messages"]):]
        for m in reversed(new_msgs):
            if getattr(m, "type", None) == "ai" and not getattr(m, "tool_calls", None):
                text = (m.content or "").strip()
                if text:
                    return text
    except Exception as exc:  # noqa: BLE001 - 에이전트 실패 → 툴 없이 직접 생성
        logger.warning("itinerary 에이전트 실패 → 툴 없이 생성: %s", exc)
    # 폴백은 툴이 없으므로 툴 언급 없는 전용 프롬프트로 직접 생성
    r = get_llm("itinerary").invoke([{"role": "system", "content": render("itinerary_direct")}, *state["messages"]])
    return (r.content or "").strip() or "### Day 1\n- 일정을 준비하고 있어요"


def itinerary_node(state: State, config=None) -> Command:
    """일자별 일정을 ReAct 에이전트로 서술 (itinerary 카드). 예약 미포함 계획이면 예약 CTA를 덧붙인다.

    config를 받아 중첩 에이전트에 전달한다 — 내부 LLM 토큰이 그래프 스트림으로 흘러 타이핑 효과가 난다.
    """
    visited = state.get("visited", [])
    if not get_settings().llm_enabled:
        content = _with_booking_cta("### Day 1\n- 주요 명소 관광\n\n### Day 2\n- 근교 코스 (mock)", state)
        return _card(content, "itinerary", "itinerary", {"markdown": content}, visited)
    content = _with_booking_cta(_run_itinerary_agent(state, config), state)
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
def search_hotels(sort: str = "", region: str = "", nights: int = 0, checkin: str = "") -> str:
    """숙박 '구간' 하나의 숙소를 검색한다. (구간 = 며칠은 어디서/어떤 조건으로)

    - sort: 정렬 — 'price'(저렴한 순)|'rating'(평점순)|''(기본)
    - region: 특정 지역/동네로 좁힐 때(없으면 '')
    - nights: 이 구간의 숙박 박수. 모르면 0
    - checkin: 이 구간의 체크인 날짜 YYYY-MM-DD — 여행 날짜에서 직접 계산해 넣어라
      (예: 8/15 출발 3박에서 "3일차부터 서귀포" → 서귀포 checkin="2026-08-17"). 계산 불가면 ""
    """
    return ""  # 실제 실행은 booking_node 가 처리


_BOOKING_TOOLS = [search_flights, search_hotels]
_TIME_RANGES = {"morning": (0, 12), "afternoon": (12, 18), "evening": (18, 24)}
# 항공권만 보여준 턴 뒤, 숙소 턴으로 이어가도록 안내(항공/숙소를 턴으로 분리)
_HOTEL_LEAD = ' 마음에 드는 항공편을 고르시고 "숙소도 보여줘"라고 하시면 숙소를 이어서 골라드릴게요. 🏨'
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


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date_md(iso: str, offset: int = 0) -> str:
    """ISO 날짜 + offset일 → 'M.D' 라벨."""
    from datetime import datetime, timedelta

    d = datetime.strptime(iso, "%Y-%m-%d") + timedelta(days=offset)
    return f"{d.month}.{d.day}"


def _iso_add_days(iso: str, days: int) -> str:
    """ISO 날짜 + days일 → ISO."""
    from datetime import datetime, timedelta

    return (datetime.strptime(iso, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")


def _hotel_card(city, sort, region="", stay_nights=0, checkin_iso="", segment=0) -> tuple[str, dict, str, str] | None:
    """숙박 '구간' 하나의 숙소 검색 → (card_type, payload, 요약, 노트). 결과 없으면 None.

    구간 = 에이전트가 사용자 발화에서 나눈 숙박 단위(체크인 날짜·박수·지역·조건). 같은 지역이라도
    조건이 다르면("처음 2일 가성비, 마지막 하루 고급") 별개 구간 = 별개 카드다.
    구간 날짜는 에이전트가 checkin으로 확정한다(프론트 선택 순서와 무관).
    지역 필터로 0건이면 숨기지 않고 도시 전체로 폴백하고 노트로 알린다(빈 카드 방지).
    """
    hotels = ts.search_hotels(city, area=region or None)
    note = ""
    if region and not hotels:  # 해당 지역 숙소 없음 → 도시 전체로 폴백
        hotels = ts.search_hotels(city)
        note = f"'{region}' 지역 숙소는 없어 {city} 전체를 보여줌"
        region = ""
    if not hotels:
        return None
    label = "가격 낮은순" if sort == "price" else "평점 높은순"  # build_hotel_payload 정렬과 일치
    place = f"{city} {region}" if region else city
    summary = f"{place} 숙소 {len(hotels)}곳 · 정렬 {label}"
    payload = ts.build_hotel_payload(city, hotels, sort=sort)
    # 카드 식별자(구간 단위) — 프론트가 '같은 카드 안에서는 교체, 다른 카드(구간)면 누적' 선택을 하는 키.
    # 같은 지역도 구간이 다르면 다른 카드이므로 구간 번호를 포함한다.
    payload["cardKey"] = f"{city}:{region or 'all'}:{segment}"
    if stay_nights > 0:
        payload["stayNights"] = stay_nights
        if checkin_iso:  # 구간 날짜를 알 때만 체크인–체크아웃 라벨 확정
            stay = f"{_date_md(checkin_iso)}–{_date_md(checkin_iso, stay_nights)}"
            payload["stayLabel"] = stay
            payload["stayCheckin"] = checkin_iso  # 시간순 정렬 기준(프론트 표시 순서)
            payload["banner"] = f"{stay} · {place} {stay_nights}박"  # 카드 배너에 '언제 어디서'를 표시
            summary += f" · 숙박 {stay}"
    return "hotel_results", payload, summary, note


def _card_region(card_type: str, payload: dict) -> str:
    """숙소 카드의 숙소들이 모두 같은 지역이면 그 지역명(스플릿 스테이 카드 라벨용). 아니면 ""."""
    if card_type != "hotel_results":
        return ""
    regions = {h.get("region") for h in payload.get("hotels", [])}
    return regions.pop() if len(regions) == 1 and None not in regions else ""


def _det_caption(card_type: str, city: str, note: str, region: str = "") -> str:
    """카드별 결정론적 캡션. 노트(필터/지역 0건 등)가 있으면 그 사실을 우선 안내한다."""
    icon = "✈️" if card_type == "flight_results" else "🏨"
    if note:
        return f"{note} {icon}"
    if card_type == "flight_results":
        return f"{city} 왕복 항공편이에요 {icon}"
    return f"{region} 숙소예요 {icon}" if region else f"{city} 숙소예요 {icon}"


def _booking_fallback(state, city, trip, visited) -> Command:
    """LLM 미설정/툴 미호출/목표 불일치 시: focus 슬롯 기반 결정론적 검색(한 턴에 한 종류, 항공권 먼저)."""
    focus = trip.get("focus")
    sort = trip.get("sort") or ""
    user_msg = _last_user_text(state["messages"])
    if focus == "hotel":  # 숙소를 콕 집었을 때만 숙소 턴
        hc = _hotel_card(city, sort)
        return _emit_booking([hc] if hc else [], user_msg, city, visited, tag="fallback",
                             empty_msg=_no_result_msg("hotel"))
    # 그 외 → 항공권 먼저
    fc = _flight_card(state, city, trip, "", sort)
    if fc:
        lead = _HOTEL_LEAD if not focus else ""  # 예약 첫 진입(focus 없음)이면 숙소로 이어가게 안내
        return _emit_booking([fc], user_msg, city, visited, tag="fallback", lead=lead)
    # 항공권 없음: 모호(focus="")면 숙소라도, 항공권을 콕 집었으면(focus=flight) 빈 결과 안내(목표 유지)
    if not focus:
        hc = _hotel_card(city, sort)
        if hc:
            return _emit_booking([hc], user_msg, city, visited, tag="fallback")
    return _emit_booking([], user_msg, city, visited, tag="fallback", empty_msg=_no_result_msg(focus))


def _no_result_msg(focus: str | None) -> str:
    """검색한 종류에 맞춘 '결과 없음' 문구(조회 안 한 종류를 없다고 오안내하지 않게)."""
    if focus == "hotel":
        return "조건에 맞는 숙소를 찾지 못했어요."
    if focus == "flight":
        return "조건에 맞는 항공편을 찾지 못했어요."
    return "조건에 맞는 항공·숙소를 찾지 못했어요."


def _emit_booking(cards, user_msg, city, visited, tag, lead="", empty_msg="조건에 맞는 항공·숙소를 찾지 못했어요.") -> Command:
    """카드들을 캡션과 함께 supervisor로.

    노트(0건 폴백 등 반드시 전달할 사실)가 있는 카드는 '결정론적 캡션'으로 정확히 안내한다.
    노트 없는 대표(첫) 카드에만 LLM이 요청 맥락에 맞춘 캡션을 붙인다(맥락성 + 사실 보장 양립).
    lead가 있으면 첫 카드 캡션 끝에 다음 단계 안내(예: 숙소 턴)를 덧붙인다.
    empty_msg는 카드가 없을 때 문구(검색한 종류에 맞춰 호출부가 지정).
    """
    if not cards:
        return Command(
            update={
                "messages": [AIMessage(content=empty_msg, name="booking")],
                "visited": visited + ["booking"],
            },
            goto="supervisor",
        )
    # 대표 카드에 노트가 없을 때만 LLM 캡션(사실 누락 위험 없음). 실패 시 결정론 캡션으로.
    # 카드가 여러 장(스플릿 스테이: 지역별 숙소)이면 각 카드에 지역 결정론 캡션을 붙인다(뭉뚱그림 방지).
    llm_caption = ""
    if get_settings().llm_enabled and not cards[0][3] and len(cards) == 1:
        llm_caption = _booking_caption(user_msg, cards[0][2])
    messages = []
    for i, (ct, pl, _summary, note) in enumerate(cards):
        region = _card_region(ct, pl)  # 스플릿 스테이(지역별 숙소 카드)면 캡션에 지역 표기
        content = llm_caption if (i == 0 and llm_caption) else _det_caption(ct, city, note, region)
        if i == 0 and lead:
            content = f"{content}{lead}"
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

    # 항공 검색엔 출발일이 필수 — 사용자가 날짜를 말한 적 없으면 지어내지 말고 묻는다.
    # (숙소만 원하는 턴(focus=hotel)은 날짜 없이 진행 가능)
    if trip.get("focus") != "hotel" and not trip.get("start_date"):
        ask = (
            "항공권을 찾으려면 출발 날짜가 필요해요. 언제 떠나실 예정인가요? "
            '(예: "8월 15일부터 2박 3일")'
        )
        return Command(
            update={"messages": [AIMessage(content=ask, name="booking")], "visited": visited + ["booking"]},
            goto="supervisor",
        )

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
    if not calls:
        # 에이전트가 툴 대신 '질문'을 택한 경우(조건 특정화: "제주와 서귀포, 어디를 먼저 가세요?" 등)
        # 그 질문을 그대로 사용자에게 전달한다. 질문도 없으면 focus 기반 기본 검색.
        question = (getattr(ai, "content", "") or "").strip()
        if question and "?" in question and len(question) < 300:  # 질문 형태만 전달(설명·환각 노출 방지)
            return Command(
                update={"messages": [AIMessage(content=question, name="booking")], "visited": visited + ["booking"]},
                goto="supervisor",
            )
        return _booking_fallback(state, city, trip, visited)

    # 2) 에이전트가 정한 파라미터 수집 — 숙소는 '숙박 구간' 단위(호출 순서 = 숙박 순서).
    #    같은 지역이라도 조건이 다르면 별개 구간("처음 2일 가성비, 마지막 하루 고급").
    flight_req = None
    hotel_reqs: list[dict] = []  # [{region, sort, nights}] — 구간 순서 유지
    ran: set[str] = set()  # 실제 실행한 툴명(재검색·오안내 방지)
    for tc in calls:
        name = tc.get("name")
        args = tc.get("args") or {}
        sort = args.get("sort", "") or trip.get("sort", "")
        if name == "search_flights":
            ran.add(name)
            if flight_req is None:
                flight_req = {"depart_time": args.get("depart_time", ""), "sort": sort}
        elif name == "search_hotels":
            ran.add(name)
            region = args.get("region", "")
            region = region.strip() if isinstance(region, str) else ""
            n = args.get("nights", 0)
            n = n if isinstance(n, int) and not isinstance(n, bool) and 0 < n <= 30 else 0
            checkin = args.get("checkin", "")
            checkin = checkin.strip() if isinstance(checkin, str) and _ISO_DATE_RE.match(str(checkin).strip()) else ""
            req = {"region": region, "sort": sort, "nights": n, "checkin": checkin}
            if req not in hotel_reqs and len(hotel_reqs) < 5:  # 완전 동일 구간만 중복 제거
                hotel_reqs.append(req)

    # 숙박 박수 보정: 미명시 구간엔 '잔여' 박수만 균등 배분(안전망 — 보통은 에이전트가 되물어 특정).
    # 전부 명시됐는데 합이 총 박수와 달라도 최신 발화의 명시값을 신뢰한다.
    total_nights = trip.get("nights") or 0
    if hotel_reqs:
        specified = sum(r["nights"] for r in hotel_reqs)
        flex = [r for r in hotel_reqs if not r["nights"]]
        remain = max(total_nights - specified, 0)
        if flex and remain:
            base, extra = divmod(remain, len(flex))
            for i, r in enumerate(flex):
                r["nights"] = base + (1 if i < extra else 0)

    # 구간 날짜: 에이전트가 계산한 checkin 우선. 없으면 '직전 구간 끝'에 이어붙이는 안전망
    # (첫 구간의 기본은 여행 시작일). 에이전트가 날짜를 다 주면 이 체인은 아무것도 하지 않는다.
    cursor = trip.get("start_date", "")
    for r in hotel_reqs:
        if not r["checkin"] and cursor:
            r["checkin"] = cursor
        if r["checkin"] and r["nights"]:
            end = _iso_add_days(r["checkin"], r["nights"])
            cursor = max(cursor, end)  # 전진만 — 명시 checkin이 뒤섞여도 미명시 구간에 과거 날짜를 주지 않음

    # 3) 실행: 항공 → 숙소 구간들 → 카드 후처리
    cards = []
    if flight_req:
        fc = _flight_card(state, city, trip, flight_req["depart_time"], flight_req["sort"])
        if fc:
            cards.append(fc)
    for i, r in enumerate(hotel_reqs):
        hc = _hotel_card(city, r["sort"], r["region"],
                         stay_nights=r["nights"], checkin_iso=r["checkin"], segment=i)
        if hc:
            cards.append(hc)
    # 프론트 표시·숙박 순서용 stayOrder = 체크인 날짜순(없는 구간은 뒤로)
    hotel_cards = [c for c in cards if c[0] == "hotel_results" and c[1].get("stayNights")]
    for rank, c in enumerate(sorted(hotel_cards, key=lambda c: c[1].get("stayCheckin", "9999"))):
        c[1]["stayOrder"] = rank

    if not ran:  # 알 수 없는 툴명만 반환됨 → focus 기반 폴백(빈 결과 방지)
        logger.warning("booking[%s] 처리 가능한 툴콜 없음 → 폴백: %s", city, [c.get("name") for c in calls])
        return _booking_fallback(state, city, trip, visited)

    # 한 턴에 한 종류만: focus로 목표 타입 강제(숙소 콕 집으면 숙소, 아니면 항공권 먼저).
    focus = trip.get("focus")
    target = "hotel_results" if focus == "hotel" else "flight_results"
    target_kind = "hotel" if target == "hotel_results" else "flight"  # 빈결과 문구는 '검색한 종류' 기준
    target_tool = "search_" + ("hotels" if target_kind == "hotel" else "flights")
    cards = [c for c in cards if c[0] == target]
    if not cards:
        if target_tool in ran:  # 목표 툴을 이미 실행했는데 0건 → 재검색 말고 빈 결과 안내(중복 API 방지)
            return _emit_booking([], _last_user_text(state["messages"]), city, visited,
                                 tag="agent", empty_msg=_no_result_msg(target_kind))
        return _booking_fallback(state, city, trip, visited)  # 목표 툴 미실행 → 결정론적 목표 검색
    if target == "flight_results":
        cards = cards[:1]  # 항공은 한 턴 한 카드
    lead = _HOTEL_LEAD if (target == "flight_results" and not focus) else ""

    logger.info("booking[%s] agent 툴=%s → %s ×%d", city, [c.get("name") for c in calls], target, len(cards))
    return _emit_booking(cards, _last_user_text(state["messages"]), city, visited, tag="agent", lead=lead)


@tool
def issue_confirmation(summary: str = "", total: int = 0) -> str:
    """선택한 항공·숙소 예약을 확정(발급)한다.

    - summary: 예약 내용 요약(예: '대한항공 07:30 왕복 · 신라스테이 2박'). 대화에서 최종 선택한 항공/숙소를 반영.
    - total: 결제 총액(원). 대화의 '총 …원'을 반영. 모르면 0.
    """
    return ""  # 실제 확정 발급은 payment_node 가 처리


_PAYMENT_TOOLS = [issue_confirmation]


def _payment_extract(state: State) -> tuple[str, int]:
    """에이전트가 대화에서 예약 내용·총액을 추출(issue_confirmation 툴콜, 정규식 대신 LLM 이해). 실패 시 ('', 0)."""
    try:
        ai = get_llm("payment").bind_tools(_PAYMENT_TOOLS).invoke(
            [{"role": "system", "content": render("payment")}, *state["messages"]]
        )
        for tc in getattr(ai, "tool_calls", None) or []:
            if tc.get("name") == "issue_confirmation":
                args = tc.get("args") or {}
                summary = args.get("summary", "")
                summary = summary.strip() if isinstance(summary, str) else ""
                total = args.get("total", 0)
                # 툴 시그니처가 int라 코어싱됨. bool 제외·상한 방어(0이면 호출부가 추정 폴백)
                valid = isinstance(total, int) and not isinstance(total, bool) and 0 < total <= 100_000_000
                return summary, total if valid else 0
    except Exception as exc:  # noqa: BLE001 - 툴콜 미지원 등 → 추정 폴백
        logger.warning("payment 에이전트 추출 실패: %s", exc)
    return "", 0


def payment_node(state: State) -> Command:
    """결제 에이전트: 대화에서 예약 내용·총액을 LLM으로 추출해 더미 확정서(confirmation) 카드를 발급한다.
    영수증 숫자(확정번호·총액)는 결정론적으로 정확히 유지하고, 확정 메시지에 무엇을 예약했는지 반영한다.
    비로그인 사용자는 결제 불가 — 예약이 계정에 저장돼야 하므로 로그인 안내로 대체한다.
    """
    visited = state.get("visited", [])
    trip = state.get("trip") or {}

    if not trip.get("authenticated"):  # 결제는 로그인 필수(예약·결제 내역이 계정에 저장됨)
        ask = (
            "결제는 로그인 후 진행할 수 있어요 — 예약 내역이 회원님 계정에 저장되거든요. "
            "우측 패널에서 로그인 또는 회원가입하고 다시 결제해 주세요. 🔐"
        )
        return Command(
            update={"messages": [AIMessage(content=ask, name="payment")], "visited": visited + ["payment"]},
            goto="supervisor",
        )
    text = _user_text(state["messages"])  # 추정 폴백용 (사용자 발화만)
    cities, _ = _resolve_destination(state)
    travelers = _pos_int(trip.get("travelers"), ts.parse_people(text), 30)
    nights = _pos_int(trip.get("nights"), ts.parse_nights(text), 60)

    summary, total = _payment_extract(state) if get_settings().llm_enabled else ("", 0)
    if not total:  # 추출 실패 → 인원·박수·최저가 기반 개략 추정
        total = ts.estimate_total(cities, travelers, nights)
    code = ts.make_confirmation()
    payload = {
        "code": code,
        "title": (" + ".join(cities) if cities else "여행") + " 예약",
        "dateLabel": "",  # 백엔드는 선택 날짜를 추적하지 않음 → 프론트가 로컬 선택값으로 덮어씀
        # 프론트가 실제 선택 합계로 덮어씀. NOTE(보류): 무상태 구조라 서버측 선택 검증은 데모 스코프 밖.
        "total": total,
        "method": "dummy",
        "status": "paid",
    }
    caption = f"💳 결제 완료! {summary} 예약이 확정됐어요. 확정번호 {code}" if summary else f"💳 결제 완료! 확정번호 {code}"
    return _card(caption, "payment", "confirmation", payload, visited)

"""워커 노드 (destination · itinerary · booking · payment).

각 워커는 자기 역할의 LLM(티어별 모델)과 툴을 가진 ReAct 에이전트다.
툴로 mock 데이터(→ 이후 실 API)를 조회해 사용자에게 안내한다.
LLM이 없으면(mock-only/키없음) 고정 mock 응답으로 폴백한다.
"""

from langchain_core.messages import AIMessage
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from app.agents.llm import get_llm
from app.agents.state import State
from app.core.config import get_settings
from app.core.logging import get_logger
from app.tools import (
    process_payment,
    search_activities,
    search_destination_info,
    search_flights,
    search_hotels,
)

logger = get_logger(__name__)

# 워커별 툴
_AGENT_TOOLS = {
    "destination": [search_destination_info, search_activities],
    "itinerary": [],  # 일정 구성은 추론 위주 (툴 없음)
    "booking": [search_flights, search_hotels],
    "payment": [process_payment],
}

# 워커별 시스템 프롬프트
_AGENT_PROMPTS = {
    "destination": (
        "너는 여행지·명소 담당이야. search_destination_info / search_activities 툴로 조회해 "
        "사용자가 언급한 도시의 대표 명소와 액티비티를 한국어로 간결히 안내해."
    ),
    "itinerary": (
        "너는 일자별 여행 일정 설계 '전담'이야. 예약·결제·실시간 재고 조회는 네 일이 아니라 "
        "다른 담당이 처리하니 신경 쓰지 말고, '실제 예약을 대행할 수 없다'는 식의 면책은 절대 하지 마. "
        "지금까지 대화에 나온 목적지·기간·명소를 바탕으로 Day별 일정표를 반드시 작성해서 제시해. "
        "여러 도시를 방문하면 효율적인 방문 순서와 이동 동선(수단·시간)도 제안해. 간결한 한국어로."
    ),
    "booking": (
        "너는 항공·숙소 예약 담당이야. search_flights / search_hotels 툴로 조회해 "
        "날짜별 가격과 숙소 옵션을 한국어로 정리해 안내해."
    ),
    "payment": (
        "너는 결제 담당이야. 예약 총액으로 process_payment 툴을 호출해 결제하고 "
        "확정번호를 안내해. 금액이 불명확하면 대화 맥락에서 합리적으로 추정해."
    ),
}

# 폴백 mock 응답 (LLM 미설정 시)
_MOCK_RESPONSES = {
    "destination": "🗺️ [여행지] 제주 인기 명소: 성산일출봉 · 우도 · 한라산",
    "itinerary": "📅 [일정] Day1 성산·우도·흑돼지 / Day2 한라산·카페거리",
    "booking": "✈️🏨 [예약] 김포→제주 항공, 제주신라 3박 옵션을 정리했어요",
    "payment": "💳 [결제] 결제 완료! 확정번호 TA-20260725-0001",
}


def _build_agents() -> dict:
    """LLM이 있으면 워커별 ReAct 에이전트를 생성한다."""
    if not get_settings().llm_enabled:
        logger.info("workers: LLM 미설정/mock 전용 → mock 폴백 사용")
        return {}
    agents = {}
    for name, tools in _AGENT_TOOLS.items():
        agents[name] = create_react_agent(
            get_llm(name), tools=tools, prompt=_AGENT_PROMPTS[name]
        )
    return agents


_agents = _build_agents()


def _make_worker(name: str):
    """이름별 워커 노드 팩토리."""

    def node(state: State) -> Command:
        visited = state.get("visited", []) + [name]
        if name in _agents:
            logger.info("worker[%s] ReAct 실행", name)
            result = _agents[name].invoke({"messages": state["messages"]})
            content = result["messages"][-1].content
        else:
            logger.info("worker[%s] mock 폴백", name)
            content = _MOCK_RESPONSES[name]
        return Command(
            update={
                "messages": [AIMessage(content=content, name=name)],
                "visited": visited,
            },
            goto="supervisor",
        )

    return node


destination_node = _make_worker("destination")
itinerary_node = _make_worker("itinerary")
booking_node = _make_worker("booking")
payment_node = _make_worker("payment")

"""Planner 노드.

coordinator가 handoff한 뒤, 사용자 요청을 분석해 **필요한 워커만** 순서대로 계획한다.
특히 결제(payment)는 사용자가 명시적으로 결제·예약 확정을 원할 때만 포함한다.
"""

from langchain_core.messages import AIMessage
from langgraph.types import Command

from app.agents.llm import get_llm
from app.agents.state import TEAM_MEMBERS, State
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

PLANNER_SYSTEM = """너는 여행 요청을 분석해 필요한 작업(워커)만 순서대로 고르는 플래너야.

가능한 워커:
- destination: 여행지·명소·액티비티 정보 조회
- itinerary: 일자별 일정·동선 설계
- booking: 항공·숙소 검색 및 예약
- payment: 결제(예약 확정)

선택 규칙:
- 여행지 추천·정보만 원하면: destination
- 일정을 원하면: destination, itinerary
- 항공/숙소 예약까지 원하면: destination, itinerary, booking
- 사용자가 '결제', '예약 확정', '결제까지 진행'을 명시적으로 요청할 때만 마지막에 payment 추가

필요한 워커 이름만 쉼표로 나열해. 예: destination, itinerary"""

DEFAULT_PLAN = ["destination", "itinerary"]

# 결제를 실행하려면 최신 사용자 발화에 아래 의사가 있어야 한다 (결정론적 gate)
PAY_KEYWORDS = ("결제", "구매", "예약 확정", "결제까지", "카드로")


def _wants_payment(messages) -> bool:
    """최신 사용자 발화에 명시적 결제 의사가 있는지."""
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human":
            return any(k in msg.content for k in PAY_KEYWORDS)
    return False


def planner_node(state: State) -> Command:
    """요청을 분석해 실행할 워커 계획을 세우고 supervisor로 넘긴다."""
    settings = get_settings()

    if not settings.llm_enabled:
        logger.info("planner: LLM 미설정 → 기본 계획")
        return Command(
            update={"plan": list(DEFAULT_PLAN), "full_plan": "기본 계획", "visited": []},
            goto="supervisor",
        )

    llm = get_llm("planner")
    response = llm.invoke([{"role": "system", "content": PLANNER_SYSTEM}, *state["messages"]])
    content = response.content.lower()

    # 언급된 워커를 팀 순서(의존성 순)대로 선택
    steps = [w for w in TEAM_MEMBERS if w in content]
    if not steps:
        steps = list(DEFAULT_PLAN)

    # 결정론적 결제 승인: 최신 사용자 발화에 결제 의사가 없으면 payment 제외
    if "payment" in steps and not _wants_payment(state["messages"]):
        steps = [s for s in steps if s != "payment"]
        logger.info("planner: 명시적 결제 의사 없음 → payment 제외")

    logger.info("planner 계획: %s", steps)
    plan_text = " → ".join(steps)
    return Command(
        update={
            "messages": [AIMessage(content=f"진행 계획: {plan_text}", name="planner")],
            "plan": steps,
            "full_plan": plan_text,
            "visited": [],
        },
        goto="supervisor",
    )

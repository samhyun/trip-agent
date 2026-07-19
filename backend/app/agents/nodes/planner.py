"""Planner 노드.

coordinator가 handoff한 뒤, 어떤 워커를 어떤 순서로 실행할지 계획을 세운다.
현재(2단계)는 고정 순서 계획을 내는 mock stub이다. 다음 단계에서 사용자 요청을
분석해 동적으로 계획(JSON)을 세우도록 LLM 기반으로 확장한다.
"""

from langchain_core.messages import AIMessage
from langgraph.types import Command

from app.agents.state import State
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_PLAN = "여행지 조회 → 일정 구성 → 예약 → 결제 순으로 진행할게요."


def planner_node(state: State) -> Command:
    """실행 계획을 세우고 supervisor로 넘긴다."""
    logger.info("planner: 실행 계획 수립")
    return Command(
        update={
            "messages": [AIMessage(content=DEFAULT_PLAN, name="planner")],
            "full_plan": DEFAULT_PLAN,
            "visited": [],
        },
        goto="supervisor",
    )

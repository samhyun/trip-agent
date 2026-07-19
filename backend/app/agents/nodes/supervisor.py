"""Supervisor 노드.

계획에 따라 다음 워커를 결정한다. 현재(2단계)는 팀 순서대로 아직 방문하지 않은
워커를 하나씩 라우팅하고, 모두 방문하면 종료(FINISH)하는 순차 라우터다.
다음 단계에서 LLM 구조화 출력(Router)으로 계획·상태 기반 동적 라우팅으로 확장한다.
"""

from langgraph.graph import END
from langgraph.types import Command

from app.agents.state import TEAM_MEMBERS, State
from app.core.logging import get_logger

logger = get_logger(__name__)


def supervisor_node(state: State) -> Command:
    """planner가 정한 계획(plan)대로, 아직 방문하지 않은 다음 워커로 라우팅."""
    plan = state.get("plan") or list(TEAM_MEMBERS)
    visited = state.get("visited", [])
    for worker in plan:
        if worker not in visited:
            logger.info("supervisor → %s (계획=%s)", worker, plan)
            return Command(goto=worker, update={"next": worker})

    logger.info("supervisor: 계획 완료 → FINISH")
    return Command(goto=END, update={"next": "FINISH"})

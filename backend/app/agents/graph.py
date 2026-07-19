"""에이전트 그래프 조립 및 실행.

현재(2단계) 구조:
    START → coordinator ─(정보충분)→ planner → supervisor ⇄ [워커들] → END
                        └(정보부족)──────────────────────────────→ END

라우팅은 각 노드가 반환하는 `Command(goto=...)` 로 결정된다.
"""

from langgraph.graph import START, StateGraph

from app.agents.nodes import (
    booking_node,
    coordinator_node,
    destination_node,
    faq_node,
    itinerary_node,
    payment_node,
    planner_node,
    supervisor_node,
)
from app.agents.state import State
from app.core.logging import get_logger

logger = get_logger(__name__)


def build_graph():
    """그래프를 구성해 컴파일한다."""
    builder = StateGraph(State)
    builder.add_node("coordinator", coordinator_node)
    builder.add_node("faq", faq_node)
    builder.add_node("planner", planner_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("destination", destination_node)
    builder.add_node("itinerary", itinerary_node)
    builder.add_node("booking", booking_node)
    builder.add_node("payment", payment_node)

    builder.add_edge(START, "coordinator")
    # 이후 흐름은 각 노드의 Command(goto=...)가 결정
    return builder.compile()


_graph = build_graph()


def run_agent(user_input: str, conversation_id: str) -> dict:
    """사용자 입력을 그래프에 넣고 최종 응답을 뽑아낸다.

    Returns: {"answer": str, "agent": str | None}
    """
    logger.info("run_agent [conv=%s]", conversation_id)
    result = _graph.invoke(
        {"messages": [{"role": "user", "content": user_input}]},
        {"recursion_limit": 60},
    )

    # 각 노드(에이전트) 발화를 순서대로 수집 (사용자 입력 제외)
    turns = []
    for msg in result.get("messages", []):
        if getattr(msg, "type", None) == "human":
            continue
        content = getattr(msg, "content", "")
        if isinstance(content, str) and content.strip():
            turns.append(
                {"agent": getattr(msg, "name", None) or getattr(msg, "type", None), "content": content}
            )

    if turns:
        answer, agent = turns[-1]["content"], turns[-1]["agent"]
    else:
        answer, agent = "응답을 생성하지 못했어요.", None
    return {"answer": answer, "agent": agent, "turns": turns}

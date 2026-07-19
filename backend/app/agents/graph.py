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


def run_agent(messages: list[dict], conversation_id: str) -> dict:
    """대화 히스토리를 그래프에 넣고 최종 응답을 뽑아낸다.

    Args:
        messages: [{"role": "user"|"assistant", "content": str}, ...] 형태의 히스토리
    Returns: {"answer": str, "agent": str | None, "turns": list}
    """
    logger.info("run_agent [conv=%s] 히스토리 %d턴", conversation_id, len(messages))
    input_len = len(messages)
    result = _graph.invoke(
        {"messages": messages},
        {"recursion_limit": 60},
    )

    # 이번 실행에서 새로 생성된 발화만 수집 (이전 턴 assistant 중복 방지)
    turns = []
    for msg in result.get("messages", [])[input_len:]:
        if getattr(msg, "type", None) == "human":
            continue
        content = getattr(msg, "content", "")
        if isinstance(content, str) and content.strip():
            kwargs = getattr(msg, "additional_kwargs", None) or {}
            turns.append(
                {
                    "agent": getattr(msg, "name", None) or getattr(msg, "type", None),
                    "content": content,
                    "type": kwargs.get("card_type", "text"),
                    "payload": kwargs.get("payload"),
                }
            )

    if turns:
        answer, agent = turns[-1]["content"], turns[-1]["agent"]
    else:
        answer, agent = "응답을 생성하지 못했어요.", None
    return {"answer": answer, "agent": agent, "turns": turns}

"""에이전트 그래프 조립 및 실행.

현재(2단계) 구조:
    START → coordinator ─(정보충분)→ planner → supervisor ⇄ [워커들] → END
                        └(정보부족)──────────────────────────────→ END

라우팅은 각 노드가 반환하는 `Command(goto=...)` 로 결정된다.
"""

from langgraph.graph import START, StateGraph

from app.agents.nodes import (
    booking_node,
    chat_reply_node,
    coordinator_node,
    destination_node,
    faq_node,
    itinerary_node,
    payment_node,
    planner_node,
    recommend_node,
    route_node,
    supervisor_node,
)
from app.agents.state import State
from app.core.logging import get_logger

logger = get_logger(__name__)

# LLM이 자유 텍스트를 생성하는 노드 → 토큰 단위 스트리밍 대상.
# (coordinator/planner의 구조화 출력·라우팅 텍스트는 스트리밍하지 않는다.)
# itinerary는 ReAct 툴 에이전트(create_agent)로 실제 명소를 조회해 생성하므로 토큰 스트리밍 대신
# 완성된 카드로 한 번에 내보낸다(중첩 에이전트 토큰은 노출하지 않음).
STREAM_TOKEN_NODES = {"chat_reply", "faq"}


def build_graph():
    """그래프를 구성해 컴파일한다."""
    builder = StateGraph(State)
    builder.add_node("coordinator", coordinator_node)
    builder.add_node("chat_reply", chat_reply_node)
    builder.add_node("faq", faq_node)
    builder.add_node("recommend", recommend_node)
    builder.add_node("planner", planner_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("destination", destination_node)
    builder.add_node("route", route_node)
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


# 스트리밍 텍스트 노드 → 프론트 렌더 카드 타입
_NODE_CARD_TYPE = {"itinerary": "itinerary", "chat_reply": "text", "faq": "text"}
# 내부 라우팅 메시지(스트림에 노출 안 함)
_SILENT_NODES = {"planner", "supervisor"}


def stream_agent(messages: list[dict], conversation_id: str):
    """그래프를 스트리밍 실행하며 이벤트(dict)를 yield.

    - text_start/text_delta/text_end : 텍스트 노드(chat_reply·faq) 토큰 스트리밍
    - card                           : 완성된 카드(명소·항공·숙소·확정) 한 번에
    - text                           : 비스트리밍 텍스트(coordinator plan 확인 등)
    - turns                          : 전체 턴 누적(DB 저장용, 마지막)
    """
    started: set[str] = set()
    turns: list[dict] = []
    for mode, data in _graph.stream(
        {"messages": messages}, {"recursion_limit": 60}, stream_mode=["messages", "updates"]
    ):
        if mode == "messages":
            chunk, meta = data
            node = meta.get("langgraph_node")
            text = getattr(chunk, "content", "")
            if node in STREAM_TOKEN_NODES and isinstance(text, str) and text:
                if node not in started:
                    started.add(node)
                    yield {"type": "text_start", "node": node, "card_type": _NODE_CARD_TYPE.get(node, "text")}
                yield {"type": "text_delta", "node": node, "text": text}
            continue

        # updates
        for node, update in (data or {}).items():
            if node in _SILENT_NODES or not isinstance(update, dict):
                continue
            for msg in update.get("messages", []) or []:
                if getattr(msg, "type", None) == "human":
                    continue
                content = getattr(msg, "content", "")
                if not (isinstance(content, str) and content.strip()):
                    continue
                kwargs = getattr(msg, "additional_kwargs", None) or {}
                card_type = kwargs.get("card_type", "text")
                turn = {
                    "agent": getattr(msg, "name", None) or node,
                    "content": content,
                    "type": card_type,
                    "payload": kwargs.get("payload"),
                }
                turns.append(turn)
                # 스트리밍 노드인데 토큰이 실제로 흐른 경우만 text_end로 마무리.
                # (mock·빈결과처럼 토큰이 없었으면 완성 content를 카드/텍스트로 폴백 전송)
                if node in STREAM_TOKEN_NODES and node in started:
                    # 최종 content 동봉(스트림 후 덧붙인 출처·후처리까지 프론트에 반영)
                    yield {"type": "text_end", "node": node, "content": content, "payload": kwargs.get("payload")}
                elif card_type != "text":
                    # card_type 을 별도 키로 (이벤트 type="card" 와 충돌 방지)
                    yield {
                        "type": "card",
                        "agent": turn["agent"],
                        "content": content,
                        "card_type": card_type,
                        "payload": kwargs.get("payload"),
                    }
                else:
                    yield {"type": "text", "agent": turn["agent"], "content": content}
    yield {"type": "turns", "turns": turns}

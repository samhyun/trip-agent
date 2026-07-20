"""Coordinator 노드 (+ chat_reply).

coordinator는 사용자 의도를 구조화 출력으로 판단해 결정론적으로 라우팅한다:
- chat : 정보 부족/일반 대화 → chat_reply 노드가 답변을 **토큰 스트리밍**으로 생성(END)
- faq  : 서비스 이용·정책 질문 → faq 노드(RAG)
- plan : 정보 충분 → planner 로 handoff

라우팅 판단(구조화)과 답변 생성(스트리밍)을 분리해, 채팅 답변도 한 글자씩 흐르게 한다.
LLM이 없으면 mock, 구조화 출력이 실패하면 chat 으로 폴백한다.
"""

from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.types import Command
from typing_extensions import TypedDict

from app.agents.llm import get_llm
from app.agents.state import State
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Intent(TypedDict):
    """coordinator의 의도 분류 + 여행 슬롯 추출 (답변 텍스트는 chat_reply가 생성)."""

    intent: Literal["chat", "faq", "plan"]
    destination: str  # 목적지 도시/지역(한국어). 아직 안 정해졌으면 ""
    travelers: int  # 여행 인원 (모르면 0)
    nights: int  # 숙박 박수 (모르면 0)


ROUTER_SYSTEM = """너는 여행 어시스턴트 'Trip Agent'의 라우터야. 사용자 발화의 의도를 판단해라:
- "chat": 목적지가 아직 불명확하거나(예: "동남아 어디 좋아?", "덜 알려진 곳 추천해줘"), 일반 잡담·정보 질문일 때. 목적지가 없으면 여기서 되물어라.
- "faq" : 예약·취소·환불·결제·수하물·체크인 등 서비스 이용/정책 질문일 때.
- "plan": 목적지가 분명하고, 사용자가 명소·일정·동선·항공·숙소를 보여달라/추천/짜줘/예약해달라고 할 때. 기간·인원이 조금 빠져도 목적지만 분명하면 plan으로 진행해라(부족하면 기본값으로 시작해도 된다).
직전에 계획/예약이 끝났고 사용자가 새로운 실행 요청 없이 감사·잡담만 하면 "chat"으로 판단해라.

또한 대화 전체에서 여행 정보를 맥락으로 추출해라(규칙이 아니라 의미로):
- destination: 최종 목적지 도시/지역명(한국어). 여러 번 바뀌면 최근 의도 반영(예: "제주 말고 부산"→"부산", 오타·구어체도 이해). 출발지는 목적지가 아니다. 못 정했으면 "".
- travelers: 인원 수(모르면 0). nights: 숙박 박수(모르면 0)."""

CHAT_SYSTEM = """너는 여행 어시스턴트 'Trip Agent'의 대화 담당이야. 목적지·기간·인원 중 부족한 정보가 있으면
자연스럽게 되묻고, 여행 관련 질문(추천·비교·정보)에는 친절하고 정확하게 답해라. 예약·결제를 대행하는 척은 하지 마라.
읽기 좋게 **마크다운**(짧은 문단, 필요하면 번호·불릿 목록, 핵심은 **굵게**)으로 정리하고, 항상 한국어로 답해라."""

MOCK_REPLY = "여행 계획을 도와드릴게요! 🧳 (지금은 mock 모드예요) 어디로, 며칠 동안, 몇 분이서 떠나세요?"


def coordinator_node(state: State) -> Command:
    """의도 판단 + 슬롯 추출. chat→chat_reply, faq→faq, plan→planner."""
    settings = get_settings()

    if not settings.llm_enabled:
        logger.info("coordinator: LLM 미설정 → mock")
        return Command(update={"messages": [AIMessage(content=MOCK_REPLY, name="coordinator")]}, goto=END)

    trip: dict = {}
    try:
        result = get_llm("coordinator").with_structured_output(Intent).invoke(
            [{"role": "system", "content": ROUTER_SYSTEM}, *state["messages"]]
        )
        intent = result.get("intent", "chat")
        dest = (result.get("destination") or "").strip()
        if dest:
            trip["destination"] = dest
        if result.get("travelers"):
            trip["travelers"] = result["travelers"]
        if result.get("nights"):
            trip["nights"] = result["nights"]
    except Exception as exc:  # 구조화 미지원 등 → 대화 유지
        logger.warning("coordinator: 구조화 출력 실패 → chat 폴백 (%s)", exc)
        intent = "chat"

    merged_trip = {**(state.get("trip") or {}), **trip}
    logger.info("coordinator: intent=%s destination=%r", intent, merged_trip.get("destination"))

    if intent == "faq":
        return Command(update={"trip": merged_trip}, goto="faq")
    if intent == "plan":
        return Command(
            update={
                "messages": [AIMessage(content="네, 바로 계획을 세워볼게요! ✈️", name="coordinator")],
                "trip": merged_trip,
            },
            goto="planner",
        )
    # chat: 답변은 chat_reply 가 토큰 스트리밍으로 생성
    return Command(update={"trip": merged_trip}, goto="chat_reply")


def chat_reply_node(state: State) -> Command:
    """일반 대화/되묻기 답변을 생성(토큰 스트리밍 대상). END로 종료."""
    if not get_settings().llm_enabled:
        return Command(update={"messages": [AIMessage(content=MOCK_REPLY, name="chat_reply")]}, goto=END)
    response = get_llm("coordinator").invoke(
        [{"role": "system", "content": CHAT_SYSTEM}, *state["messages"]]
    )
    content = (response.content or "").strip() or "조금 더 알려주세요. (목적지·기간·인원)"
    return Command(update={"messages": [AIMessage(content=content, name="chat_reply")]}, goto=END)

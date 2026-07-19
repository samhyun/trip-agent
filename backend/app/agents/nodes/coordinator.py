"""Coordinator 노드.

사용자 의도를 구조화 출력(Intent)으로 판단해 결정론적으로 라우팅한다:
- chat : 정보(목적지·기간·인원)가 부족 → 되물으며 대화 유지(END)
- faq  : 서비스 이용·정책 질문 → faq 노드(RAG)
- plan : 정보가 충분 → planner 로 handoff

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
    """coordinator의 의도 분류 + 여행 슬롯 추출 결과."""

    intent: Literal["chat", "faq", "plan"]
    reply: str  # 사용자에게 보여줄 한국어 응답
    destination: str  # 목적지 도시/지역(한국어). 아직 안 정해졌으면 ""
    travelers: int  # 여행 인원 (모르면 0)
    nights: int  # 숙박 박수 (모르면 0)


SYSTEM_PROMPT = """너는 여행 어시스턴트 'Trip Agent'의 대화 담당이야. 사용자 발화의 의도를 판단해라:
- "chat": 여행 계획 요청이지만 목적지·기간·인원 중 빠진 정보가 있어 되물어야 할 때. reply에 자연스러운 후속 질문을 담아라.
- "faq" : 예약·취소·환불·결제·수하물·체크인 등 서비스 이용/정책 질문일 때. (reply는 비워도 된다. FAQ 담당이 답한다.)
- "plan": 목적지·기간·인원이 충분하고, 사용자가 '지금' 여행 계획·일정·예약 진행을 원할 때. reply에 짧은 확인 멘트.
직전에 계획/예약이 이미 끝났고 사용자가 감사·잡담 등 새로운 실행 요청을 하지 않았다면 "chat"으로 판단해라.

또한 지금까지의 대화 전체에서 여행 정보를 추출해라(규칙이 아니라 맥락으로 판단):
- destination: 사용자가 최종적으로 가려는 목적지 도시/지역명(한국어). 여러 번 바뀌면 가장 최근 의도를 반영해라(예: "제주 말고 부산"→"부산", 오타·구어체도 문맥으로 이해). 출발지는 목적지가 아니다. 아직 못 정했으면 "".
- travelers: 여행 인원 수(모르면 0).  nights: 숙박 박수(모르면 0).
지금까지의 대화 맥락을 모두 고려하고, reply는 항상 친절한 한국어로 작성해라."""

MOCK_REPLY = "여행 계획을 도와드릴게요! 🧳 (지금은 mock 모드예요) 어디로, 며칠 동안, 몇 분이서 떠나세요?"


def coordinator_node(state: State) -> Command:
    """사용자 의도를 판단해 chat/faq/plan 으로 라우팅."""
    settings = get_settings()

    if not settings.llm_enabled:
        logger.info("coordinator: LLM 미설정 → mock 응답")
        return Command(
            update={"messages": [AIMessage(content=MOCK_REPLY, name="coordinator")]},
            goto=END,
        )

    llm = get_llm("coordinator")
    trip: dict = {}
    try:
        result = llm.with_structured_output(Intent).invoke(
            [{"role": "system", "content": SYSTEM_PROMPT}, *state["messages"]]
        )
        intent = result.get("intent", "chat")
        reply = (result.get("reply") or "").strip()
        # LLM이 추출한 여행 슬롯 중 유효값만 담는다(0/"" 로 기존 상태를 지우지 않게).
        dest = (result.get("destination") or "").strip()
        if dest:
            trip["destination"] = dest
        if result.get("travelers"):
            trip["travelers"] = result["travelers"]
        if result.get("nights"):
            trip["nights"] = result["nights"]
    except Exception as exc:  # 구조화 미지원 모델 등 → 안전하게 대화 유지
        logger.warning("coordinator: 구조화 출력 실패 → chat 폴백 (%s)", exc)
        intent, reply = "chat", "조금만 더 알려주시겠어요? (목적지·기간·인원)"

    logger.info("coordinator: intent=%s destination=%r", intent, trip.get("destination"))

    if intent == "faq":
        return Command(update={"trip": {**(state.get("trip") or {}), **trip}}, goto="faq")

    if intent == "plan":
        return Command(
            update={
                "messages": [
                    AIMessage(content=reply or "네, 여행 계획을 세워볼게요!", name="coordinator")
                ],
                "trip": {**(state.get("trip") or {}), **trip},
            },
            goto="planner",
        )

    # chat: 정보 부족 → 되묻고 대화 유지
    return Command(
        update={
            "messages": [
                AIMessage(content=reply or "조금 더 알려주세요. (목적지·기간·인원)", name="coordinator")
            ],
            "trip": {**(state.get("trip") or {}), **trip},
        },
        goto=END,
    )

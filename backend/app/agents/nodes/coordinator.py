"""Coordinator 노드.

사용자와 대화하며 여행 요청을 파악한다. 필수 정보(목적지·기간·인원)가 다 모이면
planner로 handoff하고, 아직이면 되물으며 대화를 이어간다(END).

OpenAI 키가 없으면 mock 응답으로 폴백한다(mock-first).
"""

from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.types import Command

from app.agents.llm import get_llm
from app.agents.state import State
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """너는 여행 계획을 도와주는 친절한 한국어 여행 어시스턴트 'Trip Agent'야.
사용자의 여행 요청에서 목적지·기간(날짜)·인원 같은 핵심 정보를 파악하고,
빠진 정보가 있으면 자연스럽게 하나씩 되물어. 답변은 간결하고 다정하게 한국어로 한다.

목적지·기간·인원이 모두 파악되면, 답변 맨 끝에 [HANDOFF] 토큰을 붙여라.

단, 사용자가 여행 계획이 아니라 서비스 이용·정책 질문(예약·취소·환불·결제·수하물·체크인·확정서 등
FAQ성 문의)을 하면, 직접 답하지 말고 답변 맨 끝에 [FAQ] 토큰만 붙여라.
(이 토큰들은 내부 라우팅 신호이며 사용자에게는 보이지 않게 처리된다.)"""

MOCK_REPLY = "여행 계획을 도와드릴게요! 🧳 (지금은 mock 모드예요) 어디로, 며칠 동안, 몇 분이서 떠나세요?"

HANDOFF_TOKEN = "[HANDOFF]"
FAQ_TOKEN = "[FAQ]"


def coordinator_node(state: State) -> Command:
    """사용자 메시지에 응답하고, 정보가 충분하면 planner로 handoff."""
    settings = get_settings()

    if not settings.llm_enabled:
        logger.info("coordinator: LLM 미설정/mock 전용 → mock 응답")
        return Command(
            update={"messages": [AIMessage(content=MOCK_REPLY, name="coordinator")]},
            goto=END,
        )

    llm = get_llm("coordinator")
    response = llm.invoke(
        [{"role": "system", "content": SYSTEM_PROMPT}, *state["messages"]]
    )
    content = response.content

    if FAQ_TOKEN in content:
        logger.info("coordinator: FAQ 질문 감지 → faq 노드")
        return Command(goto="faq")

    if HANDOFF_TOKEN in content:
        clean = content.replace(HANDOFF_TOKEN, "").strip()
        logger.info("coordinator: 정보 충분 → planner handoff")
        return Command(
            update={"messages": [AIMessage(content=clean, name="coordinator")]},
            goto="planner",
        )

    logger.info("coordinator: 정보 부족 → 되묻기 (대화 유지)")
    return Command(
        update={"messages": [AIMessage(content=content, name="coordinator")]},
        goto=END,
    )

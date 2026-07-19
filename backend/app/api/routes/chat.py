"""채팅 라우트.

사용자 메시지를 받아 에이전트 그래프에 전달하고 응답을 반환한다.
그래프 실행 로직은 `app.agents.graph.run_agent` 에 위임한다.
"""

import uuid

from fastapi import APIRouter

from app.agents.graph import run_agent
from app.api.schemas import ChatRequest, ChatResponse
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """사용자 메시지 → 에이전트 응답."""
    conversation_id = request.conversation_id or str(uuid.uuid4())
    logger.info("chat 요청 [conv=%s]: %s", conversation_id, request.message)

    result = run_agent(request.message, conversation_id=conversation_id)

    return ChatResponse(
        answer=result["answer"],
        turns=result.get("turns", []),
        conversation_id=conversation_id,
        agent=result.get("agent"),
    )

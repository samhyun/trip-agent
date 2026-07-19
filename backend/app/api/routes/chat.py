"""채팅 라우트.

사용자 메시지를 받아 에이전트 그래프에 전달하고 응답을 반환한다.
대화 히스토리를 DB(messages)로 유지해 멀티턴 대화를 지원한다.
동기 라우트라 FastAPI가 threadpool에서 실행 → 이벤트 루프를 막지 않는다.
"""

from fastapi import APIRouter

from app.agents.graph import run_agent
from app.api.schemas import ChatRequest, ChatResponse
from app.core.logging import get_logger
from app.db.base import SessionLocal
from app.services import conversation_service as convs

logger = get_logger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """사용자 메시지 → 에이전트 응답 (히스토리 DB 유지)."""
    db = SessionLocal()
    try:
        conv = convs.get_or_create_conversation(db, request.conversation_id)
        logger.info("chat [conv=%s] 입력 %d자", conv.id, len(request.message))

        history = convs.load_history(db, conv.id)
        history.append({"role": "user", "content": request.message})
        convs.save_message(db, conv.id, "user", request.message)

        result = run_agent(history, str(conv.id))

        convs.save_message(
            db, conv.id, "assistant", result["answer"], agent=result.get("agent")
        )
        db.commit()

        return ChatResponse(
            answer=result["answer"],
            turns=result.get("turns", []),
            conversation_id=str(conv.id),
            agent=result.get("agent"),
        )
    except Exception:
        db.rollback()
        logger.exception("chat 처리 실패")
        raise
    finally:
        db.close()

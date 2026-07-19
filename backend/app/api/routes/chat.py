"""채팅 라우트.

사용자 메시지를 받아 에이전트 그래프에 전달하고 응답을 반환한다.
대화 히스토리를 DB(messages)로 유지해 멀티턴 대화를 지원한다.
동기 라우트라 FastAPI가 threadpool에서 실행 → 이벤트 루프를 막지 않는다.
"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agents.graph import run_agent, stream_agent
from app.api.deps import get_current_user_optional
from app.api.schemas import ChatRequest, ChatResponse
from app.core.logging import get_logger
from app.db.base import SessionLocal
from app.db.models import User
from app.services import conversation_service as convs
from app.services import trip_service

logger = get_logger(__name__)
router = APIRouter()


def _sse(event: dict) -> str:
    """SSE 한 줄 (data: {json}\\n\\n)."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: User | None = Depends(get_current_user_optional),
) -> ChatResponse:
    """사용자 메시지 → 에이전트 응답 (히스토리 DB 유지). 로그인 시 대화가 유저에 연결됨."""
    db = SessionLocal()
    user_id = current_user.id if current_user else None
    try:
        conv = convs.get_or_create_conversation(db, request.conversation_id, user_id)
        logger.info("chat [conv=%s user=%s] 입력 %d자", conv.id, user_id, len(request.message))

        history = convs.load_history(db, conv.id)
        history.append({"role": "user", "content": request.message})
        convs.save_message(db, conv.id, "user", request.message)

        result = run_agent(history, str(conv.id))

        convs.save_message(
            db, conv.id, "assistant", result["answer"], agent=result.get("agent")
        )
        # 결제 완료 시 여행/예약을 저장(로그인 유저에 연결). 실패해도 채팅 응답은 진행.
        try:
            with db.begin_nested():
                trip_service.record_booking(
                    db, conv.id, user_id, result.get("turns", []),
                    "\n".join(m["content"] for m in history),
                )
        except Exception:
            logger.exception("여행 영속화 실패 (무시)")
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


@router.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    current_user: User | None = Depends(get_current_user_optional),
) -> StreamingResponse:
    """스트리밍 채팅 (SSE) — 텍스트는 토큰 단위, 카드는 완성 후 한 번에."""
    user_id = current_user.id if current_user else None

    def generate():
        # 1) 짧은 트랜잭션: 대화 확보 + 사용자 메시지 저장 후 세션을 닫는다(스트림 동안 커넥션 미점유).
        db = SessionLocal()
        try:
            conv = convs.get_or_create_conversation(db, request.conversation_id, user_id)
            conv_id = conv.id
            history = convs.load_history(db, conv_id)
            history.append({"role": "user", "content": request.message})
            convs.save_message(db, conv_id, "user", request.message)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("chat_stream 준비 실패")
            db.close()
            yield _sse({"type": "error", "message": "응답 생성 중 오류가 발생했어요."})
            return
        finally:
            db.close()

        logger.info("chat_stream [conv=%s user=%s] 입력 %d자", conv_id, user_id, len(request.message))
        yield _sse({"type": "meta", "conversation_id": str(conv_id)})

        # 2) 스트리밍 (DB 미점유)
        turns: list[dict] = []
        try:
            for ev in stream_agent(history, str(conv_id)):
                if ev.get("type") == "turns":
                    turns = ev.get("turns", [])
                    continue
                yield _sse(ev)
        except Exception:
            logger.exception("chat_stream 스트리밍 실패")
            yield _sse({"type": "error", "message": "응답 생성 중 오류가 발생했어요."})
            return

        # 3) 짧은 트랜잭션: 응답 저장 + 결제 시 여행/예약 영속화
        db = SessionLocal()
        try:
            answer = turns[-1]["content"] if turns else ""
            agent = turns[-1]["agent"] if turns else None
            if answer:
                convs.save_message(db, conv_id, "assistant", answer, agent=agent)
            try:
                with db.begin_nested():
                    trip_service.record_booking(
                        db, conv_id, user_id, turns, "\n".join(m["content"] for m in history)
                    )
            except Exception:
                logger.exception("여행 영속화 실패 (무시)")
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("chat_stream 응답 저장 실패")
        finally:
            db.close()
        yield _sse({"type": "done", "conversation_id": str(conv_id)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )

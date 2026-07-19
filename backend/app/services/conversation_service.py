"""대화 세션·메시지 영속 (DB).

`messages` 테이블에 대화를 저장하고, 이전 히스토리를 로드해 멀티턴 대화를 지원한다.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Message


def get_or_create_conversation(db: Session, conversation_id: str | None) -> Conversation:
    """conversation_id가 유효하면 조회, 아니면 새 세션을 만든다."""
    if conversation_id:
        try:
            conv = db.get(Conversation, uuid.UUID(conversation_id))
            if conv:
                return conv
        except (ValueError, TypeError):
            pass
    conv = Conversation()
    db.add(conv)
    db.flush()
    return conv


def load_history(db: Session, conversation_id: uuid.UUID) -> list[dict]:
    """이전 대화(user/assistant)를 LLM 입력용 리스트로 반환한다."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq)
    )
    return [{"role": m.role, "content": m.content} for m in db.scalars(stmt)]


def save_message(
    db: Session,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    agent: str | None = None,
    type_: str = "text",
    payload: dict | None = None,
) -> Message:
    """메시지 1건을 저장한다 (커밋은 호출자 책임)."""
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        agent=agent,
        type=type_,
        payload=payload,
    )
    db.add(msg)
    return msg

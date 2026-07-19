"""대화 세션·메시지 영속 (DB).

`messages` 테이블에 대화를 저장하고, 이전 히스토리를 로드해 멀티턴 대화를 지원한다.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Message


def get_or_create_conversation(
    db: Session, conversation_id: str | None, user_id: uuid.UUID | None = None
) -> Conversation:
    """conversation_id가 유효하면 조회, 아니면 새 세션을 만든다.

    소유권 검증(IDOR 방지): 대화에 주인(user_id)이 있고 요청 유저와 다르면 반환하지 않고
    새 대화를 만든다. 익명으로 시작한 대화는 도중 로그인 시 그 유저에게 귀속시킨다.
    """
    if conversation_id:
        try:
            conv = db.get(Conversation, uuid.UUID(conversation_id))
        except (ValueError, TypeError):
            conv = None
        # 타 유저 소유 대화면 접근 불가 → 새 대화로 폴백
        if conv is not None and conv.user_id is not None and conv.user_id != user_id:
            conv = None
        if conv is not None:
            if user_id and conv.user_id is None:  # 익명 대화 → 로그인 유저 귀속
                conv.user_id = user_id
            return conv
    conv = Conversation(user_id=user_id)
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

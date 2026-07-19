"""API 요청/응답 Pydantic 스키마."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """사용자 채팅 요청."""

    message: str = Field(..., description="사용자 입력 메시지")
    conversation_id: str | None = Field(
        default=None, description="세션 유지용 대화 ID (없으면 새 대화)"
    )


class AgentTurn(BaseModel):
    """대화 흐름 중 한 노드(에이전트)의 발화."""

    agent: str | None = Field(default=None, description="노드/에이전트 이름")
    content: str = Field(..., description="해당 노드의 발화 내용")


class ChatResponse(BaseModel):
    """에이전트 채팅 응답."""

    answer: str = Field(..., description="에이전트 최종 응답")
    turns: list[AgentTurn] = Field(
        default_factory=list, description="노드별 발화 순서 (coordinator·워커 등 전체)"
    )
    conversation_id: str = Field(..., description="대화 ID")
    agent: str | None = Field(default=None, description="최종 응답을 낸 노드 이름")


class HealthResponse(BaseModel):
    """헬스 체크 응답."""

    status: str = "ok"

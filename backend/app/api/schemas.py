"""API 요청/응답 Pydantic 스키마."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """사용자 채팅 요청."""

    message: str = Field(..., min_length=1, max_length=2000, description="사용자 입력 메시지")
    conversation_id: str | None = Field(
        default=None, description="세션 유지용 대화 ID (없으면 새 대화)"
    )


class AgentTurn(BaseModel):
    """대화 흐름 중 한 노드(에이전트)의 발화 (프론트 렌더 계약)."""

    agent: str | None = Field(default=None, description="노드/에이전트 이름")
    content: str = Field(..., description="발화 내용(텍스트)")
    type: str = Field(default="text", description="렌더 카드 타입 (destination_carousel 등)")
    payload: dict | None = Field(default=None, description="카드 데이터")


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


# ----- 인증 -----

class RegisterRequest(BaseModel):
    """회원가입 요청."""

    email: str = Field(..., min_length=3, max_length=255, description="이메일")
    password: str = Field(..., min_length=6, max_length=128, description="비밀번호(6자 이상)")
    name: str = Field(..., min_length=1, max_length=80, description="이름")


class LoginRequest(BaseModel):
    """로그인 요청."""

    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class UserResponse(BaseModel):
    """유저 공개 정보."""

    id: str
    email: str
    name: str


class TokenResponse(BaseModel):
    """로그인/회원가입 성공 응답 (액세스 토큰 + 유저)."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ----- 내 여행/예약 -----

class BookingResponse(BaseModel):
    """예약 항목."""

    id: str
    type: str  # flight / hotel / activity
    title: str | None = None
    provider: str
    status: str
    price: float | None = None


class TripResponse(BaseModel):
    """저장된 여행(결제 완료). 예약 항목·합계 포함."""

    id: str
    title: str | None = None
    destinations: list | None = None
    travelers: int
    status: str
    total: float
    confirmation_no: str | None = None
    created_at: str
    bookings: list[BookingResponse] = Field(default_factory=list)

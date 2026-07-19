"""인증 라우트 — 회원가입 · 로그인 · 현재 유저."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.core.logging import get_logger
from app.db.base import get_db
from app.db.models import User
from app.services import auth_service

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _user_response(u: User) -> UserResponse:
    return UserResponse(id=str(u.id), email=u.email, name=u.name)


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """회원가입 → 액세스 토큰 발급."""
    try:
        user = auth_service.register_user(db, req.email, req.password, req.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    logger.info("회원가입 [user=%s]", user.id)
    return TokenResponse(access_token=auth_service.create_access_token(user.id), user=_user_response(user))


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """로그인 → 액세스 토큰 발급."""
    user = auth_service.authenticate_user(db, req.email, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )
    logger.info("로그인 [user=%s]", user.id)
    return TokenResponse(access_token=auth_service.create_access_token(user.id), user=_user_response(user))


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    """현재 로그인 유저 정보."""
    return _user_response(user)

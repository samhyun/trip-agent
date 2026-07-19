"""API 의존성 — 현재 로그인 유저 해석 (Bearer 토큰).

get_current_user_optional : 토큰 없거나 무효면 None (비로그인 허용 라우트용)
get_current_user          : 없으면 401 (로그인 필수 라우트용)
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import User
from app.services import auth_service

_bearer = HTTPBearer(auto_error=False)


def get_current_user_optional(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """토큰이 있으면 유저를, 없거나 무효면 None."""
    if not creds:
        return None
    user_id = auth_service.decode_token(creds.credentials)
    if not user_id:
        return None
    return auth_service.get_user(db, user_id)


def get_current_user(user: User | None = Depends(get_current_user_optional)) -> User:
    """로그인 필수. 미인증이면 401."""
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다.")
    return user

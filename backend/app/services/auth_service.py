"""인증 서비스 — 비밀번호 해싱(bcrypt) + JWT 토큰 + 유저 조회/생성.

라우트/의존성이 이 모듈을 통해 회원가입·로그인·현재 유저 해석을 수행한다.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import User


def _prehash(plain: str) -> bytes:
    """bcrypt 72바이트 한계 회피: SHA-256 hexdigest(64 ASCII)로 정규화 후 해싱.

    긴/멀티바이트 비밀번호의 조용한 절단(앞 72바이트만 비교)을 막는다.
    """
    return hashlib.sha256(plain.encode("utf-8")).hexdigest().encode("ascii")


def _norm_email(email: str) -> str:
    """이메일 정규화(공백 제거 + 소문자). 공백/대소문자 차이로 중복 계정 방지."""
    return email.strip().lower()


def hash_password(plain: str) -> str:
    """평문 비밀번호 → bcrypt 해시(SHA-256 프리해시)."""
    return bcrypt.hashpw(_prehash(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """평문 vs 해시 대조."""
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: uuid.UUID) -> str:
    """유저 id로 JWT 액세스 토큰 발급 (sub=user_id, exp)."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=s.jwt_expire_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> uuid.UUID | None:
    """토큰 검증 후 user_id 반환. 무효/만료면 None."""
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# ----- 유저 조회/생성 -----

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == _norm_email(email)))


def get_user(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def register_user(db: Session, email: str, password: str, name: str) -> User:
    """새 유저 생성. 이메일 중복이면 ValueError(사전 조회 + DB 유니크 경쟁조건 모두 처리)."""
    email = _norm_email(email)
    if get_user_by_email(db, email):
        raise ValueError("이미 가입된 이메일입니다.")
    user = User(email=email, hashed_password=hash_password(password), name=name.strip())
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # 동시 가입 경쟁조건 → 유니크 위반
        db.rollback()
        raise ValueError("이미 가입된 이메일입니다.") from exc
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """이메일+비밀번호 검증. 실패 시 None."""
    user = get_user_by_email(db, email)
    if user and verify_password(password, user.hashed_password):
        return user
    return None

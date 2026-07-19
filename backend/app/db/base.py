"""데이터베이스 엔진·세션·Base (SQLAlchemy 2.0, Postgres+pgvector)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """모든 ORM 모델의 베이스."""


engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    """요청 스코프 DB 세션 (FastAPI 의존성용)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

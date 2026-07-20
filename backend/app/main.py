"""FastAPI 진입점.

`uvicorn app.main:app` 으로 기동한다. CORS 허용 + 라우터 등록 + 헬스 체크.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth_router, chat_router, details_router, trips_router
from app.api.schemas import HealthResponse
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)
settings = get_settings()

app = FastAPI(title="Trip Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(trips_router)
app.include_router(details_router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """헬스 체크."""
    return HealthResponse()


if settings.jwt_secret == "dev-secret-change-me":
    logger.warning("JWT_SECRET이 기본 개발키입니다. 운영 배포 시 .env에서 반드시 교체하세요.")

logger.info(
    "Trip Agent 시작 (모델=%s, OpenAI키=%s, mock전용=%s)",
    settings.openai_model,
    settings.has_openai,
    settings.use_mock_only,
)

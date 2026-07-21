"""FastAPI 진입점.

`uvicorn app.main:app` 으로 기동한다. CORS 허용 + 라우터 등록 + 헬스 체크.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """미처리 예외 → 일관된 500 응답 (내부 상세는 로그에만, 클라이언트엔 노출 안 함).

    HTTPException(401·404 등)은 FastAPI 기본 핸들러가 처리하므로 여기 오지 않는다.
    스트리밍 라우트는 자체적으로 SSE error 이벤트를 내보내므로 영향받지 않는다.
    """
    logger.exception("처리되지 않은 예외 [%s %s]", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요."},
    )


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

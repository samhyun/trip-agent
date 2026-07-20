"""API 라우트 모듈."""

from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.details import router as details_router
from app.api.routes.trips import router as trips_router

__all__ = ["auth_router", "chat_router", "details_router", "trips_router"]

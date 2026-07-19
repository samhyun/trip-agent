"""내 여행/예약 조회 라우트 (로그인 필수)."""

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import BookingResponse, TripResponse
from app.db.base import get_db
from app.db.models import Trip, User
from app.services import trip_service

router = APIRouter(prefix="/me", tags=["me"])


def _trip_response(trip: Trip) -> TripResponse:
    # 재결제 시 각 Payment는 전액 재결제이므로 합산이 아니라 최신 결제를 기준으로 한다.
    latest = max(trip.payments, key=lambda p: p.created_at, default=None)
    total = latest.amount if latest else Decimal(0)
    confirmation_no = latest.confirmation_no if latest else None
    return TripResponse(
        id=str(trip.id),
        title=trip.title,
        destinations=trip.destinations,
        travelers=trip.travelers,
        status=trip.status,
        total=float(total),
        confirmation_no=confirmation_no,
        created_at=trip.created_at.isoformat(),
        bookings=[
            BookingResponse(
                id=str(b.id),
                type=b.type,
                title=b.title,
                provider=b.provider,
                status=b.status,
                price=float(b.price) if b.price is not None else None,
            )
            for b in trip.bookings
        ],
    )


@router.get("/trips", response_model=list[TripResponse])
def my_trips(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[TripResponse]:
    """내 여행(결제 완료) 목록 — 최신순."""
    return [_trip_response(t) for t in trip_service.list_user_trips(db, user.id)]

"""여행·예약 영속화.

결제(confirmation)가 완료되면 대화에서 여행/예약/결제를 DB에 저장하고 로그인 유저에 연결한다.
백엔드는 선택 상태를 갖지 않으므로, 예약한 항공/숙소는 대화 히스토리의 선택 발화에서
best-effort로 파싱한다(프론트가 보내는 "…항공편으로 예약할게요" / "…숙소로 예약할게요").
"""

import re
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Booking, Payment, Trip
from app.services import travel_service as ts

logger = get_logger(__name__)

# 프론트 선택 발화 패턴 (App.jsx dispatch). 라인 경계로 다른 메시지 침범 방지.
_FLIGHT_RE = re.compile(r"([^\n]{1,40}?)\s+(\d{1,2}:\d{2})\s*항공편으로\s*예약")
_HOTEL_RE = re.compile(r"([^\n]{1,60}?)\s*숙소로\s*예약")
_TOTAL_RE = re.compile(r"총\s*([\d,]+)\s*원")  # 결제 발화의 실제 선택 합계


def _to_decimal(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


def _confirmation_turn(turns: list) -> dict | None:
    """turns에서 결제 확정(confirmation) 카드를 찾는다."""
    for t in turns:
        t = t if isinstance(t, dict) else getattr(t, "__dict__", {})
        if t.get("type") == "confirmation":
            return t
    return None


def _parse_selected_bookings(history_text: str) -> list[dict]:
    """대화 히스토리에서 선택한 항공/숙소를 예약 항목으로 추출.

    재선택이 있을 수 있으므로 **가장 마지막(최신) 선택**을 사용한다.
    """
    items = []
    flights = _FLIGHT_RE.findall(history_text)
    if flights:
        air, dep = flights[-1]
        items.append({"type": "flight", "title": f"{air.strip()} {dep}"})
    hotels = _HOTEL_RE.findall(history_text)
    if hotels:
        items.append({"type": "hotel", "title": hotels[-1].strip()})
    return items


def record_booking(
    db: Session,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID | None,
    turns: list,
    history_text: str,
) -> Trip | None:
    """결제 확정이 있으면 Trip·Booking·Payment를 저장(대화당 Trip 1개, 재결제 시 결제만 추가)."""
    conf = _confirmation_turn(turns)
    if not conf:
        return None
    payload = conf.get("payload") or {}

    cities = ts.find_cities(history_text)
    travelers = ts.parse_people(history_text)

    # 대화당 Trip 1개 (get-or-create)
    trip = db.scalar(select(Trip).where(Trip.conversation_id == conversation_id))
    if trip is None:
        trip = Trip(conversation_id=conversation_id)
        db.add(trip)
    trip.user_id = user_id
    trip.destinations = cities or None
    trip.travelers = travelers
    trip.title = payload.get("title") or ((" + ".join(cities) + " 여행") if cities else "여행")
    trip.status = "booked"
    db.flush()

    # 예약 항목(항공/숙소)은 최초 1회만 기록 (재결제 중복 방지)
    has_booking = db.scalar(select(Booking.id).where(Booking.trip_id == trip.id))
    if not has_booking:
        for item in _parse_selected_bookings(history_text):
            db.add(
                Booking(
                    trip_id=trip.id,
                    user_id=user_id,
                    type=item["type"],
                    title=item["title"],
                    provider="api",
                    status="confirmed",
                )
            )

    # 결제 금액: 결제 발화의 실제 선택 합계를 우선(화면 표시와 일치). 일정 예산표 등 앞선 '총 …원'에
    # 오염되지 않도록 **마지막** 일치값을 쓴다. 없으면 확정서 추정값.
    totals = _TOTAL_RE.findall(history_text)
    amount = _to_decimal(totals[-1].replace(",", "")) if totals else _to_decimal(payload.get("total"))
    # 결제 (confirmation_no 유니크)
    db.add(
        Payment(
            trip_id=trip.id,
            user_id=user_id,
            amount=amount,
            confirmation_no=payload.get("code"),
            method="dummy",
            status="paid",
        )
    )
    db.flush()
    logger.info("여행 저장 [trip=%s user=%s cities=%s]", trip.id, user_id, cities)
    return trip


def list_user_trips(db: Session, user_id: uuid.UUID) -> list[Trip]:
    """유저의 여행 목록(최신순). bookings·payments 관계 포함."""
    return list(
        db.scalars(
            select(Trip).where(Trip.user_id == user_id).order_by(Trip.created_at.desc())
        )
    )

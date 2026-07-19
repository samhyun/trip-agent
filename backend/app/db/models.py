"""ORM 모델 (대화·여행·예약·결제).

관계:
    conversations 1─N messages
    conversations 1─N trips 1─N bookings   (항공/숙소/액티비티가 각각 별도 row)
                           trips 1─N payments
FAQ 벡터는 pgvector(langchain 관리 테이블)로 별도 저장한다.

도메인 무결성은 CHECK 제약으로 DB 레벨에서 보장한다.
(payment↔booking↔trip 소속 정합성은 저장 로직에서 추가 검증한다.)
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Conversation(Base):
    """대화 세션."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    trips: Mapped[list["Trip"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    """대화 발화 (프론트 렌더 계약: type/payload)."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role in ('user','assistant')", name="ck_messages_role"),
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user / assistant
    agent: Mapped[str | None] = mapped_column(String(40))  # coordinator / itinerary / ...
    type: Mapped[str] = mapped_column(String(40), default="text")  # 프론트 카드 타입
    content: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict | None] = mapped_column(JSONB)  # 리치카드 데이터
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Trip(Base):
    """여행 계획 (우측 '내 여행' 패널의 기본 정보)."""

    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("travelers > 0", name="ck_trips_travelers_pos"),
        CheckConstraint(
            "start_date is null or end_date is null or start_date <= end_date",
            name="ck_trips_dates",
        ),
        CheckConstraint(
            "status in ('planning','booked','completed')", name="ck_trips_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(120))
    destinations: Mapped[list | None] = mapped_column(JSONB)  # ["제주"] / ["세부","보홀"]
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    travelers: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="planning")  # planning/booked/completed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="trips")
    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )


class Booking(Base):
    """예약 항목 (항공/숙소/액티비티가 각각 별도 row). 개별 예약·취소 가능."""

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("type in ('flight','hotel','activity')", name="ck_bookings_type"),
        CheckConstraint(
            "status in ('pending','confirmed','cancelled')", name="ck_bookings_status"
        ),
        CheckConstraint("price is null or price >= 0", name="ck_bookings_price_nonneg"),
        Index("ix_bookings_trip_type", "trip_id", "type"),
        Index("ix_bookings_trip_status", "trip_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # flight / hotel / activity
    provider: Mapped[str] = mapped_column(String(40), default="mock")  # duffel/liteapi/tourapi/mock
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/confirmed/cancelled
    title: Mapped[str | None] = mapped_column(String(200))
    details: Mapped[dict | None] = mapped_column(JSONB)  # 항공편/호텔 등 상세
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KRW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    trip: Mapped["Trip"] = relationship(back_populates="bookings")


class Payment(Base):
    """더미 결제. booking_id가 있으면 개별 항목 결제, 없으면 여행 일괄 결제."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_payments_amount_nonneg"),
        CheckConstraint("status in ('paid','failed')", name="ck_payments_status"),
        UniqueConstraint("confirmation_no", name="uq_payments_confirmation_no"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(20), default="dummy")
    status: Mapped[str] = mapped_column(String(20), default="paid")  # paid / failed
    confirmation_no: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trip: Mapped["Trip"] = relationship(back_populates="payments")

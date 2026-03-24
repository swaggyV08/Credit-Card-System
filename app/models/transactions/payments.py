"""
Transaction Processing System — Payment & Refund Models
Tables: payments, refunds
"""
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal

from sqlalchemy import String, Numeric, Boolean, DateTime, Date, Text, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base_class import Base
from app.models.transactions.enums import PaymentStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False, index=True
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    status: Mapped[str] = mapped_column(
        String(15), nullable=False, default=PaymentStatus.PENDING.value
    )

    payment_source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    allocation_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_payment_card_status", "card_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Payment {self.id} amount={self.amount} status={self.status}>"


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    original_txn_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True
    )
    refund_txn_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    partial: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<Refund {self.id} amount={self.amount} partial={self.partial}>"

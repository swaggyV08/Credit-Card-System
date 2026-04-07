"""
Transaction Processing System — Payment & Refund Models
Payment model moved to app/models/billing.py for Week 5 billing system.
Refund model remains here.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import String, Numeric, Boolean, DateTime, Date, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base_class import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# Re-export Payment from billing for backward compatibility
from app.models.billing import Payment  # noqa: E402, F401


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

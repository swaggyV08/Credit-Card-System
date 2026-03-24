"""
Transaction Processing System — Fee Model
Table: fees
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import String, Numeric, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base_class import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Fee(Base):
    __tablename__ = "fees"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False, index=True
    )

    fee_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    waived: Mapped[bool] = mapped_column(Boolean, default=False)
    waiver_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    waived_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    linked_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_fee_card_type", "card_id", "fee_type"),
    )

    def __repr__(self) -> str:
        return f"<Fee {self.id} type={self.fee_type} amount={self.amount}>"

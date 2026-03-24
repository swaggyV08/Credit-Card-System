"""
Transaction Processing System — Clearing Models
Tables: clearing_batches, clearing_records
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import String, Numeric, Boolean, DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base_class import Base
from app.models.transactions.enums import ClearingBatchStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class ClearingBatch(Base):
    __tablename__ = "clearing_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    network: Mapped[str] = mapped_column(String(20), nullable=False)
    file_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ClearingBatchStatus.RECEIVED.value
    )

    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    exception_count: Mapped[int] = mapped_column(Integer, default=0)
    force_post_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    records: Mapped[list["ClearingRecord"]] = relationship(back_populates="batch", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ClearingBatch {self.id} network={self.network} status={self.status}>"


class ClearingRecord(Base):
    __tablename__ = "clearing_records"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True, index=True
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clearing_batches.id"), nullable=False, index=True
    )

    clearing_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    interchange_fee: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, default=Decimal("0"))
    network_fee: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, default=Decimal("0"))
    clearing_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    force_post: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    batch: Mapped["ClearingBatch"] = relationship(back_populates="records")

    def __repr__(self) -> str:
        return f"<ClearingRecord {self.id} amount={self.clearing_amount}>"

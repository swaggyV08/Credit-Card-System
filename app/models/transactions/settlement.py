"""
Transaction Processing System — Settlement Models
Tables: settlement_runs, settlement_records
"""
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal

from sqlalchemy import String, Numeric, DateTime, Date, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base_class import Base
from app.models.transactions.enums import SettlementRunStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class SettlementRun(Base):
    __tablename__ = "settlement_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    network: Mapped[str] = mapped_column(String(20), nullable=False)
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SettlementRunStatus.PENDING.value
    )

    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    cards_settled: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    records: Mapped[list["SettlementRecord"]] = relationship(back_populates="run", lazy="selectin")

    def __repr__(self) -> str:
        return f"<SettlementRun {self.id} date={self.settlement_date} status={self.status}>"


class SettlementRecord(Base):
    __tablename__ = "settlement_records"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    settlement_run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("settlement_runs.id"), nullable=False, index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True
    )

    net_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    interchange_earned: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"))
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    run: Mapped["SettlementRun"] = relationship(back_populates="records")

    def __repr__(self) -> str:
        return f"<SettlementRecord {self.id} amount={self.net_amount}>"

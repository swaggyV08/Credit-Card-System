"""
Transaction Processing System — Statement Models
Tables: statements, statement_line_items
"""
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal

from sqlalchemy import String, Numeric, Boolean, DateTime, Date, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base_class import Base
from app.models.transactions.enums import StatementStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Statement(Base):
    __tablename__ = "statements"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False, index=True
    )

    cycle_start: Mapped[date] = mapped_column(Date, nullable=False)
    cycle_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(15), nullable=False, default=StatementStatus.OPEN.value
    )

    opening_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    closing_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    total_purchases: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    total_cash_advances: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    total_fees: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    total_credits: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))

    minimum_due: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    payment_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fully_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    min_paid: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    line_items: Mapped[list["StatementLineItem"]] = relationship(back_populates="statement", lazy="selectin")

    __table_args__ = (
        Index("ix_statement_card_cycle", "card_id", "cycle_start", "cycle_end"),
    )

    def __repr__(self) -> str:
        return f"<Statement {self.id} {self.cycle_start}-{self.cycle_end} status={self.status}>"


class StatementLineItem(Base):
    __tablename__ = "statement_line_items"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    statement_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("statements.id"), nullable=False, index=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True
    )

    line_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    line_date: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    statement: Mapped["Statement"] = relationship(back_populates="line_items")

    def __repr__(self) -> str:
        return f"<StatementLineItem {self.id} type={self.line_type} amount={self.amount}>"

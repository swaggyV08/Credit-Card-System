"""
Billing System Models — Week 5
Tables: statements, statement_line_items, payments, fraud_flags, idempotency_keys

All billing-related models consolidated here. Enums imported from
app.models.transactions.enums for consistency with the existing codebase.
"""
import uuid
import enum
from datetime import datetime, date, timezone
from decimal import Decimal

from sqlalchemy import (
    String, Integer, Numeric, Boolean, DateTime, Date,
    ForeignKey, Index, JSON, Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base_class import Base
from app.models.transactions.enums import (
    StatementStatus, LineItemType, PaymentStatus, PaymentSource,
)


# ─── helpers ───────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ─── Billing-specific enums (not in transactions) ─────
class FraudRule(str, enum.Enum):
    """Fraud detection rule identifiers."""
    VELOCITY = "VELOCITY"
    AMOUNT_SPIKE = "AMOUNT_SPIKE"
    UNUSUAL_HOUR = "UNUSUAL_HOUR"


class FraudAction(str, enum.Enum):
    """Fraud rule outcome actions."""
    DECLINED = "DECLINED"
    REVIEW = "REVIEW"


# ═══════════════════════════════════════════════════════
# BILL
# ═══════════════════════════════════════════════════════
class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("credit_account.id"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="GENERATED",
    )
    billing_cycle_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    billing_cycle_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    previous_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.0"))
    new_charges: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.0"))
    foreign_fees_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.0"))
    interest: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.0"))
    other_fees: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.0"))
    credits: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.0"))

    total_due: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    min_payment_due: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    transactions_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    statements: Mapped[list["Statement"]] = relationship(back_populates="bill")
    fees: Mapped[list["Fee"]] = relationship(back_populates="bill")

    def __repr__(self) -> str:
        return f"<Bill {self.id} cycle_end={self.billing_cycle_end} status={self.status}>"


# ═══════════════════════════════════════════════════════
# STATEMENT
# ═══════════════════════════════════════════════════════
class Statement(Base):
    __tablename__ = "statements"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("credit_account.id"), nullable=False,
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False, index=True,
    )

    bill_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("bills.id"), nullable=False, index=True
    )
    billing_cycle: Mapped[str] = mapped_column(String(7), nullable=False) # YYYY-MM
    
    total_charges: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    total_foreign_fees: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    interest_charged: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    total_due: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    min_payment_due: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    bill: Mapped["Bill"] = relationship(back_populates="statements")
    line_items: Mapped[list["StatementLineItem"]] = relationship(back_populates="statement", lazy="selectin")

    __table_args__ = (
        Index("ix_stmt_card_cycle", "card_id", "billing_cycle"),
    )

    def __repr__(self) -> str:
        return f"<Statement {self.id} cycle={self.billing_cycle}>"


# ═══════════════════════════════════════════════════════
# STATEMENT LINE ITEM
# ═══════════════════════════════════════════════════════
class StatementLineItem(Base):
    __tablename__ = "statement_line_items"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    statement_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("statements.id"), nullable=False, index=True,
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True,
    )

    line_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    # Relationships
    statement: Mapped["Statement"] = relationship(back_populates="line_items")

    def __repr__(self) -> str:
        return f"<StatementLineItem {self.id} type={self.line_type} amount={self.amount}>"


# ═══════════════════════════════════════════════════════
# PAYMENT (with waterfall allocation fields)
# ═══════════════════════════════════════════════════════
class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    credit_account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("credit_account.id"), nullable=False,
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False, index=True,
    )
    bill_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("bills.id"), nullable=True,
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    payment_type: Mapped[str] = mapped_column(String(20), nullable=False, default="FULL")
    payment_source: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_no: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(15), nullable=False, default=PaymentStatus.PENDING.value,
    )

    # Waterfall allocation (H4)
    allocated_fees: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0"),
    )
    allocated_interest: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0"),
    )
    allocated_cash_advance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0"),
    )
    allocated_purchases: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0"),
    )
    remaining_balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0"),
    )
    is_partial: Mapped[bool] = mapped_column(Boolean, default=False)

    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    __table_args__ = (
        Index("ix_payment_card_status", "card_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Payment {self.id} amount={self.amount} status={self.status}>"








# ═══════════════════════════════════════════════════════
# IDEMPOTENCY KEY
# ═══════════════════════════════════════════════════════
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False,
    )
    response_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<IdempotencyKey {self.key} expires_at={self.expires_at}>"

"""
Transaction Processing System — Core Transaction & Hold & Audit Models
Tables: transactions, credit_holds, audit_log
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.transactions.disputes import Dispute

from sqlalchemy import (
    String, Numeric, Boolean, DateTime, Text, ForeignKey, Index, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base_class import Base
from app.models.transactions.enums import (
    TransactionType, TransactionStatus, POSEntryMode, RiskTier,
    HoldStatus, AuditAction,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# =====================================================
# TRANSACTIONS TABLE
# =====================================================
class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("credit_account.id"), nullable=False, index=True
    )

    # Financial
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=TransactionStatus.PENDING_AUTHORIZATION.value)

    # Merchant
    merchant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    merchant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    merchant_category_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    merchant_country: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # Authorization
    auth_code: Mapped[str | None] = mapped_column(String(8), unique=True, nullable=True, index=True)
    terminal_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pos_entry_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Flags
    card_not_present: Mapped[bool] = mapped_column(Boolean, default=False)
    installments: Mapped[int | None] = mapped_column(nullable=True)

    risk_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_notes: Mapped[str | None] = mapped_column(String, nullable=True)

    # Linkage
    parent_txn_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True
    )

    # Risk
    fraud_score: Mapped[float | None] = mapped_column(nullable=True)
    risk_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    internal_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    internal_flag_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Idempotency
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)

    # Metadata
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    holds: Mapped[list["CreditHold"]] = relationship(back_populates="transaction", lazy="selectin")
    dispute: Mapped[Optional["Dispute"]] = relationship(
        "Dispute",
        primaryjoin="and_(Transaction.id == Dispute.transaction_id, Dispute.status != 'WITHDRAWN')",
        backref="transaction",
        uselist=False,
        viewonly=True,
        lazy="selectin"
    )

    __table_args__ = (
        Index("ix_txn_card_created", "card_id", "created_at"),
        Index("ix_txn_status", "status"),
        Index("ix_txn_merchant", "merchant_id"),
    )

    def __repr__(self) -> str:
        return f"<Transaction {self.id} type={self.transaction_type} status={self.status}>"


# =====================================================
# CREDIT HOLDS TABLE
# =====================================================
class CreditHold(Base):
    __tablename__ = "credit_holds"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False, index=True
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    status: Mapped[str] = mapped_column(String(15), nullable=False, default=HoldStatus.ACTIVE.value)

    hold_expiry: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    release_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    transaction: Mapped["Transaction"] = relationship(back_populates="holds")

    __table_args__ = (
        Index("ix_hold_card_status", "card_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<CreditHold {self.id} status={self.status} amount={self.amount}>"


# =====================================================
# AUDIT LOG TABLE (APPEND-ONLY)
# =====================================================
class TransactionAuditLog(Base):
    __tablename__ = "transaction_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)

    actor_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    def __repr__(self) -> str:
        return f"<TransactionAuditLog {self.entity_type}:{self.entity_id} action={self.action}>"

"""
Transaction Processing System — Dispute Models
Tables: disputes, dispute_evidence, provisional_credits
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import String, Numeric, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base_class import Base
from app.models.transactions.enums import DisputeStatus, ProvisionalCreditStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False, index=True
    )

    case_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    dispute_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DisputeStatus.OPENED.value
    )

    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount_disputed: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    provisional_credit_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("provisional_credits.id"), nullable=True
    )

    raised_by_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    @property
    def raised_at(self) -> datetime:
        return self.created_at

    evidence: Mapped[list["DisputeEvidence"]] = relationship(back_populates="dispute", lazy="selectin")

    __table_args__ = (
        Index("ix_dispute_card_status", "card_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Dispute {self.case_number} type={self.dispute_type} status={self.status}>"


class DisputeEvidence(Base):
    __tablename__ = "dispute_evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    dispute_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("disputes.id"), nullable=False, index=True
    )
    submitted_by: Mapped[str] = mapped_column(String(100), nullable=False)
    document_s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    dispute: Mapped["Dispute"] = relationship(back_populates="evidence")

    def __repr__(self) -> str:
        return f"<DisputeEvidence {self.id} dispute={self.dispute_id}>"


class ProvisionalCredit(Base):
    __tablename__ = "provisional_credits"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    dispute_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False, index=True
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ProvisionalCreditStatus.PROVISIONAL.value
    )

    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<ProvisionalCredit {self.id} amount={self.amount} status={self.status}>"

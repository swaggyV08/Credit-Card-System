"""
Transaction Processing System — Risk Alert Model
Table: risk_alerts
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Float, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base_class import Base
from app.models.transactions.enums import RiskAlertStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class RiskAlert(Base):
    __tablename__ = "risk_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False, index=True
    )

    risk_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    fraud_score: Mapped[float] = mapped_column(Float, nullable=False)
    rules_triggered: Mapped[list | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RiskAlertStatus.OPEN.value
    )
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True)
    review_outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_risk_alert_status", "status"),
        Index("ix_risk_alert_tier", "risk_tier"),
    )

    def __repr__(self) -> str:
        return f"<RiskAlert {self.id} tier={self.risk_tier} status={self.status}>"

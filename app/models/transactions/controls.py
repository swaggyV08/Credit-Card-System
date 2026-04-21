"""
Transaction Processing System — Card Controls Models
Tables: card_controls, card_controls_history
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import String, Numeric, Boolean, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base_class import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class CardControl(Base):
    __tablename__ = "card_controls"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False, unique=True, index=True
    )

    # Toggle controls
    international_transactions_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    online_transactions_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    contactless_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    atm_withdrawals_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Spending limits
    daily_limit: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    single_transaction_limit: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    monthly_limit: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)

    # Restriction lists (stored as JSON arrays)
    mcc_blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    allowed_countries: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<CardControl card_id={self.card_id}>"


class CardControlHistory(Base):
    __tablename__ = "card_controls_history"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("card.id"), nullable=False, index=True
    )
    changed_by: Mapped[str] = mapped_column(String(100), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    previous_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    diff: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<CardControlHistory {self.id} card={self.card_id}>"


# =====================================================
# PROHIBITED / RESTRICTED COUNTRIES TABLE
# =====================================================
class ProhibitedCountry(Base):
    __tablename__ = "prohibited_countries"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, unique=True, index=True)
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    restriction_type: Mapped[str] = mapped_column(String(15), nullable=False)  # PROHIBITED | RESTRICTED

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return f"<ProhibitedCountry {self.country_code} type={self.restriction_type}>"

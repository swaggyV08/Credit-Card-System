import uuid
from sqlalchemy import Column, Integer, Numeric, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.base_class import Base
from app.models.enums import BureauRiskBand, ScoreTrigger

class BureauScore(Base):
    """
    Stores each computed bureau score snapshot for a user.
    One row per calculation event. History is preserved — never updated.
    """
    __tablename__ = "bureau_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    score = Column(Integer, nullable=False)
    risk_band = Column(SQLEnum(BureauRiskBand), nullable=False)
    trigger_event = Column(SQLEnum(ScoreTrigger), nullable=False)
    trigger_ref_id = Column(UUID(as_uuid=True), nullable=True)

    # Factor breakdown
    payment_history_score = Column(Integer, nullable=False)
    utilisation_score = Column(Integer, nullable=False)
    credit_history_score = Column(Integer, nullable=False)
    transaction_behaviour_score = Column(Integer, nullable=False)
    derogatory_score = Column(Integer, nullable=False)

    # Factor inputs
    on_time_payment_count = Column(Integer, nullable=False)
    late_payment_count = Column(Integer, nullable=False)
    missed_payment_count = Column(Integer, nullable=False)
    current_utilisation_pct = Column(Numeric(5, 2), nullable=False)
    account_age_days = Column(Integer, nullable=False)
    total_transactions_90d = Column(Integer, nullable=False)
    disputes_90d = Column(Integer, nullable=False)
    chargebacks_total = Column(Integer, nullable=False)

    # Audit
    computed_at = Column(DateTime(timezone=True), nullable=False, default=func.now(), index=True)
    computed_by = Column(UUID(as_uuid=True), nullable=True)

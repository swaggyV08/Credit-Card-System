from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid

from app.db.base_class import Base

class BureauScore(Base):
    __tablename__ = "bureau_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("ccm_users.id"), nullable=False)
    score = Column(Integer, nullable=False)
    risk_band = Column(String(50))
    trigger_event = Column(String(100))
    computed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Detailed components
    payment_history_score = Column(Integer, default=0)
    utilisation_score = Column(Integer, default=0)
    credit_history_score = Column(Integer, default=0)
    transaction_behaviour_score = Column(Integer, default=0)
    derogatory_score = Column(Integer, default=0)
    
    # Stats
    on_time_payment_count = Column(Integer, default=0)
    late_payment_count = Column(Integer, default=0)
    missed_payment_count = Column(Integer, default=0)
    current_utilisation_pct = Column(Numeric(5, 2), default=0.0)
    account_age_days = Column(Integer, default=0)
    total_transactions_90d = Column(Integer, default=0)
    disputes_90d = Column(Integer, default=0)
    chargebacks_total = Column(Integer, default=0)

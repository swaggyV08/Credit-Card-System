import uuid
from sqlalchemy import Column, String, Numeric, Integer, ForeignKey, DateTime, Boolean
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base

class BillingStatement(Base):
    """
    Monthly statement snapshot for a credit account.
    """
    __tablename__ = "billing_statements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_account_id = Column(UUID(as_uuid=True), ForeignKey("ccm_credit_accounts.id"), nullable=False)
    
    statement_period_start = Column(DateTime(timezone=True), nullable=False)
    statement_period_end = Column(DateTime(timezone=True), nullable=False)
    statement_date = Column(DateTime(timezone=True), server_default=func.now())
    due_date = Column(DateTime(timezone=True), nullable=False)
    
    opening_balance = Column(Numeric(15, 2), default=0.0)
    total_purchases = Column(Numeric(15, 2), default=0.0)
    total_cash_advances = Column(Numeric(15, 2), default=0.0)
    total_payments = Column(Numeric(15, 2), default=0.0)
    total_credits = Column(Numeric(15, 2), default=0.0)
    interest_charged = Column(Numeric(15, 2), default=0.0)
    fees_charged = Column(Numeric(15, 2), default=0.0)
    closing_balance = Column(Numeric(15, 2), default=0.0)
    
    minimum_amount_due = Column(Numeric(15, 2), default=0.0)
    
    is_fully_paid = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    credit_account = relationship("CCMCreditAccount")

class RewardEntry(Base):
    """
    Dedicated rewards ledger for tracking points/cashback.
    """
    __tablename__ = "rewards_ledger"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_account_id = Column(UUID(as_uuid=True), ForeignKey("ccm_credit_accounts.id"), nullable=False)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("ccm_card_transactions.id"), nullable=True)
    
    points_earned = Column(Numeric(15, 2), default=0.0)
    points_redeemed = Column(Numeric(15, 2), default=0.0)
    points_reversed = Column(Numeric(15, 2), default=0.0)
    
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    credit_account = relationship("CCMCreditAccount")
    transaction = relationship("CCMCardTransaction")

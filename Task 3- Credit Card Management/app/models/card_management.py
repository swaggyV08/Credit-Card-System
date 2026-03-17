import uuid
from typing import Optional
from sqlalchemy import Column, String, Boolean, Numeric, Integer, ForeignKey, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.models.enums import (
    CCMCardStatus, CCMTransactionType, CCMTransactionStatus, CCMFraudBlockReason,
    CardNetwork, CardVariant, ActorType, CCMAccountStatus, CCMAccountRiskFlag,
    CCMAdjustmentType, CCMLedgerEntryType
)


class CCMCreditAccount(Base):
    """
    Dedicated Credit Account model for Card Management System.
    Links 1-to-1 with a Credit Card (enforced logically, or via ForeignKey here).
    """
    __tablename__ = "ccm_credit_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # The requirement specifically mentions Card (1) - (1) Credit Account
    card_id = Column(UUID(as_uuid=True), ForeignKey("ccm_credit_cards.id"), unique=True, nullable=True)

    credit_limit = Column(Numeric(15, 2), nullable=False)
    available_credit = Column(Numeric(15, 2), nullable=False)
    outstanding_balance = Column(Numeric(15, 2), default=0.0)
    cash_limit = Column(Numeric(15, 2), nullable=False)
    
    billing_cycle_day = Column(Integer, default=1)
    payment_due_days = Column(Integer, default=20)
    minimum_due = Column(Numeric(15, 2), default=0.0)
    interest_rate = Column(Numeric(5, 2), default=0.0)
    late_fee = Column(Numeric(15, 2), default=0.0)
    
    # APR Configuration
    purchase_apr = Column(Numeric(5, 2), default=3.49)
    cash_apr = Column(Numeric(5, 2), default=3.99)
    penalty_apr = Column(Numeric(5, 2), default=4.99)

    # Risk & Status
    product_code = Column(String, nullable=True) # e.g. PLATINUM_CARD
    status = Column(SQLEnum(CCMAccountStatus, native_enum=False), default=CCMAccountStatus.PENDING)
    risk_flag = Column(SQLEnum(CCMAccountRiskFlag, native_enum=False), default=CCMAccountRiskFlag.NONE)
    
    # Overlimit Configuration
    overlimit_enabled = Column(Boolean, default=False)
    overlimit_buffer = Column(Numeric(15, 2), default=0.0)
    overlimit_fee = Column(Numeric(15, 2), default=0.0)

    last_statement_date = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    card = relationship("CCMCreditCard", back_populates="credit_account")
    transactions = relationship("CCMCardTransaction", back_populates="credit_account")
    adjustments = relationship("CCMCreditAccountAdjustment", back_populates="credit_account")
    ledger_entries = relationship("CCMCreditAccountLedger", back_populates="credit_account")


class CCMCreditCard(Base):
    """
    Dedicated Credit Card model.
    """
    __tablename__ = "ccm_credit_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    card_number = Column(String, unique=True, index=True, nullable=False) # In real world, encrypted.
    card_network = Column(SQLEnum(CardNetwork, native_enum=False), nullable=False)
    card_variant = Column(SQLEnum(CardVariant, native_enum=False), nullable=False)
    
    expiry_date = Column(String, nullable=False)
    cvv_hash = Column(String, nullable=False)
    
    status = Column(SQLEnum(CCMCardStatus, native_enum=False), default=CCMCardStatus.CREATED)
    
    is_virtual = Column(Boolean, default=False)
    is_contactless_enabled = Column(Boolean, default=True)
    is_international_enabled = Column(Boolean, default=False)
    is_online_enabled = Column(Boolean, default=True)
    is_atm_enabled = Column(Boolean, default=True)
    is_domestic_enabled = Column(Boolean, default=True)
    
    daily_spend_limit = Column(Numeric(15, 2), nullable=True)
    daily_withdraw_limit = Column(Numeric(15, 2), nullable=True)
    
    issued_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    
    blocked_reason = Column(SQLEnum(CCMFraudBlockReason, native_enum=False), nullable=True)
    blocked_by_actor = Column(SQLEnum(ActorType, native_enum=False), nullable=True)
    pin_hash = Column(String, nullable=True) # Encrypted or hashed (bcrypt) pin
    reissue_reference = Column(UUID(as_uuid=True), ForeignKey("ccm_credit_cards.id"), nullable=True) 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User")
    credit_account = relationship("CCMCreditAccount", back_populates="card", uselist=False)
    transactions = relationship("CCMCardTransaction", back_populates="card")
    reissued_from = relationship("CCMCreditCard", remote_side=[id])


class CCMCardTransaction(Base):
    """
    Transaction log for purchases, refunds, reversals.
    """
    __tablename__ = "ccm_card_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_id = Column(UUID(as_uuid=True), ForeignKey("ccm_credit_cards.id"), nullable=False)
    credit_account_id = Column(UUID(as_uuid=True), ForeignKey("ccm_credit_accounts.id"), nullable=False)
    
    amount = Column(Numeric(15, 2), nullable=False)
    merchant_name = Column(String, nullable=False)
    merchant_category = Column(String, nullable=True)
    currency = Column(String, default="INR")
    
    transaction_type = Column(SQLEnum(CCMTransactionType, native_enum=False), nullable=False)
    status = Column(SQLEnum(CCMTransactionStatus, native_enum=False), default=CCMTransactionStatus.PENDING)
    
    geo_location = Column(String, nullable=True) 
    is_fraud_flagged = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    card = relationship("CCMCreditCard", back_populates="transactions")
    credit_account = relationship("CCMCreditAccount", back_populates="transactions")


class CCMCreditAccountAdjustment(Base):
    """
    Manual adjustments made to the credit account (credits/debits).
    """
    __tablename__ = "ccm_credit_account_adjustments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_account_id = Column(UUID(as_uuid=True), ForeignKey("ccm_credit_accounts.id"), nullable=False)
    
    amount = Column(Numeric(15, 2), nullable=False)
    adjustment_type = Column(SQLEnum(CCMAdjustmentType, native_enum=False), nullable=False)
    reason_code = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    
    created_by = Column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    credit_account = relationship("CCMCreditAccount", back_populates="adjustments")


class CCMCreditAccountLedger(Base):
    """
    Full financial ledger for the credit account.
    Every financial change MUST have an entry here.
    """
    __tablename__ = "ccm_credit_account_ledger"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_account_id = Column(UUID(as_uuid=True), ForeignKey("ccm_credit_accounts.id"), nullable=False)
    
    entry_type = Column(SQLEnum(CCMLedgerEntryType, native_enum=False), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    description = Column(String, nullable=False)
    reference_id = Column(UUID(as_uuid=True), nullable=True) # ID of transaction or adjustment
    
    balance_before = Column(Numeric(15, 2), nullable=False)
    balance_after = Column(Numeric(15, 2), nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    credit_account = relationship("CCMCreditAccount", back_populates="ledger_entries")




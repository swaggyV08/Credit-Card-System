import uuid
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, Numeric, Integer, ForeignKey, DateTime

if TYPE_CHECKING:
    from app.models.auth import User
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(20), ForeignKey("users.id"), nullable=False)
    # The requirement specifically mentions Card (1) - (1) Credit Account
    card_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("ccm_credit_cards.id"), unique=True, nullable=True)

    credit_limit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    available_credit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    outstanding_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    cash_limit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    
    billing_cycle_day: Mapped[int] = mapped_column(Integer, default=1)
    payment_due_days: Mapped[int] = mapped_column(Integer, default=20)
    minimum_due: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    interest_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0)
    late_fee: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    
    # APR Configuration
    purchase_apr: Mapped[float] = mapped_column(Numeric(5, 2), default=3.49)
    cash_apr: Mapped[float] = mapped_column(Numeric(5, 2), default=3.99)
    penalty_apr: Mapped[float] = mapped_column(Numeric(5, 2), default=4.99)

    # Risk & Status
    product_code: Mapped[Optional[str]] = mapped_column(String, nullable=True) # e.g. PLATINUM_CARD
    status: Mapped[CCMAccountStatus] = mapped_column(SQLEnum(CCMAccountStatus, native_enum=False), default=CCMAccountStatus.PENDING)
    risk_flag: Mapped[CCMAccountRiskFlag] = mapped_column(SQLEnum(CCMAccountRiskFlag, native_enum=False), default=CCMAccountRiskFlag.NONE)
    
    # Overlimit Configuration
    overlimit_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    overlimit_buffer: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    overlimit_fee: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)

    last_statement_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False) # Optimistic Locking
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    card: Mapped[Optional["CCMCreditCard"]] = relationship("CCMCreditCard", back_populates="credit_account")
    transactions: Mapped[List["CCMCardTransaction"]] = relationship("CCMCardTransaction", back_populates="credit_account")
    adjustments: Mapped[List["CCMCreditAccountAdjustment"]] = relationship("CCMCreditAccountAdjustment", back_populates="credit_account")
    ledger_entries: Mapped[List["CCMCreditAccountLedger"]] = relationship("CCMCreditAccountLedger", back_populates="credit_account")

    @property
    def card_count(self) -> int:
        return 1 if self.card_id else 0

    @property
    def cards(self) -> list:
        return [self.card] if self.card else []


class CCMCreditCard(Base):
    """
    Dedicated Credit Card model.
    """
    __tablename__ = "ccm_credit_cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(20), ForeignKey("users.id"), nullable=False)
    
    card_number: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False) # In real world, encrypted.
    card_network: Mapped[CardNetwork] = mapped_column(SQLEnum(CardNetwork, native_enum=False), nullable=False)
    card_variant: Mapped[CardVariant] = mapped_column(SQLEnum(CardVariant, native_enum=False), nullable=False)
    
    expiry_date: Mapped[str] = mapped_column(String, nullable=False)
    cvv_hash: Mapped[str] = mapped_column(String, nullable=False)
    
    status: Mapped[CCMCardStatus] = mapped_column(SQLEnum(CCMCardStatus, native_enum=False), default=CCMCardStatus.CREATED)
    
    is_virtual: Mapped[bool] = mapped_column(Boolean, default=False)
    is_contactless_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_international_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_online_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_atm_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_domestic_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    
    daily_spend_limit: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    daily_withdraw_limit: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    blocked_reason: Mapped[Optional[CCMFraudBlockReason]] = mapped_column(SQLEnum(CCMFraudBlockReason, native_enum=False), nullable=True)
    blocked_by_actor: Mapped[Optional[ActorType]] = mapped_column(SQLEnum(ActorType, native_enum=False), nullable=True)
    pin_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True) # Encrypted or hashed (bcrypt) pin
    reissue_reference: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("ccm_credit_cards.id"), nullable=True) 
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    user: Mapped["User"] = relationship("app.models.auth.User")
    credit_account: Mapped[Optional["CCMCreditAccount"]] = relationship("CCMCreditAccount", back_populates="card", uselist=False)
    transactions: Mapped[List["CCMCardTransaction"]] = relationship("CCMCardTransaction", back_populates="card")
    reissued_from: Mapped[Optional["CCMCreditCard"]] = relationship("CCMCreditCard", remote_side=[id])


class CCMCardTransaction(Base):
    """
    Transaction log for purchases, refunds, reversals.
    """
    __tablename__ = "ccm_card_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ccm_credit_cards.id"), nullable=False)
    credit_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ccm_credit_accounts.id"), nullable=False)
    
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    merchant_name: Mapped[str] = mapped_column(String, nullable=False)
    merchant_category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="INR")
    
    transaction_type: Mapped[CCMTransactionType] = mapped_column(SQLEnum(CCMTransactionType, native_enum=False), nullable=False)
    status: Mapped[CCMTransactionStatus] = mapped_column(SQLEnum(CCMTransactionStatus, native_enum=False), default=CCMTransactionStatus.PENDING)
    
    idempotency_key: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True) # Critical for production duplicate prevention
    reference_id: Mapped[Optional[str]] = mapped_column(String, nullable=True) # External reference
    settlement_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    card: Mapped["CCMCreditCard"] = relationship("CCMCreditCard", back_populates="transactions")
    credit_account: Mapped["CCMCreditAccount"] = relationship("CCMCreditAccount", back_populates="transactions")


class CCMCreditAccountAdjustment(Base):
    """
    Manual adjustments made to the credit account (credits/debits).
    """
    __tablename__ = "ccm_credit_account_adjustments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ccm_credit_accounts.id"), nullable=False)
    
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    adjustment_type: Mapped[CCMAdjustmentType] = mapped_column(SQLEnum(CCMAdjustmentType, native_enum=False), nullable=False)
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    credit_account: Mapped["CCMCreditAccount"] = relationship("CCMCreditAccount", back_populates="adjustments")


class CCMCreditAccountLedger(Base):
    """
    Full financial ledger for the credit account.
    Every financial change MUST have an entry here.
    """
    __tablename__ = "ccm_credit_account_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ccm_credit_accounts.id"), nullable=False)
    
    entry_type: Mapped[CCMLedgerEntryType] = mapped_column(SQLEnum(CCMLedgerEntryType, native_enum=False), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    reference_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True) # ID of transaction or adjustment
    
    balance_before: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    credit_account: Mapped["CCMCreditAccount"] = relationship("CCMCreditAccount", back_populates="ledger_entries")




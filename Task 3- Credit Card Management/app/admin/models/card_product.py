import uuid
from sqlalchemy import Column, String, Boolean, Numeric, Integer, ForeignKey, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.models.enums import (
    CardNetwork, CardFormFactor, CardVariant, BillingCycleType,
    StatementGenerationMode, RewardAccrualType, RewardExpiryPolicy,
    FraudMonitoringProfile, VelocityCheckProfile, ProductStatus
)

class CardProductCore(Base):
    __tablename__ = "card_product_core"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_product_id = Column(UUID(as_uuid=True), ForeignKey("credit_product_information.id"), nullable=False)

    card_network = Column(SQLEnum(CardNetwork, native_enum=False), nullable=False)
    card_bin_range = Column(String, nullable=False)  # Example: 4XXXXX
    card_branding_code = Column(String, nullable=False)
    card_form_factor = Column(SQLEnum(CardFormFactor, native_enum=False), default=CardFormFactor.PHYSICAL)
    card_variant = Column(SQLEnum(CardVariant, native_enum=False), default=CardVariant.CLASSIC)
    default_card_currency = Column(String, default="INR")

    credit_product = relationship("CreditProductInformation", back_populates="card_products")
    billing_config = relationship("CardBillingConfiguration", back_populates="card_product", uselist=False, cascade="all, delete-orphan")
    transaction_controls = relationship("CardTransactionControls", back_populates="card_product", uselist=False, cascade="all, delete-orphan")
    fx_configuration = relationship("CardFxConfiguration", back_populates="card_product", uselist=False, cascade="all, delete-orphan")
    usage_limits = relationship("CardUsageLimits", back_populates="card_product", uselist=False, cascade="all, delete-orphan")
    rewards_config = relationship("CardRewardsConfiguration", back_populates="card_product", uselist=False, cascade="all, delete-orphan")
    authorization_rules = relationship("CardAuthorizationRules", back_populates="card_product", uselist=False, cascade="all, delete-orphan")
    lifecycle_rules = relationship("CardLifecycleRules", back_populates="card_product", uselist=False, cascade="all, delete-orphan")
    fraud_profile = relationship("CardFraudRiskProfile", back_populates="card_product", uselist=False, cascade="all, delete-orphan")
    governance = relationship("CardProductGovernance", back_populates="card_product", uselist=False, cascade="all, delete-orphan")
    applications = relationship("CreditCardApplication", back_populates="card_product")

class CardBillingConfiguration(Base):
    __tablename__ = "card_billing_configuration"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_product_id = Column(UUID(as_uuid=True), ForeignKey("card_product_core.id"), nullable=False, unique=True)

    billing_cycle_type = Column(SQLEnum(BillingCycleType, native_enum=False), default=BillingCycleType.MONTHLY)
    billing_cycle_day = Column(Integer, default=1)  # Day of month statements generate
    payment_due_days = Column(Integer, default=20)  # Days after stmt to pay
    minimum_due_formula = Column(String, default="5_PCT_OF_BILL")  # e.g. min 5%
    statement_generation_mode = Column(SQLEnum(StatementGenerationMode, native_enum=False), default=StatementGenerationMode.ELECTRONIC)
    statement_currency = Column(String, default="INR")
    grace_period_days = Column(Integer, default=3)

    card_product = relationship("CardProductCore", back_populates="billing_config")

class CardTransactionControls(Base):
    __tablename__ = "card_transaction_controls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_product_id = Column(UUID(as_uuid=True), ForeignKey("card_product_core.id"), nullable=False, unique=True)

    pos_allowed = Column(Boolean, default=True)
    ecommerce_allowed = Column(Boolean, default=True)
    atm_withdrawal_allowed = Column(Boolean, default=False)
    contactless_enabled = Column(Boolean, default=True)
    international_txn_allowed = Column(Boolean, default=False)
    international_txn_limit_cap = Column(Numeric(15, 2), nullable=True)
    international_cash_allowed = Column(Boolean, default=False)
    tokenization_supported = Column(Boolean, default=True)
    recurring_txn_allowed = Column(Boolean, default=True)

    card_product = relationship("CardProductCore", back_populates="transaction_controls")

class CardFxConfiguration(Base):
    __tablename__ = "card_fx_configuration"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_product_id = Column(UUID(as_uuid=True), ForeignKey("card_product_core.id"), nullable=False, unique=True)

    supported_currencies = Column(JSONB, nullable=True) # Array of allowed ISO currency codes
    fx_rate_source = Column(String, default="VISA")
    fx_conversion_method = Column(String, default="MARKET_RATE")
    foreign_markup_fee_pct = Column(Numeric(5, 2), default=3.5)
    cross_border_fee_applicable = Column(Boolean, default=True)
    cross_border_fee_rate = Column(Numeric(5, 2), default=1.0)

    card_product = relationship("CardProductCore", back_populates="fx_configuration")

class CardUsageLimits(Base):
    __tablename__ = "card_usage_limits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_product_id = Column(UUID(as_uuid=True), ForeignKey("card_product_core.id"), nullable=False, unique=True)

    cash_advance_limit_pct = Column(Numeric(5, 2), default=20.0)
    domestic_txn_daily_cap = Column(Numeric(15, 2), nullable=False)
    contactless_txn_cap = Column(Numeric(15, 2), default=5000.0)
    max_txn_per_day = Column(Integer, default=50)

    card_product = relationship("CardProductCore", back_populates="usage_limits")

class CardRewardsConfiguration(Base):
    __tablename__ = "card_rewards_configuration"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_product_id = Column(UUID(as_uuid=True), ForeignKey("card_product_core.id"), nullable=False, unique=True)

    reward_program_code = Column(String, nullable=False)
    reward_accrual_type = Column(SQLEnum(RewardAccrualType, native_enum=False), default=RewardAccrualType.POINTS)
    reward_earn_rate = Column(Numeric(5, 2), default=1.0) # E.g., 1 unit per 100 spent
    reward_expiry_policy = Column(SQLEnum(RewardExpiryPolicy, native_enum=False), default=RewardExpiryPolicy.TWO_YEARS)
    reward_redemption_modes = Column(JSONB, nullable=False) # E.g., ["STATEMENT_CREDIT", "CATALOG"]
    merchant_category_bonus = Column(JSONB, nullable=True) # E.g., {"DINING": 5}

    card_product = relationship("CardProductCore", back_populates="rewards_config")

class CardAuthorizationRules(Base):
    __tablename__ = "card_authorization_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_product_id = Column(UUID(as_uuid=True), ForeignKey("card_product_core.id"), nullable=False, unique=True)

    partial_auth_allowed = Column(Boolean, default=False)
    offline_txn_allowed = Column(Boolean, default=False)
    authorization_ttl_seconds = Column(Integer, default=604800) # 7 days
    retry_authorization_allowed = Column(Boolean, default=True)
    network_stand_in_allowed = Column(Boolean, default=True)

    card_product = relationship("CardProductCore", back_populates="authorization_rules")

class CardLifecycleRules(Base):
    __tablename__ = "card_lifecycle_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_product_id = Column(UUID(as_uuid=True), ForeignKey("card_product_core.id"), nullable=False, unique=True)

    card_validity_years = Column(Integer, default=5)
    auto_renew_card = Column(Boolean, default=True)
    replacement_reason_codes = Column(JSONB, nullable=False) # e.g., ["LOST", "STOLEN", "DAMAGED"]
    reissue_fee_applicable = Column(Boolean, default=True)
    temporary_block_supported = Column(Boolean, default=True)

    card_product = relationship("CardProductCore", back_populates="lifecycle_rules")

class CardFraudRiskProfile(Base):
    __tablename__ = "card_fraud_risk_profile"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_product_id = Column(UUID(as_uuid=True), ForeignKey("card_product_core.id"), nullable=False, unique=True)

    fraud_monitoring_profile = Column(SQLEnum(FraudMonitoringProfile, native_enum=False), default=FraudMonitoringProfile.STANDARD)
    velocity_check_profile = Column(SQLEnum(VelocityCheckProfile, native_enum=False), default=VelocityCheckProfile.STANDARD)
    geo_blocking_supported = Column(Boolean, default=True)
    fallback_auth_allowed = Column(Boolean, default=False)

    card_product = relationship("CardProductCore", back_populates="fraud_profile")

class CardProductGovernance(Base):
    __tablename__ = "card_product_governance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_product_id = Column(UUID(as_uuid=True), ForeignKey("card_product_core.id"), nullable=False, unique=True)

    card_product_version = Column(Integer, default=1, nullable=False)
    status = Column(SQLEnum(ProductStatus, native_enum=False), default=ProductStatus.DRAFT)
    effective_from = Column(DateTime(timezone=True), nullable=True)
    effective_to = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=False)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=True)

    card_product = relationship("CardProductCore", back_populates="governance")
    creator = relationship("Admin", foreign_keys=[created_by])
    approver = relationship("Admin", foreign_keys=[approved_by])
    updater = relationship("Admin", foreign_keys=[updated_by])

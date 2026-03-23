import uuid
from typing import Optional
from sqlalchemy import Column, String, Boolean, Numeric, Integer, ForeignKey, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.models.enums import (
    ApplicationStatus, ApplicationStage, AccountStatus, CardStatus, CardType,
    AMLRiskCategory, InternalRiskRating, AutoPayType
)
from app.core.identifiers import generate_readable_id

class CreditCardApplication(Base):
    __tablename__ = "credit_card_application"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    readable_id = Column(String, unique=True, index=True, default=lambda: generate_readable_id("APP"))
    user_id = Column(String(20), ForeignKey("users.id"), nullable=False)
    credit_product_id = Column(UUID(as_uuid=True), ForeignKey("credit_product_information.id"), nullable=False)
    card_product_id = Column(UUID(as_uuid=True), ForeignKey("card_product_core.id"), nullable=False)

    application_status = Column(SQLEnum(ApplicationStatus, native_enum=False), default=ApplicationStatus.SUBMITTED)
    current_stage = Column(SQLEnum(ApplicationStage, native_enum=False), default=ApplicationStage.KYC)
    
    employment_status = Column(String, nullable=True)
    declared_income = Column(Numeric(15, 2), nullable=True)
    income_frequency = Column(String, default="ANNUAL")
    occupation = Column(String, nullable=True)
    employer_name = Column(String, nullable=True)
    work_experience_years = Column(Integer, nullable=True)

    existing_emis_monthly = Column(Numeric(15, 2), default=0.0)
    has_existing_credit_card = Column(Boolean, default=False)
    existing_cards_count = Column(Integer, default=0)
    approx_credit_limit_total = Column(Numeric(15, 2), default=0.0)

    residential_status = Column(String, nullable=True)
    years_at_current_address = Column(Integer, nullable=True)

    preferred_billing_cycle = Column(String, nullable=True)
    statement_delivery_mode = Column(String, nullable=True)
    
    card_delivery_address_type = Column(String, nullable=True)
    preferred_branch_code = Column(String, nullable=True)

    nominee_name = Column(String, nullable=True)
    nominee_relationship = Column(String, nullable=True)

    consent_terms_accepted = Column(Boolean, default=False)
    consent_credit_bureau_check = Column(Boolean, default=False)
    consent_marketing_communication = Column(Boolean, default=False)
    application_declaration_accepted = Column(Boolean, default=False)

    
    retry_count = Column(Integer, default=0)
    cooling_period_until = Column(DateTime(timezone=True), nullable=True)
    rejection_reason_code = Column(String, nullable=True)
    rejection_reason = Column(String, nullable=True)

    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=True)

    @property
    def bureau_score(self) -> Optional[int]:
        try:
            return self.bureau_report.bureau_score if self.bureau_report else None
        except Exception:
            return None

    @property
    def risk_band(self) -> Optional[str]:
        try:
            if not self.risk_assessment:
                return None
            val = self.risk_assessment.risk_band
            return val.value if hasattr(val, 'value') else str(val)
        except Exception:
            return None

    user = relationship("User", foreign_keys=[user_id])
    credit_product = relationship("CreditProductInformation", back_populates="applications")
    card_product = relationship("CardProductCore", back_populates="applications")
    reviewer = relationship("Admin", foreign_keys=[reviewed_by])
    credit_account = relationship("CreditAccount", back_populates="application", uselist=False)
    
    bureau_report = relationship("BureauReport", back_populates="application", uselist=False)
    risk_assessment = relationship("RiskAssessment", back_populates="application", uselist=False)

    @property
    def credit_account_id(self) -> Optional[uuid.UUID]:
        if self.credit_account:
            return self.credit_account.id
        return None


class CreditAccount(Base):
    __tablename__ = "credit_account"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    readable_id = Column(String, unique=True, index=True, default=lambda: generate_readable_id("ACC"))
    user_id = Column(String(20), ForeignKey("users.id"), nullable=False)
    credit_product_id = Column(UUID(as_uuid=True), ForeignKey("credit_product_information.id"), nullable=False)
    card_product_id = Column(UUID(as_uuid=True), ForeignKey("card_product_core.id"), nullable=False)
    application_id = Column(UUID(as_uuid=True), ForeignKey("credit_card_application.id"), nullable=True) # Traceability

    account_currency = Column(String, default="INR")
    credit_limit = Column(Numeric(15, 2), nullable=False)
    available_limit = Column(Numeric(15, 2), nullable=False)
    cash_advance_limit = Column(Numeric(15, 2), nullable=False)
    outstanding_amount = Column(Numeric(15, 2), default=0.0)
    
    billing_cycle_id = Column(String, nullable=False)
    internal_risk_rating = Column(SQLEnum(InternalRiskRating, native_enum=False), nullable=True)
    aml_risk_category = Column(SQLEnum(AMLRiskCategory, native_enum=False), nullable=True)
    
    overlimit_allowed = Column(Boolean, default=False)
    overlimit_percentage = Column(Numeric(5, 2), nullable=True)
    
    revolving_credit_enabled = Column(Boolean, default=True)
    
    autopay_enabled = Column(Boolean, default=False)
    autopay_type = Column(SQLEnum(AutoPayType, native_enum=False), nullable=True)
    
    account_status = Column(SQLEnum(AccountStatus, native_enum=False), default=AccountStatus.ACTIVE)
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    
    created_by = Column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=True)

    credit_product = relationship("CreditProductInformation", back_populates="credit_accounts")
    cards = relationship("Card", back_populates="credit_account")
    creator = relationship("Admin", foreign_keys=[created_by])
    approver = relationship("Admin", foreign_keys=[approved_by])
    application = relationship("CreditCardApplication", back_populates="credit_account")


class Card(Base):
    __tablename__ = "card"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    readable_id = Column(String, unique=True, index=True, default=lambda: generate_readable_id("CRD"))
    credit_account_id = Column(UUID(as_uuid=True), ForeignKey("credit_account.id"), nullable=False)
    card_product_id = Column(UUID(as_uuid=True), ForeignKey("card_product_core.id"), nullable=False)

    card_type = Column(SQLEnum(CardType, native_enum=False), default=CardType.PRIMARY)
    
    # SECURITY: PAN stored encrypted, never in plain-text
    pan_encrypted = Column(String, nullable=False)
    # SECURITY: Masked PAN for safe API exposure
    pan_masked = Column(String, nullable=False)
    
    expiry_date = Column(String, nullable=False) # Store securely, encrypted if necessary depending on PCI scope
    expiry_date_masked = Column(String, nullable=False)
    
    cvv_encrypted = Column(String, nullable=False)
    cvv_masked = Column(String, nullable=False)
    
    card_status = Column(SQLEnum(CardStatus, native_enum=False), default=CardStatus.INACTIVE)
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    activation_date = Column(DateTime(timezone=True), nullable=True)
    
    international_usage_enabled = Column(Boolean, default=False)
    ecommerce_enabled = Column(Boolean, default=False)
    atm_enabled = Column(Boolean, default=False)
    pin_hashed = Column(String, nullable=True)

    credit_account = relationship("CreditAccount", back_populates="cards")
    card_product = relationship("CardProductCore")

class CardActivationOTP(Base):
    __tablename__ = "card_activation_otp"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_id = Column(UUID(as_uuid=True), ForeignKey("card.id"), nullable=False)
    otp_hash = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    card = relationship("Card")

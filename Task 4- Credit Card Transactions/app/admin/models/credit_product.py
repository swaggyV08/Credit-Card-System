import uuid
from sqlalchemy import Column, String, Boolean, Numeric, Integer, ForeignKey, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.models.enums import (
    ProductCategory, ProductStatus, InterestType, InterestCalculationMethod,
    InterestBasis, Country, AMLRiskCategory, TaxApplicability
)

class CreditProductInformation(Base):
    __tablename__ = "credit_product_information"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_code = Column(String, unique=True, index=True, nullable=False)
    product_name = Column(String, nullable=False)
    product_category = Column(SQLEnum(ProductCategory, native_enum=False), default=ProductCategory.CARD)
    product_version = Column(Integer, default=1, nullable=False)
    status = Column(SQLEnum(ProductStatus, native_enum=False), default=ProductStatus.DRAFT)

    limits = relationship("CreditProductLimits", back_populates="product", uselist=False, cascade="all, delete-orphan")
    interest_framework = relationship("CreditProductInterestFramework", back_populates="product", uselist=False, cascade="all, delete-orphan")
    fees = relationship("CreditProductFees", back_populates="product", uselist=False, cascade="all, delete-orphan")
    eligibility_rules = relationship("CreditProductEligibilityRules", back_populates="product", uselist=False, cascade="all, delete-orphan")
    compliance_metadata = relationship("CreditProductComplianceMetadata", back_populates="product", uselist=False, cascade="all, delete-orphan")
    accounting_mapping = relationship("CreditProductAccountingMapping", back_populates="product", uselist=False, cascade="all, delete-orphan")
    governance = relationship("CreditProductGovernance", back_populates="product", uselist=False, cascade="all, delete-orphan")

    card_products = relationship("CardProductCore", back_populates="credit_product")
    applications = relationship("CreditCardApplication", back_populates="credit_product")
    credit_accounts = relationship("CreditAccount", back_populates="credit_product")

class CreditProductLimits(Base):
    __tablename__ = "credit_product_limits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_product_id = Column(UUID(as_uuid=True), ForeignKey("credit_product_information.id"), nullable=False, unique=True)

    min_credit_limit = Column(Numeric(15, 2), nullable=False)
    max_credit_limit = Column(Numeric(15, 2), nullable=False)
    max_total_exposure_per_cif = Column(Numeric(15, 2), nullable=False)
    
    revolving_credit_allowed = Column(Boolean, default=True)
    overlimit_allowed = Column(Boolean, default=False)
    overlimit_percentage = Column(Numeric(5, 2), default=0.0)

    product = relationship("CreditProductInformation", back_populates="limits")

class CreditProductInterestFramework(Base):
    __tablename__ = "credit_product_interest_framework"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_product_id = Column(UUID(as_uuid=True), ForeignKey("credit_product_information.id"), nullable=False, unique=True)

    interest_type = Column(SQLEnum(InterestType, native_enum=False), default=InterestType.FIXED)
    base_interest_rate = Column(Numeric(5, 2), nullable=False) # e.g., 18.5 for 18.5%
    interest_calculation_method = Column(SQLEnum(InterestCalculationMethod, native_enum=False), default=InterestCalculationMethod.AVERAGE_DAILY_BALANCE)
    interest_basis = Column(SQLEnum(InterestBasis, native_enum=False), default=InterestBasis.ACTUAL_360)
    penal_interest_rate = Column(Numeric(5, 2), nullable=False)
    
    interest_free_allowed = Column(Boolean, default=True)
    max_interest_free_days = Column(Integer, default=30)

    product = relationship("CreditProductInformation", back_populates="interest_framework")

class CreditProductFees(Base):
    __tablename__ = "credit_product_fees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_product_id = Column(UUID(as_uuid=True), ForeignKey("credit_product_information.id"), nullable=False, unique=True)

    joining_fee = Column(Numeric(10, 2), default=0.0)
    annual_fee = Column(Numeric(10, 2), default=0.0)
    renewal_fee = Column(Numeric(10, 2), default=0.0)
    late_payment_fee = Column(Numeric(10, 2), default=0.0)
    overlimit_fee = Column(Numeric(10, 2), default=0.0)
    cash_advance_fee = Column(Numeric(10, 2), default=0.0)

    product = relationship("CreditProductInformation", back_populates="fees")



class CreditProductEligibilityRules(Base):
    __tablename__ = "credit_product_eligibility_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_product_id = Column(UUID(as_uuid=True), ForeignKey("credit_product_information.id"), nullable=False, unique=True)

    min_age = Column(Integer, default=18)
    max_age = Column(Integer, default=70)
    min_income_required = Column(Numeric(15, 2), nullable=False)
    employment_types_allowed = Column(JSONB, nullable=False) # e.g., ["FULL_TIME", "SELF_EMPLOYED"]
    min_credit_score = Column(Integer, default=750)
    secured_flag = Column(Boolean, default=False)

    product = relationship("CreditProductInformation", back_populates="eligibility_rules")

class CreditProductComplianceMetadata(Base):
    __tablename__ = "credit_product_compliance_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_product_id = Column(UUID(as_uuid=True), ForeignKey("credit_product_information.id"), nullable=False, unique=True)

    regulatory_product_code = Column(String, nullable=False)
    kyc_level_required = Column(String, default="FULL_KYC")
    aml_risk_category = Column(SQLEnum(AMLRiskCategory, native_enum=False), default=AMLRiskCategory.MEDIUM)
    jurisdiction = Column(SQLEnum(Country, native_enum=False), default=Country.INDIA)
    tax_applicability = Column(SQLEnum(TaxApplicability, native_enum=False), default=TaxApplicability.GST_APPLICABLE)
    statement_disclosure_version = Column(String, nullable=False)
    regulatory_reporting_category = Column(String, nullable=False)

    product = relationship("CreditProductInformation", back_populates="compliance_metadata")

class CreditProductAccountingMapping(Base):
    __tablename__ = "credit_product_accounting_mapping"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_product_id = Column(UUID(as_uuid=True), ForeignKey("credit_product_information.id"), nullable=False, unique=True)

    principal_gl_code = Column(String, nullable=False)
    interest_income_gl_code = Column(String, nullable=False)
    fee_income_gl_code = Column(String, nullable=False)
    penalty_gl_code = Column(String, nullable=False)
    writeoff_gl_code = Column(String, nullable=False)

    product = relationship("CreditProductInformation", back_populates="accounting_mapping")

class CreditProductGovernance(Base):
    __tablename__ = "credit_product_governance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_product_id = Column(UUID(as_uuid=True), ForeignKey("credit_product_information.id"), nullable=False, unique=True)

    effective_from = Column(DateTime(timezone=True), nullable=True)
    effective_to = Column(DateTime(timezone=True), nullable=True)
    auto_renewal_allowed = Column(Boolean, default=True)
    cooling_period_days = Column(Integer, default=90)
    rejection_reason = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=False)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), ForeignKey("admins.id"), nullable=True)

    product = relationship("CreditProductInformation", back_populates="governance")
    creator = relationship("Admin", foreign_keys=[created_by])
    approver = relationship("Admin", foreign_keys=[approved_by])
    updater = relationship("Admin", foreign_keys=[updated_by])

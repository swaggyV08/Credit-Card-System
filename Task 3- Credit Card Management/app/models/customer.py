import uuid
from enum import Enum

from sqlalchemy import Column, String, Boolean, Date, DateTime, ForeignKey, Numeric, Integer
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.models.enums import (
    Country,
    CountryCode,
    Suffix,
    YesNo,
    CitizenshipDocumentType,
    EmploymentType,
    PreferredCommunication,
    TimeZone,
    KYCState,
    Gender,
    MaritalStatus,
    PreferredLanguage,
    AddressType,
    ResidenceType,
    PrimaryJurisdiction,
    DocumentCategory,
    KYCVerificationStatus,
    ScreeningType,
    ScreeningStatus
)

class CustomerProfile(Base):
    __tablename__ = "customer_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True)

    first_name = Column(String)
    middle_name = Column(String)
    last_name = Column(String)
    suffix = Column(SQLEnum(Suffix, native_enum = False))

    country_of_residence = Column(SQLEnum(Country,native_enum = False))
    nationality = Column(SQLEnum(Country,native_enum = False))
    dual_citizenship = Column(SQLEnum(YesNo,native_enum = False), default=YesNo.NO)

    date_of_birth = Column(Date)
    
    gender = Column(SQLEnum(Gender, native_enum = False))
    marital_status = Column(SQLEnum(MaritalStatus, native_enum = False))

    preferred_communication = Column(SQLEnum(PreferredCommunication,native_enum = False))
    preferred_language = Column(SQLEnum(PreferredLanguage, native_enum = False), default=PreferredLanguage.ENGLISH)
    
    kyc_state = Column(SQLEnum(KYCState,native_enum = False), default=KYCState.NOT_STARTED)
    primary_jurisdiction = Column(SQLEnum(PrimaryJurisdiction, native_enum=False), default=PrimaryJurisdiction.INDIA)
    cif_number = Column(String, unique=True, index=True, nullable=True)

    customer_status = Column(String, default="IN_PROGRESS")  # IN_PROGRESS / ACTIVE / BLOCKED

    pep_flag = Column(Boolean, default=False)
    high_risk_flag = Column(Boolean, default=False)

    fatca_required = Column(Boolean, default=False)
    kyc_reupload_requested = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    user = relationship("User", back_populates="customer_profile")

    addresses = relationship(
        "CustomerAddress",
        back_populates="customer_profile",
        cascade="all, delete-orphan"
    )

    employment_detail = relationship(
        "EmploymentDetail",
        back_populates="customer_profile",
        uselist=False,
        cascade="all, delete-orphan"
    )

    financial_information = relationship(
        "FinancialInformation",
        back_populates="customer_profile",
        uselist=False,
        cascade="all, delete-orphan"
    )

    kyc_document_submissions = relationship(
        "KYCDocumentSubmission",
        back_populates="customer_profile",
        cascade="all, delete-orphan"
    )

    risk_compliance_logs = relationship(
        "RiskComplianceLog",
        back_populates="customer_profile",
        cascade="all, delete-orphan"
    )


class CustomerAddress(Base):
    __tablename__ = "customer_addresses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_profile_id = Column(UUID(as_uuid=True), ForeignKey("customer_profiles.id"))

    address_line_1 = Column(String, nullable=True)
    address_line_2 = Column(String)
    city = Column(String)
    state = Column(String)
    postal_code = Column(String)
    country = Column(String)

    address_type = Column(SQLEnum(AddressType, native_enum=False))
    residence_type = Column(SQLEnum(ResidenceType, native_enum=False), nullable=True)
    same_as_current = Column(Boolean, default=False)
    is_kyc_verified = Column(Boolean, default=False)
    
    years_at_address = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer_profile = relationship("CustomerProfile", back_populates="addresses")


class EmploymentDetail(Base):
    __tablename__ = "employment_details"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_profile_id = Column(UUID(as_uuid=True), ForeignKey("customer_profiles.id"))

    employment_type = Column(SQLEnum(EmploymentType,native_enum = False))

    organisation_name= Column(String)
    organisation_country = Column(String)
    designation= Column(String)

    annual_income = Column(Numeric(15, 2))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer_profile = relationship("CustomerProfile", back_populates="employment_detail")


class FinancialInformation(Base):
    __tablename__ = "financial_information"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_profile_id = Column(UUID(as_uuid=True), ForeignKey("customer_profiles.id"))

    net_annual_income = Column(Numeric(15, 2))
    monthly_income = Column(Numeric(15, 2))
    other_income = Column(Numeric(15, 2))

    housing_payment = Column(Numeric(15, 2))
    other_obligations = Column(Numeric(15, 2))

    bankruptcy_flag = Column(Boolean, default=False)
    default_history_flag = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer_profile = relationship("CustomerProfile", back_populates="financial_information")


class KYCDocumentSubmission(Base):
    __tablename__ = "kyc_document_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kyc_profile_id = Column(UUID(as_uuid=True), ForeignKey("customer_profiles.id"))
    document_category = Column(SQLEnum(DocumentCategory, native_enum=False), nullable=False)
    document_type = Column(String, nullable=False)
    document_reference_masked = Column(String)
    document_reference_token = Column(String)
    s3_file_locator = Column(String)
    verification_status = Column(SQLEnum(KYCVerificationStatus, native_enum=False), default=KYCVerificationStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    customer_profile = relationship("CustomerProfile", back_populates="kyc_document_submissions")
    otp_verifications = relationship("KYCOTPVerification", back_populates="document_submission", cascade="all, delete-orphan")

class KYCOTPVerification(Base):
    __tablename__ = "kyc_otp_verifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_submission_id = Column(UUID(as_uuid=True), ForeignKey("kyc_document_submissions.id"))
    phone_number_masked = Column(String)
    otp_hash = Column(String)
    expires_at = Column(DateTime(timezone=True))
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document_submission = relationship("KYCDocumentSubmission", back_populates="otp_verifications")

class RiskComplianceLog(Base):
    __tablename__ = "risk_compliance_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kyc_profile_id = Column(UUID(as_uuid=True), ForeignKey("customer_profiles.id"))
    screening_type = Column(SQLEnum(ScreeningType, native_enum=False), nullable=False)
    status = Column(SQLEnum(ScreeningStatus, native_enum=False), default=ScreeningStatus.REVIEW_REQUIRED)
    match_score = Column(Numeric(5, 2))
    system_remarks = Column(String)
    audited_by = Column(UUID(as_uuid=True), nullable=True) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer_profile = relationship("CustomerProfile", back_populates="risk_compliance_logs")

class OTPPurpose(str, Enum):
    LOGIN = "LOGIN"
    REGISTRATION = "REGISTRATION"
    PASSWORD_RESET = "PASSWORD_RESET"
    ACTIVATION = "ACTIVATION"
    UNBLOCK = "UNBLOCK"


class OTPCode(Base):
    __tablename__ = "otp_codes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    email = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    otp_hash = Column(String, nullable=False)
    purpose = Column(SQLEnum(OTPPurpose,native_enum = False), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    linkage_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
# =====================================================
# FATCA DECLARATION TABLE
# =====================================================

class FATCADeclaration(Base):
    __tablename__ = "fatca_declarations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_profile_id = Column(UUID(as_uuid=True), ForeignKey("customer_profiles.id"), unique=True)

    us_citizen = Column(Boolean, default=False)
    us_tax_resident = Column(Boolean, default=False)
    us_tin = Column(String, nullable=True)

    declaration_signed_at = Column(DateTime(timezone=True), server_default=func.now())

    customer_profile = relationship("CustomerProfile")
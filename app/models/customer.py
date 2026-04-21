import uuid
from datetime import date, datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Numeric, Integer, LargeBinary

if TYPE_CHECKING:
    from app.models.auth import User
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from enum import Enum

from app.db.base_class import Base
from app.models.enums import (
    Country, CountryCode, Suffix, YesNo, CitizenshipDocumentType,
    EmploymentType, PreferredCommunication, TimeZone, KYCState, Gender,
    MaritalStatus, PreferredLanguage, AddressType, ResidenceType,
    PrimaryJurisdiction, DocumentCategory, KYCVerificationStatus,
    ScreeningType, ScreeningStatus
)

class CustomerProfile(Base):
    __tablename__ = "customer_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(20), ForeignKey("users.id"), unique=True)

    first_name: Mapped[Optional[str]] = mapped_column(String)
    middle_name: Mapped[Optional[str]] = mapped_column(String)
    last_name: Mapped[Optional[str]] = mapped_column(String)
    suffix: Mapped[Optional[Suffix]] = mapped_column(SQLEnum(Suffix, native_enum=False))

    country_of_residence: Mapped[Optional[Country]] = mapped_column(SQLEnum(Country, native_enum=False))
    nationality: Mapped[Optional[Country]] = mapped_column(SQLEnum(Country, native_enum=False))
    dual_citizenship: Mapped[YesNo] = mapped_column(SQLEnum(YesNo, native_enum=False), default=YesNo.NO)

    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    
    gender: Mapped[Optional[Gender]] = mapped_column(SQLEnum(Gender, native_enum=False))
    marital_status: Mapped[Optional[MaritalStatus]] = mapped_column(SQLEnum(MaritalStatus, native_enum=False))

    preferred_communication: Mapped[Optional[PreferredCommunication]] = mapped_column(SQLEnum(PreferredCommunication, native_enum=False))
    preferred_language: Mapped[PreferredLanguage] = mapped_column(SQLEnum(PreferredLanguage, native_enum=False), default=PreferredLanguage.ENGLISH)
    
    kyc_state: Mapped[KYCState] = mapped_column(SQLEnum(KYCState, native_enum=False), default=KYCState.NOT_STARTED)
    primary_jurisdiction: Mapped[PrimaryJurisdiction] = mapped_column(SQLEnum(PrimaryJurisdiction, native_enum=False), default=PrimaryJurisdiction.INDIA)

    customer_status: Mapped[str] = mapped_column(String, default="IN_PROGRESS")  # IN_PROGRESS / ACTIVE / BLOCKED

    pep_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    high_risk_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    fatca_required: Mapped[bool] = mapped_column(Boolean, default=False)
    kyc_reupload_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="customer_profile")

    addresses: Mapped[List["CustomerAddress"]] = relationship(
        "CustomerAddress",
        back_populates="customer_profile",
        cascade="all, delete-orphan"
    )

    employment_detail: Mapped[Optional["EmploymentDetail"]] = relationship(
        "EmploymentDetail",
        back_populates="customer_profile",
        uselist=False,
        cascade="all, delete-orphan"
    )

    financial_information: Mapped[Optional["FinancialInformation"]] = relationship(
        "FinancialInformation",
        back_populates="customer_profile",
        uselist=False,
        cascade="all, delete-orphan"
    )

    kyc_document_submissions: Mapped[List["KYCDocumentSubmission"]] = relationship(
        "KYCDocumentSubmission",
        back_populates="customer_profile",
        cascade="all, delete-orphan"
    )

    risk_compliance_logs: Mapped[List["RiskComplianceLog"]] = relationship(
        "RiskComplianceLog",
        back_populates="customer_profile",
        cascade="all, delete-orphan"
    )



class CustomerAddress(Base):
    __tablename__ = "customer_addresses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_profiles.id"))

    address_line_1: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address_line_2: Mapped[Optional[str]] = mapped_column(String)
    city: Mapped[Optional[str]] = mapped_column(String)
    state: Mapped[Optional[str]] = mapped_column(String)
    postal_code: Mapped[Optional[str]] = mapped_column(String)
    country: Mapped[Optional[str]] = mapped_column(String)

    address_type: Mapped[AddressType] = mapped_column(SQLEnum(AddressType, native_enum=False))
    residence_type: Mapped[Optional[ResidenceType]] = mapped_column(SQLEnum(ResidenceType, native_enum=False), nullable=True)
    same_as_current: Mapped[bool] = mapped_column(Boolean, default=False)
    is_kyc_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    years_at_address: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    customer_profile: Mapped["CustomerProfile"] = relationship("CustomerProfile", back_populates="addresses")


class EmploymentDetail(Base):
    __tablename__ = "employment_details"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_profiles.id"))

    employment_type: Mapped[EmploymentType] = mapped_column(SQLEnum(EmploymentType, native_enum=False))

    organisation_name: Mapped[Optional[str]] = mapped_column(String)
    organisation_country: Mapped[Optional[str]] = mapped_column(String)
    designation: Mapped[Optional[str]] = mapped_column(String)

    annual_income: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    customer_profile: Mapped["CustomerProfile"] = relationship("CustomerProfile", back_populates="employment_detail")


class FinancialInformation(Base):
    __tablename__ = "financial_information"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_profiles.id"))

    net_annual_income: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    monthly_income: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    other_income: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))

    housing_payment: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    other_obligations: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))

    bankruptcy_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    default_history_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    customer_profile: Mapped["CustomerProfile"] = relationship("CustomerProfile", back_populates="financial_information")


class KYCDocumentSubmission(Base):
    __tablename__ = "kyc_document_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kyc_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_profiles.id"))
    document_category: Mapped[DocumentCategory] = mapped_column(SQLEnum(DocumentCategory, native_enum=False), nullable=False)
    document_type: Mapped[str] = mapped_column(String, nullable=False)
    document_reference_masked: Mapped[Optional[str]] = mapped_column(String)
    document_reference_token: Mapped[Optional[str]] = mapped_column(String)
    # SECURITY: Files are stored outside the database. storage_path contains the reference.
    storage_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Kept for forward-compatibility with cloud storage migration
    s3_file_locator: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    verification_status: Mapped[KYCVerificationStatus] = mapped_column(SQLEnum(KYCVerificationStatus, native_enum=False), default=KYCVerificationStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer_profile: Mapped["CustomerProfile"] = relationship("CustomerProfile", back_populates="kyc_document_submissions")
    otp_verifications: Mapped[List["KYCOTPVerification"]] = relationship("KYCOTPVerification", back_populates="document_submission", cascade="all, delete-orphan")

class KYCOTPVerification(Base):
    __tablename__ = "kyc_otp_verifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kyc_document_submissions.id"))
    phone_number_masked: Mapped[Optional[str]] = mapped_column(String)
    otp_hash: Mapped[Optional[str]] = mapped_column(String)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document_submission: Mapped["KYCDocumentSubmission"] = relationship("KYCDocumentSubmission", back_populates="otp_verifications")

class RiskComplianceLog(Base):
    __tablename__ = "risk_compliance_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kyc_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_profiles.id"))
    screening_type: Mapped[ScreeningType] = mapped_column(SQLEnum(ScreeningType, native_enum=False), nullable=False)
    status: Mapped[ScreeningStatus] = mapped_column(SQLEnum(ScreeningStatus, native_enum=False), default=ScreeningStatus.REVIEW_REQUIRED)
    match_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    system_remarks: Mapped[Optional[str]] = mapped_column(String)
    audited_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True) 
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer_profile: Mapped["CustomerProfile"] = relationship("CustomerProfile", back_populates="risk_compliance_logs")

class OTPPurpose(str, Enum):
    """Valid OTP purposes for the ZBANQUe system."""
    REGISTRATION = "REGISTRATION"
    PASSWORD_RESET = "PASSWORD_RESET"
    ACTIVATION = "ACTIVATION"
    LOGIN = "LOGIN"


class OTPCode(Base):
    __tablename__ = "otp_codes"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("users.id"), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    otp_hash: Mapped[str] = mapped_column(String, nullable=False)
    purpose: Mapped[OTPPurpose] = mapped_column(SQLEnum(OTPPurpose, native_enum=False), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    linkage_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    

class FATCADeclaration(Base):
    __tablename__ = "fatca_declarations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_profiles.id"), unique=True)

    us_citizen: Mapped[bool] = mapped_column(Boolean, default=False)
    us_tax_resident: Mapped[bool] = mapped_column(Boolean, default=False)
    us_tin: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    declaration_signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    customer_profile: Mapped["CustomerProfile"] = relationship("CustomerProfile")
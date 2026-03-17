import uuid
from uuid import UUID
from typing import Optional, List, Union
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.models.enums import (
    ApplicationStatus, ApplicationStage, AccountStatus, CardType, CardStatus,
    InternalRiskRating, AutoPayType, AMLRiskCategory
)
from decimal import Decimal

def validate_currency_10_3(v: Decimal) -> Decimal:
    if v is None: return v
    if v < 0:
        raise ValueError("Value cannot be negative")
    if v >= Decimal("10000000000"):
        raise ValueError("Value must be less than 10 digits before decimal")
    str_v = str(v)
    if "." in str_v:
        decimals = len(str_v.split(".")[1])
        if decimals > 3:
            raise ValueError("only upto 4 digits after decimal")
    return v

# =====================================================
# CREDIT CARD APPLICATION
# =====================================================
class CreditCardApplicationCreate(BaseModel):
    user_id: UUID
    credit_product_id: UUID
    card_product_id: UUID
    employment_status: str
    declared_income: Optional[Decimal] = None

    @field_validator("declared_income")
    @classmethod
    def validate_income(cls, v):
        return validate_currency_10_3(v)

class CreditCardApplicationUpdate(BaseModel):
    application_status: Optional[ApplicationStatus] = None
    current_stage: Optional[ApplicationStage] = None
    rejection_reason_code: Optional[str] = None

    @field_validator("rejection_reason_code", mode="before")
    @classmethod
    def lowercase_codes(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

class CreditCardApplicationSummary(BaseModel):
    application_id: UUID = Field(validation_alias="id")
    cif_id: Optional[str] = Field(validation_alias="customer_cif_id")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class CreditCardApplicationResponse(BaseModel):
    id: UUID
    cif_id: Optional[str] = Field(validation_alias="customer_cif_id")
    user_id: UUID
    credit_product_id: UUID
    card_product_id: UUID
    
    application_status: ApplicationStatus
    current_stage: ApplicationStage
    
    employment_status: Optional[str]
    declared_income: Optional[float]
    bureau_score: Optional[int] = None
    risk_band: Optional[str] = None
    
    retry_count: int
    cooling_period_until: Optional[datetime]
    rejection_reason_code: Optional[str]
    rejection_reason: Optional[str]
    credit_account_id: Optional[UUID] = None
    
    submitted_at: datetime
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[UUID]

    @field_validator("rejection_reason_code", mode="before")
    @classmethod
    def lowercase_codes(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class ApplicationReviewRequest(BaseModel):
    rejection_reason: Optional[str] = None

class AdminKYCReviewRequest(BaseModel):
    notes: Optional[str] = None

class CreditAccountManualConfig(BaseModel):
    credit_limit: Decimal = Field(..., gt=0)
    cash_advance_limit: Decimal = Field(..., ge=0)
    billing_cycle_id: str = Field(
        ..., 
        pattern=r'^CYCLE_\d{2}$',
        description=(
            "Billing cycle identifier. Maps to the day of the month when statement is generated.\n"
            "- **CYCLE_01**: 1st of month\n"
            "- **CYCLE_05**: 5th of month\n"
            "- **CYCLE_10**: 10th of month\n"
            "- **CYCLE_15**: 15th of month\n"
            "- **CYCLE_20**: 20th of month\n"
            "- **CYCLE_25**: 25th of month\n"
            "- **CYCLE_28**: 28th of month"
        )
    )
    
    overlimit_allowed: bool = False
    overlimit_percentage: Decimal = Field(Decimal("0.0"), ge=0, le=100)

    autopay_enabled: bool = False
    autopay_type: Optional[AutoPayType] = None

    @field_validator("credit_limit", "cash_advance_limit", "overlimit_percentage")
    @classmethod
    def validate_nums(cls, v):
        return validate_currency_10_3(v)

class CreditSummary(BaseModel):
    total_credit_limit: Decimal
    available_credit: Decimal
    cash_advance_limit: Decimal
    used_credit: Decimal

class StatementSummary(BaseModel):
    opening_balance: Decimal
    payment_credits: Decimal
    purchase_debits: Decimal
    finance_charges: Decimal
    total_dues: Decimal

class BillingDetails(BaseModel):
    billing_cycle_day: int
    statement_date: date
    payment_due_date: date
    minimum_payment_due: Decimal
    statement_summary: StatementSummary
    credit_summary: CreditSummary

class CreditAccountResponse(BaseModel):
    credit_account_id: UUID = Field(validation_alias="id")
    application_id: Optional[UUID] = None
    cif_id: str = Field(validation_alias="customer_cif_id")
    credit_product_id: UUID
    card_product_id: UUID
    
    account_currency: str
    credit_limit: Decimal
    available_limit: Decimal
    cash_advance_limit: Decimal
    outstanding_amount: Decimal
    
    billing_cycle_id: str
    internal_risk_rating: Optional[InternalRiskRating]
    aml_risk_category: Optional[AMLRiskCategory]
    overlimit_allowed: bool
    overlimit_percentage: Optional[Decimal]
    
    account_status: AccountStatus
    opened_at: datetime
    
    created_by: Optional[UUID] = None
    approved_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class CustomerCreditAccountResponse(BaseModel):
    readable_id: str
    customer_id: str = Field(validation_alias="customer_cif_id")
    card_product_name: str
    account_status: AccountStatus
    opened_at: datetime
    account_currency: str
    billing_details: BillingDetails

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class ApplicationApprovedResponse(BaseModel):
    credit_account_id: UUID
    application_status: ApplicationStatus = ApplicationStatus.APPROVED
    account_details: CreditAccountResponse
    message: Optional[str] = None

class ApplicationRejectedResponse(BaseModel):
    application_status: ApplicationStatus = ApplicationStatus.REJECTED
    rejection_reason: Optional[str] = None
    message: Optional[str] = None

ApplicationReviewResponse = Union[ApplicationApprovedResponse, ApplicationRejectedResponse]

class IssueCardRequest(BaseModel):
    card_product_id: UUID
    card_type: CardType = CardType.PRIMARY

class CardActivationRequest(BaseModel):
    otp: str = Field(..., pattern=r'^\d{6}$')

class SetPinRequest(BaseModel):
    pin: str = Field(..., pattern=r'^\d{4}$')

class CardResponse(BaseModel):
    id: UUID
    credit_account_id: UUID
    card_product_id: UUID
    card_type: CardType
    
    pan_masked: str
    expiry_date_masked: str
    cvv_masked: str
    
    card_status: CardStatus
    issued_at: datetime
    activation_date: Optional[datetime] = None
    
    international_usage_enabled: bool
    ecommerce_enabled: bool
    atm_enabled: bool

    model_config = ConfigDict(from_attributes=True)

class CustomerCardResponse(BaseModel):
    card_id: UUID = Field(validation_alias="id")
    card_readable_id: str = Field(validation_alias="readable_id")
    credit_account_id: UUID
    card_product_name: str
    card_type: CardType
    pan_masked: str
    expiry_date_masked: str
    cvv_masked: str
    card_status: CardStatus
    issued_at: datetime
    activation_date: Optional[datetime] = None
    international_usage_enabled: bool
    ecommerce_enabled: bool
    atm_enabled: bool
    card_holder_name: str
    card_network: str
    card_variant: str
    account_currency: str = "INR"

    model_config = ConfigDict(from_attributes=True)

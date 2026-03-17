from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator, condecimal
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from app.models.enums import (
    CCMAccountStatus, CCMAccountRiskFlag, CCMAdjustmentType, 
    CCMLedgerEntryType, CCMLimitReasonCode, CCMStatusReasonCode, 
    CCMAdjustmentReasonCode, CardVariant
)

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
            raise ValueError("only upto 4 digits after decimal") # Error if 4 or more
    return v

# --- Request Schemas ---

class EffectiveFromDate(BaseModel):
    Year: int = Field(..., ge=2024)
    Month: int = Field(..., ge=1, le=12)
    Date: int = Field(..., ge=1, le=31, alias="Date")

class CreditLimitUpdateRequest(BaseModel):
    new_credit_limit: condecimal(max_digits=13, decimal_places=3, gt=0)
    reason_code: CCMLimitReasonCode
    notes: Optional[str] = None
    effective_from: EffectiveFromDate

    @field_validator("new_credit_limit")
    @classmethod
    def validate_limits(cls, v):
        return validate_currency_10_3(v)

class AccountStatusUpdateRequest(BaseModel):
    status: CCMAccountStatus
    reason_code: CCMStatusReasonCode
    notes: Optional[str] = None

class AccountFreezeRequest(BaseModel):
    freeze: bool
    reason_code: CCMStatusReasonCode
    notes: Optional[str] = None

class BillingCycleUpdateRequest(BaseModel):
    billing_cycle_day: int = Field(..., ge=1, le=28)
    grace_period: int = Field(..., ge=1, alias="grace period")
    
    model_config = ConfigDict(populate_by_name=True)

class RiskFlagUpdateRequest(BaseModel):
    risk_flag: CCMAccountRiskFlag
    reason: str
    
    @field_validator("reason", mode="before")
    @classmethod
    def lowercase_reason(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

class InterestUpdateRequest(BaseModel):
    purchase_apr: condecimal(max_digits=13, decimal_places=3, ge=0)
    cash_apr: condecimal(max_digits=13, decimal_places=3, ge=0)
    penalty_apr: condecimal(max_digits=13, decimal_places=3, ge=0)

    @field_validator("purchase_apr", "cash_apr", "penalty_apr")
    @classmethod
    def validate_apr(cls, v):
        return validate_currency_10_3(v)

class OverlimitConfigRequest(BaseModel):
    overlimit_enabled: bool
    overlimit_buffer: condecimal(max_digits=13, decimal_places=3, ge=0) = Decimal("0.0")
    overlimit_fee: condecimal(max_digits=13, decimal_places=3, ge=0) = Decimal("0.0")

class ManualAdjustmentRequest(BaseModel):
    adjustment_type: CCMAdjustmentType
    amount: condecimal(max_digits=13, decimal_places=3, gt=0)
    reason_code: CCMAdjustmentReasonCode
    notes: Optional[str] = None

# --- Response Schemas ---

class AdminCardSummary(BaseModel):
    card_id: UUID = Field(..., validation_alias="id")
    card_number: str
    status: str
    card_type: Optional[str] = None
    issued_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class CreditAccountSummary(BaseModel):
    credit_account_id: UUID = Field(..., validation_alias="id")
    user_id: UUID
    product_code: Optional[str]
    status: CCMAccountStatus
    credit_limit: condecimal(max_digits=13, decimal_places=3)
    available_credit: condecimal(max_digits=13, decimal_places=3)
    outstanding_balance: condecimal(max_digits=13, decimal_places=3)
    billing_cycle_day: int
    card_count: int = 0
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "populate_by_name": True
    }

    @field_validator("credit_limit", "available_credit", "outstanding_balance")
    @classmethod
    def validate_summary_nums(cls, v):
        return validate_currency_10_3(v)

class CreditAccountDetail(CreditAccountSummary):
    cash_limit: condecimal(max_digits=13, decimal_places=3)
    interest_rate: condecimal(max_digits=13, decimal_places=3)
    late_fee: condecimal(max_digits=13, decimal_places=3)
    grace_period: int = Field(..., alias="payment_due_days")
    
    # APRs
    purchase_apr: condecimal(max_digits=13, decimal_places=3)
    cash_apr: condecimal(max_digits=13, decimal_places=3)
    penalty_apr: condecimal(max_digits=13, decimal_places=3)
    
    risk_flag: CCMAccountRiskFlag
    overlimit_enabled: bool
    overlimit_buffer: condecimal(max_digits=13, decimal_places=3)
    overlimit_fee: condecimal(max_digits=13, decimal_places=3)
    
    cards: List[AdminCardSummary] = []
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("cash_limit", "interest_rate", "late_fee", "purchase_apr", "cash_apr", "penalty_apr", "overlimit_buffer", "overlimit_fee")
    @classmethod
    def validate_detail_nums(cls, v):
        return validate_currency_10_3(v)

class CreditLimitUpdateResponse(BaseModel):
    credit_account_id: UUID
    old_credit_limit: condecimal(max_digits=13, decimal_places=3)
    new_credit_limit: condecimal(max_digits=13, decimal_places=3)
    available_credit: condecimal(max_digits=13, decimal_places=3)
    updated_by: UUID
    updated_at: datetime

class AccountStatusUpdateResponse(BaseModel):
    credit_account_id: UUID
    previous_status: CCMAccountStatus
    new_status: CCMAccountStatus
    updated_at: datetime

class AccountFreezeResponse(BaseModel):
    credit_account_id: UUID
    freeze_status: str # "FROZEN" or "ACTIVE"
    reason_code: str
    updated_at: datetime

class BillingCycleUpdateResponse(BaseModel):
    credit_account_id: UUID
    billing_cycle_day: int
    grace_period: int = Field(..., alias="payment_due_days")
    next_statement_date: datetime

    model_config = ConfigDict(populate_by_name=True)

class RiskFlagUpdateResponse(BaseModel):
    credit_account_id: UUID
    risk_flag: CCMAccountRiskFlag
    updated_at: datetime

class InterestUpdateResponse(BaseModel):
    credit_account_id: UUID
    purchase_apr: condecimal(max_digits=13, decimal_places=3)
    cash_apr: condecimal(max_digits=13, decimal_places=3)
    penalty_apr: condecimal(max_digits=13, decimal_places=3)

    @field_validator("purchase_apr", "cash_apr", "penalty_apr")
    @classmethod
    def validate_apr_resp(cls, v):
        return validate_currency_10_3(v)

class OverlimitConfigResponse(BaseModel):
    credit_account_id: UUID
    overlimit_enabled: bool
    overlimit_buffer: condecimal(max_digits=13, decimal_places=3)
    overlimit_fee: condecimal(max_digits=13, decimal_places=3)

    @field_validator("overlimit_buffer", "overlimit_fee")
    @classmethod
    def validate_overlimit_resp(cls, v):
        return validate_currency_10_3(v)

class AdjustmentResponse(BaseModel):
    adjustment_id: UUID = Field(..., validation_alias="id")
    credit_account_id: UUID
    amount: condecimal(max_digits=13, decimal_places=3)
    adjustment_type: CCMAdjustmentType
    new_outstanding_balance: condecimal(max_digits=13, decimal_places=3)
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "populate_by_name": True
    }

class LedgerEntryResponse(BaseModel):
    entry_id: UUID = Field(..., validation_alias="id")
    type: CCMLedgerEntryType = Field(..., validation_alias="entry_type")
    amount: condecimal(max_digits=13, decimal_places=3)
    description: str
    balance_before: condecimal(max_digits=13, decimal_places=3)
    balance_after: condecimal(max_digits=13, decimal_places=3)
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "populate_by_name": True
    }

class LedgerResponse(BaseModel):
    credit_account_id: UUID
    ledger_entries: List[LedgerEntryResponse]

class PaginatedAccountsResponse(BaseModel):
    page: int
    limit: int
    total_records: int
    accounts: List[CreditAccountSummary]

class AccountLimitsResponse(BaseModel):
    credit_account_id: UUID
    credit_limit: condecimal(max_digits=13, decimal_places=3)
    available_credit: condecimal(max_digits=13, decimal_places=3)
    cash_limit: condecimal(max_digits=13, decimal_places=3)
    outstanding_balance: condecimal(max_digits=13, decimal_places=3)

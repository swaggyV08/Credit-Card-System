import uuid
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, condecimal, ConfigDict, field_validator, model_validator

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
            raise ValueError("only upto 4 digits after decimal") # Failure if 4+
    return v
from app.models.enums import (
    CardNetwork, CardVariant, CCMCommand, CCMReissueReason, CCMReissueType,
    CCMCardStatus, CCMTransactionType, CCMTransactionStatus, CCMFraudBlockReason
)

# -----------------
# Base Account
# -----------------
class CCMCreditAccountBase(BaseModel):
    credit_limit: condecimal(max_digits=13, decimal_places=3, ge=0) = Field(..., json_schema_extra={"example": "0000000000.000"})
    available_credit: condecimal(max_digits=13, decimal_places=3, ge=0) = Field(..., json_schema_extra={"example": "0000000000.000"})
    outstanding_balance: condecimal(max_digits=13, decimal_places=3, ge=0) = Field(..., json_schema_extra={"example": "0000000000.000"})
    cash_limit: condecimal(max_digits=13, decimal_places=3, ge=0) = Field(..., json_schema_extra={"example": "0000000000.000"})
    billing_cycle_day: int
    minimum_due: condecimal(max_digits=13, decimal_places=3, ge=0) = Field(..., json_schema_extra={"example": "0000000000.000"})
    interest_rate: condecimal(max_digits=13, decimal_places=3, ge=0) = Field(..., json_schema_extra={"example": "0000000000.000"})
    late_fee: condecimal(max_digits=13, decimal_places=3, ge=0) = Field(..., json_schema_extra={"example": "0000000000.000"})

    @field_validator("credit_limit", "available_credit", "outstanding_balance", "cash_limit", "minimum_due", "interest_rate", "late_fee")
    @classmethod
    def validate_acc_nums(cls, v):
        return validate_currency_10_3(v)
    status: str
    last_statement_date: Optional[datetime]

class CCMCreditAccountResponse(CCMCreditAccountBase):
    id: uuid.UUID
    card_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)

# -----------------
# Base Card
# -----------------
class CCMCreditCardBase(BaseModel):
    user_id: uuid.UUID = Field(..., description="Unique identifier of the cardholder/user")
    card_number: str = Field(..., description="Full PAN (Primary Account Number), usually masked in responses")
    card_network: CardNetwork = Field(..., description="Payment network (e.g., VISA, MASTERCARD, RUPAY)")
    card_variant: CardVariant = Field(..., description="Card tier (e.g., CLASSIC, PLATINUM, INFINITE)")
    expiry_date: str = Field(..., description="Card expiry in MM/YY format")
    status: CCMCardStatus = Field(..., description="Lifecycle status: CREATED(Dispatched), ISSUED(Dispatched), INACTIVE(Received), ACTIVE(Usable), BLOCKED_USER(Frozen by user), BLOCKED_FRAUD(Security hold), TERMINATED(Closed)")
    
    is_virtual: bool = Field(True, description="True if the card is a digital-only instance")
    is_contactless_enabled: bool = Field(True, description="Control for NFC/Tap-to-pay transactions")
    is_international_enabled: bool = Field(False, description="Control for cross-border/Foreign currency transactions")
    is_online_enabled: bool = Field(True, description="Control for E-commerce/CNP transactions")
    is_atm_enabled: bool = Field(True, description="Control for Cash withdrawals at ATMs")
    is_domestic_enabled: bool = Field(True, description="Control for within-country transactions")
    
    daily_spend_limit: Optional[condecimal(max_digits=13, decimal_places=3, ge=0)] = Field(None, description="Maximum total spend allowed per 24h cycle", json_schema_extra={"example": "0000000000.000"})
    daily_withdraw_limit: Optional[condecimal(max_digits=13, decimal_places=3, ge=0)] = Field(None, description="Maximum total ATM withdrawal allowed per 24h cycle", json_schema_extra={"example": "0000000000.000"})

    @field_validator("daily_spend_limit", "daily_withdraw_limit")
    @classmethod
    def validate_card_nums(cls, v):
        return validate_currency_10_3(v)
    
    issued_at: Optional[datetime] = Field(None, description="Timestamp when the card was physically or digitally generated")
    activated_at: Optional[datetime] = Field(None, description="Timestamp of the first successful PIN set/activation")
    blocked_reason: Optional[CCMFraudBlockReason] = Field(None, description="Specific reason code if the card is currently unavailable")

class CCMCreditCardResponse(CCMCreditCardBase):
    id: uuid.UUID = Field(..., description="Unique internal card instance UUID")
    created_at: datetime = Field(..., description="Audit timestamp of record creation")
    updated_at: Optional[datetime] = Field(None, description="Audit timestamp of last state change")
    credit_account: Optional[CCMCreditAccountResponse] = Field(None, description="Associated credit line details")

    model_config = ConfigDict(from_attributes=True)

# -----------------
# Requests (Issue / Activate / etc.)
# -----------------

# -----------------
# Professional Response Schemas
# -----------------

class CardIssuanceResponse(BaseModel):
    message: str = "Card issued successfully"
    card_id: uuid.UUID
    last_4_digits: str
    expiry: str
    status: str
    delivery: str = "In progress"

class CardActivationResponse(BaseModel):
    message: str = "Activation initiated"
    old_status: CCMCardStatus
    new_status: CCMCardStatus
    activation_id: uuid.UUID
    card_id: uuid.UUID

class CardActionResponse(BaseModel):
    message: str
    old_status: CCMCardStatus
    new_status: CCMCardStatus
    card_id: Optional[uuid.UUID] = None
    unblock_id: Optional[str] = None

# -----------------
# Requests (Issue / Activate / etc.)
# -----------------

class CCMCardIssueRequest(BaseModel):
    credit_account_id: uuid.UUID = Field(..., description="The account associated with the new card")
    card_product_id: uuid.UUID = Field(..., description="The template/product ID for the card")
    card_type: CCMReissueType = Field(..., description="PHYSICAL or VIRTUAL")
    embossed_name: str = Field(..., min_length=2, description="The name as it will appear on the card")
    delivery_address: str = Field(..., min_length=5, description="The shipping destination")

    @field_validator("embossed_name")
    def validate_name(cls, v):
        if not all(x.isalpha() or x.isspace() for x in v):
            raise ValueError("Embossed name must only contain letters and spaces")
        return v.upper()

class CCMCardActivationRequest(BaseModel):
    # For Stage 1: command=generate (no specialized body usually, but linkage_id will be returned)
    # For Stage 3: command=activate
    pin: Optional[str] = Field(None, min_length=4, max_length=4, pattern=r"^\d{4}$", description="4-digit numeric PIN")
    activation_id: Optional[uuid.UUID] = Field(None, description="The unique ID returned in Stage 1")

    @model_validator(mode='after')
    def validate_activate_logic(self) -> 'CCMCardActivationRequest':
        # If this is for the 'activate' command, both must be present
        return self

class CCMCardBlockRequest(BaseModel):
    reason: CCMFraudBlockReason = Field(..., description="Reason for blocking: LOST, STOLEN, FRAUD, TEMPORARY_BLOCK")

class CCMCardUnblockRequest(BaseModel):
    reason: Optional[str] = Field("CARD_FOUND", description="Reason for unblocking (e.g., Card found)")
    
    @field_validator("reason", mode="before")
    @classmethod
    def lowercase_reason(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

class CCMCardReplaceRequest(BaseModel):
    reason: CCMReissueReason = Field(..., description="DAMAGED, LOST, UPGRADE")
    reissue_type: CCMReissueType = Field(..., description="PHYSICAL or VIRTUAL")
    delivery_address: str = Field(..., min_length=5, alias="Delivery Address")

    model_config = ConfigDict(populate_by_name=True)

class CCMCardTerminateRequest(BaseModel):
    reason: str = Field(..., min_length=5, description="Reason for closing (e.g., No longer needed, Switching bank)")

    @field_validator("reason", mode="before")
    @classmethod
    def lowercase_reason(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

class CCMCardRenewRequest(BaseModel):
    reissue_type: CCMReissueType = Field(..., description="Type of renewal card: PHYSICAL or VIRTUAL")
    delivery_address: str = Field(..., min_length=5, description="Shipping destination for the renewed card")

# -----------------
# Transactions
# -----------------
class CCMCardTransactionBase(BaseModel):
    card_id: uuid.UUID
    amount: condecimal(max_digits=13, decimal_places=3, gt=0) = Field(..., json_schema_extra={"example": "0000000000.000"})

    @field_validator("amount")
    @classmethod
    def validate_txn_nums(cls, v):
        return validate_currency_10_3(v)
    merchant_name: str
    merchant_category: Optional[str] = None
    currency: str = "INR"
    transaction_type: CCMTransactionType
    geo_location: Optional[str] = None

    @field_validator("merchant_name", "merchant_category", "currency", mode="before")
    @classmethod
    def lowercase_txn_strings(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

class CCMCardTransactionResponse(BaseModel):
    transaction_id: uuid.UUID = Field(..., alias="id")
    amount: condecimal(max_digits=13, decimal_places=3) = Field(..., json_schema_extra={"example": "0000000000.000"})
    merchant: str = Field(..., alias="merchant_name")
    status: CCMTransactionStatus
    is_fraud_flagged: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class CCMChargeRequest(BaseModel):
    card_id: uuid.UUID
    amount: condecimal(max_digits=13, decimal_places=3, gt=0) = Field(..., json_schema_extra={"example": "0000000000.000"})
    merchant_name: str
    merchant_category: Optional[str] = None
    currency: str = "INR"
    transaction_type: CCMTransactionType = CCMTransactionType.PURCHASE
    geo_location: Optional[str] = None

    @field_validator("merchant_name", "merchant_category", "currency", mode="before")
    @classmethod
    def lowercase_charge_strings(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

class CCMTransactionReverseRequest(BaseModel):
    transaction_id: uuid.UUID

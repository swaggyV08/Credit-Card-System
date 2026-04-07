"""
Transaction Schemas — Request/Response models for Groups 1–5
Covers: Transactions, Holds, Clearing, Settlement, Disputes, Refunds
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict

from app.models.transactions.enums import (
    TransactionType, TransactionStatus, POSEntryMode, RiskTier,
    HoldStatus, ClearingBatchStatus, SettlementRunStatus, NetworkType,
    DisputeType, DisputeStatus, ProvisionalCreditStatus,
)


# =====================================================
# GROUP 1 — TRANSACTION SCHEMAS
# =====================================================
class BillingAddressSchema(BaseModel):
    line1: str
    line2: str | None = None
    city: str
    state: str
    postal_code: str
    country: str


class CreateTransactionRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, decimal_places=2, description="Transaction amount (>0, 2 decimal places)")
    currency: str = Field(default="INR", min_length=3, max_length=3, description="ISO 4217 currency code")
    transaction_type: TransactionType
    merchant_id: UUID
    merchant_name: str = Field(..., min_length=1, max_length=255)
    merchant_category_code: str = Field(..., min_length=4, max_length=4, description="4-digit MCC")
    merchant_country: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2")
    card_not_present: bool = False
    billing_address: BillingAddressSchema | None = None
    cvv2: str | None = Field(None, min_length=3, max_length=4)
    terminal_id: str | None = None
    pos_entry_mode: POSEntryMode | None = None
    installments: int | None = Field(None, ge=1, description="EMI splits, 1=no split")
    metadata: dict | None = None

    @field_validator("cvv2")
    @classmethod
    def cvv2_required_if_cnp(cls, v, info):
        if info.data.get("card_not_present") and not v:
            raise ValueError("CVV2 is required for card-not-present transactions")
        return v

    @field_validator("merchant_category_code")
    @classmethod
    def validate_mcc(cls, v):
        if not v.isdigit():
            raise ValueError("MCC must be a 4-digit numeric code")
        return v


class TransactionResponse(BaseModel):
    transaction_id: UUID
    auth_code: str | None
    status: str
    amount: Decimal
    currency: str
    available_credit: Decimal
    hold_id: UUID | None = None
    hold_expiry: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TransactionSummarySchema(BaseModel):
    id: UUID
    amount: Decimal
    currency: str
    transaction_type: str
    status: str
    merchant_name: str | None
    merchant_category_code: str | None
    merchant_country: str | None
    card_not_present: bool
    auth_code: str | None
    created_at: datetime
    fraud_score: float | None = None
    internal_flag: bool = False
    active_holds: list["HoldSchema"] | None = None

    model_config = ConfigDict(from_attributes=True)


class TransactionDetailSchema(TransactionSummarySchema):
    card_id: UUID
    account_id: UUID
    merchant_id: UUID | None
    terminal_id: str | None
    pos_entry_mode: str | None
    installments: int | None
    parent_txn_id: UUID | None
    risk_tier: str | None
    internal_flag_reason: str | None
    idempotency_key: str | None
    metadata_json: dict | None
    updated_at: datetime
    dispute: Optional["DisputeSummarySchema"] = None

    model_config = ConfigDict(from_attributes=True)


class TransactionCommandRequest(BaseModel):
    amount: Decimal | None = None
    reason: str | None = None
    internal_notes: str | None = None
    flag_reason: str | None = None
    unflag_reason: str | None = None


# =====================================================
# GROUP 2 — HOLD SCHEMAS
# =====================================================
class HoldSchema(BaseModel):
    id: UUID
    transaction_id: UUID
    card_id: UUID
    amount: Decimal
    currency: str
    status: str
    hold_expiry: datetime
    release_reason: str | None
    released_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HoldReleaseRequest(BaseModel):
    release_reason: str = Field(..., min_length=5, description="Reason for manual hold release")


class HoldSummaryResponse(BaseModel):
    holds: list[HoldSchema]
    total_hold_amount: Decimal
    available_credit: Decimal


# =====================================================
# GROUP 3 — CLEARING SCHEMAS
# =====================================================
class ClearingRecordInput(BaseModel):
    auth_code: str
    merchant_id: UUID
    amount: Decimal
    clearing_amount: Decimal
    currency: str = "INR"
    txn_date: datetime


class CreateClearingBatchRequest(BaseModel):
    network: NetworkType
    file_reference: str | None = None
    clearing_records: list[ClearingRecordInput]


class ClearingBatchResponse(BaseModel):
    batch_id: UUID
    processed: int
    matched: int
    exceptions: int
    force_posts: int

    model_config = ConfigDict(from_attributes=True)


class ClearingBatchDetailSchema(BaseModel):
    id: UUID
    network: str
    file_reference: str | None
    status: str
    processed_count: int
    matched_count: int
    exception_count: int
    force_post_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =====================================================
# GROUP 3 — SETTLEMENT SCHEMAS
# =====================================================
class CreateSettlementRequest(BaseModel):
    settlement_date: date
    network: NetworkType
    cutoff_datetime: datetime


class SettlementRunResponse(BaseModel):
    settlement_run_id: UUID
    cards_settled: int
    total_amount: Decimal
    failed_count: int

    model_config = ConfigDict(from_attributes=True)


class SettlementRunDetailSchema(BaseModel):
    id: UUID
    network: str
    settlement_date: date
    status: str
    total_amount: Decimal
    cards_settled: int
    failed_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =====================================================
# GROUP 4 — DISPUTE SCHEMAS
# =====================================================
class CreateDisputeRequest(BaseModel):
    dispute_type: DisputeType
    description: str = Field(..., min_length=20, description="Detailed dispute description (min 20 chars)")
    transaction_amount_disputed: Decimal = Field(..., gt=0)
    supporting_documents: list[str] | None = None
    request_provisional_credit: bool = True


class DisputeResponse(BaseModel):
    dispute_id: UUID
    case_number: str
    status: str
    provisional_credit_issued: bool
    deadline: datetime
    next_steps: str

    model_config = ConfigDict(from_attributes=True)


class DisputeSummarySchema(BaseModel):
    id: UUID
    case_number: str
    dispute_type: str
    status: str
    amount_disputed: Decimal
    deadline: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DisputeDetailSchema(DisputeSummarySchema):
    transaction_id: UUID
    card_id: UUID
    description: str
    resolution: str | None
    resolved_at: datetime | None
    resolved_by: str | None
    provisional_credit_id: UUID | None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DisputeCommandRequest(BaseModel):
    """Discriminated body for dispute state machine commands."""
    resolution: str | None = None
    documents: list[str] | None = None
    statement: str | None = None
    escalation_reason: str | None = None
    compliance_officer_id: str | None = None
    chargeback_reason_code: str | None = None
    withdrawal_reason: str | None = None


# =====================================================
# GROUP 5 — REFUND SCHEMAS
# =====================================================
class CreateRefundRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    reason: str = Field(..., min_length=5)
    merchant_reference: str | None = None
    partial: bool = False


class RefundResponse(BaseModel):
    refund_transaction_id: UUID
    credited_amount: Decimal
    new_balance: Decimal
    new_available_credit: Decimal
    posted_at: datetime

    model_config = ConfigDict(from_attributes=True)

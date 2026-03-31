"""
Statement, Fee, Payment, Controls, Risk, Audit Schemas — Groups 6–11
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from app.models.transactions.enums import (
    FeeType, PaymentSource, StatementStatus, ExportFormat,
    LineItemType,
)


# =====================================================
# GROUP 6 — STATEMENT SCHEMAS
# =====================================================
class StatementSummarySchema(BaseModel):
    id: UUID
    card_id: UUID
    cycle_start: date
    cycle_end: date
    status: str
    opening_balance: Decimal
    closing_balance: Decimal
    total_purchases: Decimal
    total_cash_advances: Decimal
    total_fees: Decimal
    total_credits: Decimal
    minimum_due: Decimal
    payment_due_date: date | None
    fully_paid: bool
    min_paid: bool

    model_config = ConfigDict(from_attributes=True)


class StatementLineItemSchema(BaseModel):
    id: UUID
    line_type: str
    description: str
    amount: Decimal
    line_date: date
    transaction_id: UUID | None

    model_config = ConfigDict(from_attributes=True)


class StatementDetailSchema(StatementSummarySchema):
    line_items: list[StatementLineItemSchema] = []


class CreateExportRequest(BaseModel):
    format: ExportFormat


class ExportJobResponse(BaseModel):
    export_job_id: UUID
    status: str = "QUEUED"
    poll_url: str


# =====================================================
# GROUP 7 — FEE SCHEMAS
# =====================================================
class FeeSchema(BaseModel):
    id: UUID
    card_id: UUID
    fee_type: str
    amount: Decimal
    currency: str
    waived: bool
    waiver_reason: str | None
    waived_by: str | None
    linked_transaction_id: UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreateFeeRequest(BaseModel):
    fee_type: FeeType
    amount: Decimal = Field(..., gt=0)
    reason: str = Field(..., min_length=3)
    waived: bool = False
    waiver_reason: str | None = None


class FeeWaiveRequest(BaseModel):
    waiver_reason: str = Field(..., min_length=5, description="Mandatory reason for waiving the fee")


class InterestPostRequest(BaseModel):
    """System-only: monthly interest calculation input."""
    billing_cycle_days: int = Field(..., gt=0)
    average_daily_balance: Decimal = Field(..., ge=0)
    purchase_apr: Decimal = Field(..., ge=0)
    cash_advance_apr: Decimal = Field(..., ge=0)
    penalty_apr: Decimal | None = None
    previous_cycle_fully_paid: bool = False


# =====================================================
# GROUP 8 — PAYMENT SCHEMAS
# =====================================================
class CreatePaymentRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    payment_source: PaymentSource
    source_reference: str = Field(..., min_length=3)
    payment_date: date | None = None
    remarks: str | None = None


class PaymentSchema(BaseModel):
    id: UUID
    card_id: UUID
    amount: Decimal
    currency: str
    status: str
    payment_source: str
    source_reference: str
    allocation_breakdown: dict | None
    payment_date: date
    posted_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentResponse(BaseModel):
    payment_id: UUID
    status: str
    amount: Decimal
    new_balance: Decimal
    new_available_credit: Decimal
    allocation_breakdown: dict | None

    model_config = ConfigDict(from_attributes=True)


class PaymentCommandRequest(BaseModel):
    reason: str | None = None


# =====================================================
# GROUP 9 — CONTROLS SCHEMAS
# =====================================================
class CardControlSchema(BaseModel):
    international_transactions_enabled: bool
    online_transactions_enabled: bool
    contactless_enabled: bool
    atm_withdrawals_enabled: bool
    mcc_blocks: list[str] | None
    daily_limit: Decimal | None
    single_transaction_limit: Decimal | None
    monthly_limit: Decimal | None
    allowed_countries: list[str] | None

    model_config = ConfigDict(from_attributes=True)


class UpdateCardControlRequest(BaseModel):
    international_transactions_enabled: bool | None = None
    online_transactions_enabled: bool | None = None
    contactless_enabled: bool | None = None
    atm_withdrawals_enabled: bool | None = None
    mcc_blocks: list[str] | None = None
    daily_limit: Decimal | None = None
    single_transaction_limit: Decimal | None = None
    monthly_limit: Decimal | None = None
    allowed_countries: list[str] | None = None





# =====================================================
# GROUP 11 — RECONCILIATION & AUDIT SCHEMAS
# =====================================================
class ReconciliationSummarySchema(BaseModel):
    date: date
    total_authorized: Decimal
    total_cleared: Decimal
    total_settled: Decimal
    total_reversed: Decimal
    total_disputed: Decimal
    total_fees_collected: Decimal
    interchange_earned: Decimal
    open_holds_count: int
    open_holds_amount: Decimal
    exceptions_count: int


class AuditLogSchema(BaseModel):
    id: UUID
    entity_type: str
    entity_id: str
    action: str
    actor_id: str | None
    actor_role: str | None
    ip_address: str | None
    before_state: dict | None
    after_state: dict | None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

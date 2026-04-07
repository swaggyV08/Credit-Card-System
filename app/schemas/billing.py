"""
Billing & Payment Schemas — Week 5
All Pydantic models for billing generation, statement views, payment processing,
and fraud flag summaries.

Design: Uses Decimal (never float) for money. All timestamps are tz-aware.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ─── Statement Schemas ─────────────────────────────────

class StatementLineItemSchema(BaseModel):
    """Single line item inside a statement."""
    id: UUID
    line_type: str
    description: str
    amount: Decimal = Field(..., decimal_places=2)
    transaction_date: date
    transaction_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class StatementSummary(BaseModel):
    """Lightweight statement overview for list endpoints."""
    id: UUID
    credit_account_id: UUID
    card_id: UUID
    cycle_start: date
    cycle_end: date
    payment_due_date: date
    opening_balance: Decimal = Field(..., decimal_places=2)
    closing_balance: Decimal = Field(..., decimal_places=2)
    minimum_due: Decimal = Field(..., decimal_places=2)
    total_amount_due: Decimal = Field(..., decimal_places=2)
    status: str
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StatementDetail(StatementSummary):
    """Full statement with all financial breakdowns and line items."""
    total_purchases: Decimal = Field(..., decimal_places=2)
    total_cash_advances: Decimal = Field(..., decimal_places=2)
    total_fees: Decimal = Field(..., decimal_places=2)
    total_interest: Decimal = Field(..., decimal_places=2)
    total_credits: Decimal = Field(..., decimal_places=2)
    total_payments: Decimal = Field(..., decimal_places=2)
    line_items: list[StatementLineItemSchema] = []

    model_config = ConfigDict(from_attributes=True)


# ─── Payment Schemas ───────────────────────────────────

class PaymentCreateRequest(BaseModel):
    """Request to make a payment on a credit card."""
    amount: Decimal = Field(..., gt=0, decimal_places=2, description="Payment amount in INR")
    payment_source: str = Field(..., description="BANK_ACCOUNT | NEFT | RTGS | UPI | CHEQUE")
    reference_no: str = Field(..., min_length=3, max_length=64, description="External payment reference")
    payment_date: date | None = None

    @field_validator("payment_source")
    @classmethod
    def validate_payment_source(cls, v: str) -> str:
        allowed = {"BANK_ACCOUNT", "BANK_TRANSFER", "NEFT", "RTGS", "UPI", "CHEQUE"}
        if v.upper() not in allowed:
            raise ValueError(f"payment_source must be one of {allowed}")
        return v.upper()


class PaymentResponse(BaseModel):
    """Response after payment processing."""
    payment_id: UUID
    card_id: UUID
    amount: Decimal = Field(..., decimal_places=2)
    status: str
    reference_no: str
    payment_date: date
    allocated_fees: Decimal = Field(..., decimal_places=2)
    allocated_interest: Decimal = Field(..., decimal_places=2)
    allocated_cash_advance: Decimal = Field(..., decimal_places=2)
    allocated_purchases: Decimal = Field(..., decimal_places=2)
    posted_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Billing Generation ───────────────────────────────

class BillingGenerateRequest(BaseModel):
    """Admin request to trigger statement generation for a billing cycle."""
    cycle_date: date = Field(..., description="The cycle-end date to generate statements for")
    purchase_apr: Decimal = Field(default=Decimal("0.3599"), ge=0, description="Annual purchase APR")
    cash_advance_apr: Decimal = Field(default=Decimal("0.4199"), ge=0, description="Annual cash advance APR")
    late_fee: Decimal = Field(default=Decimal("500.00"), ge=0, description="Fixed late fee amount")


# ─── Fraud Flag ────────────────────────────────────────

class FraudFlagSummary(BaseModel):
    """Summary view of a fraud flag attached to a transaction."""
    id: UUID
    transaction_id: UUID
    card_id: UUID
    rule: str
    action: str
    details: dict | None = None
    flagged_at: datetime

    model_config = ConfigDict(from_attributes=True)

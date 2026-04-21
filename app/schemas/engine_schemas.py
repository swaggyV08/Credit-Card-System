from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Annotated
from decimal import Decimal
from datetime import datetime, date
from uuid import UUID
from app.models.transactions.enums import PaymentType

StrictDecimal = Annotated[
    Decimal,
    Field(max_digits=12, decimal_places=2, json_schema_extra={"example": "0000000000.00"})
]

class StrictBase(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, populate_by_name=True)

# ── 1. TRANSACTION AUTHORIZATION ──
class AuthorizeTransactionReq(StrictBase):
    amount: StrictDecimal = Field(..., max_digits=12, decimal_places=2, gt=0, json_schema_extra={"example": "0000000000.00"})
    merchant: str = Field(..., max_length=120)
    category: str
    merchant_country: str = Field(..., min_length=2, max_length=2)
    description: Optional[str] = None

    @field_validator('category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        allowed = {"PURCHASE", "BALANCE_TRANSFER", "CASH_WITHDRAWAL"}
        if v not in allowed:
            raise ValueError(f"category must be one of {allowed}")
        return v
    
    @field_validator('merchant_country')
    @classmethod
    def validate_country(cls, v: str) -> str:
        if len(v) != 2 or not v.isalpha() or not v.isupper():
            raise ValueError("merchant_country must be ISO 3166-1 alpha-2 uppercase")
        return v

class AuthorizeTransactionResp(StrictBase):
    transaction_id: UUID
    account_id: UUID
    status: str
    amount: StrictDecimal
    foreign_fee: StrictDecimal
    hold_amount: StrictDecimal
    merchant: str
    category: str
    merchant_country: str
    is_foreign: bool
    authorization_code: str
    available_credit_before: StrictDecimal
    available_credit_after: StrictDecimal
    idempotency_key: str
    timestamp: datetime

# ── 2. TRANSACTION QUERY ──
class TransactionItem(StrictBase):
    transaction_id: UUID
    account_id: UUID
    card_id: UUID
    amount: StrictDecimal
    foreign_fee: StrictDecimal
    hold_amount: StrictDecimal
    merchant: str
    category: str
    merchant_country: str
    is_foreign: bool
    status: str
    authorization_code: str
    description: Optional[str] = None
    timestamp: datetime

class PaginatedTransactionResp(StrictBase):
    page: int
    limit: int
    total: int
    pages: int
    sort_by: str
    order: str
    items: List[TransactionItem]

# ── 3. CLEARING ──
class ClearingError(StrictBase):
    transaction_id: UUID
    reason: str

class ProcessClearingResp(StrictBase):
    job_name: str
    run_at: datetime
    cycle_date: str
    transactions_cleared: int
    total_amount_cleared: StrictDecimal
    accounts_affected: int
    errors: List[ClearingError]

# ── 4. BILLING ──
class GenerateBillReq(StrictBase):
    account_id: Optional[UUID] = None
    cycle_end: Optional[date] = None

class GenerateBillResp(StrictBase):
    bill_id: UUID
    account_id: UUID
    status: str
    billing_cycle_start: datetime
    billing_cycle_end: datetime
    previous_balance: StrictDecimal
    new_charges: StrictDecimal
    foreign_fees_total: StrictDecimal
    interest: StrictDecimal
    other_fees: StrictDecimal
    credits: StrictDecimal
    total_due: StrictDecimal
    min_payment_due: StrictDecimal
    due_date: datetime
    generated_at: datetime
    transactions_count: int

# ── 5. PAYMENT ──
class ProcessPaymentReq(StrictBase):
    amount: StrictDecimal = Field(..., max_digits=12, decimal_places=2, gt=0, json_schema_extra={"example": "0000000000.00"})
    payment_type: PaymentType = Field(PaymentType.PARTIAL, description="Enum: FULL, PARTIAL, MINIMUM. Defaults to PARTIAL.")

    @field_validator('payment_type')
    @classmethod
    def validate_payment_type(cls, v: str) -> str:
        # Pydantic Enum validation handles the membership, but we keep this for consistency if needed or casting
        return v

class ProcessPaymentResp(StrictBase):
    payment_id: UUID
    card_id: UUID
    bill_id: UUID
    amount_paid: StrictDecimal
    previous_balance: StrictDecimal
    new_balance: StrictDecimal
    available_credit_before: StrictDecimal
    available_credit_after: StrictDecimal
    bill_status: str
    remaining_due: StrictDecimal
    is_full_payment: bool
    timestamp: datetime

# ── 6. STATEMENTS ──
class StatementTransaction(StrictBase):
    transaction_id: UUID
    date: date
    merchant: str
    category: str
    amount: StrictDecimal
    foreign_fee: StrictDecimal
    total_charged: StrictDecimal
    is_foreign: bool
    status: str

class GenerateStatementResp(StrictBase):
    statement_id: UUID
    card_id: UUID
    account_id: UUID
    billing_cycle: str
    bill_id: UUID
    total_charges: StrictDecimal
    total_foreign_fees: StrictDecimal
    interest_charged: StrictDecimal
    total_due: StrictDecimal
    min_payment_due: StrictDecimal
    due_date: datetime
    generated_at: datetime
    transactions: List[StatementTransaction]

class StatementListItem(StrictBase):
    statement_id: UUID
    billing_cycle: str
    total_due: StrictDecimal
    min_payment_due: StrictDecimal
    due_date: datetime
    bill_status: str
    transactions_count: int
    generated_at: datetime

class PaginatedStatementResp(StrictBase):
    page: int
    limit: int
    total: int
    pages: int
    items: List[StatementListItem]

# ── 7. SETTLEMENT ──
class SettlementReq(StrictBase):
    settlement_date: Optional[date] = None

class SettlementError(StrictBase):
    transaction_id: UUID
    reason: str

class ProcessSettlementResp(StrictBase):
    settlement_id: UUID
    settlement_date: date
    transactions_settled: int
    total_settled_amount: StrictDecimal
    net_issuer_obligation: StrictDecimal
    status: str
    processed_at: datetime
    errors: List[SettlementError]

# ── 8. FEES ──
class AssessFeeReq(StrictBase):
    fee_type: str
    amount: StrictDecimal = Field(..., max_digits=12, decimal_places=2, gt=0, json_schema_extra={"example": "0000000000.00"})
    reason: Optional[str] = None

    @field_validator('fee_type')
    @classmethod
    def validate_fee_type(cls, v: str) -> str:
        allowed = {"LATE_FEE", "ANNUAL_FEE", "OVERLIMIT_FEE", "RETURNED_PAYMENT_FEE"}
        if v not in allowed:
            raise ValueError(f"fee_type must be one of {allowed}")
        return v

class AssessFeeResp(StrictBase):
    fee_id: UUID
    card_id: UUID
    account_id: UUID
    fee_type: str
    amount: StrictDecimal
    reason: Optional[str] = None
    status: str
    applied_to_bill: Optional[UUID] = None
    assessed_at: datetime
    assessed_by: str

# ── 9. BILLS LIST AND DETAIL ──
class BillListItem(StrictBase):
    bill_id: UUID
    account_id: UUID
    status: str
    billing_cycle_start: datetime
    billing_cycle_end: datetime
    total_due: StrictDecimal
    min_payment_due: StrictDecimal
    due_date: datetime
    generated_at: datetime

class PaginatedBillResp(StrictBase):
    page: int
    limit: int
    total: int
    pages: int
    items: List[BillListItem]

class BillPaymentItem(StrictBase):
    payment_id: UUID
    amount: StrictDecimal
    paid_at: datetime

class BillDetailTransactionItem(StrictBase):
    transaction_id: UUID
    date: date
    merchant: str
    amount: StrictDecimal
    foreign_fee: StrictDecimal
    total_charged: StrictDecimal
    category: str
    status: str

class BillDetailResp(StrictBase):
    bill_id: UUID
    account_id: UUID
    status: str
    billing_cycle_start: datetime
    billing_cycle_end: datetime
    previous_balance: StrictDecimal
    new_charges: StrictDecimal
    foreign_fees_total: StrictDecimal
    interest: StrictDecimal
    other_fees: StrictDecimal
    credits: StrictDecimal
    total_due: StrictDecimal
    min_payment_due: StrictDecimal
    due_date: datetime
    generated_at: datetime
    transactions: List[BillDetailTransactionItem]
    payments: List[BillPaymentItem]

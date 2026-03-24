from typing import List, Optional
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from decimal import Decimal

class BillingStatementResponse(BaseModel):
    id: UUID
    credit_account_id: UUID
    statement_period_start: datetime
    statement_period_end: datetime
    statement_date: datetime
    due_date: datetime
    opening_balance: Decimal
    total_purchases: Decimal
    total_cash_advances: Decimal
    total_payments: Decimal
    interest_charged: Decimal
    fees_charged: Decimal
    closing_balance: Decimal
    minimum_amount_due: Decimal
    is_fully_paid: bool

    class Config:
        from_attributes = True

class RewardSummaryResponse(BaseModel):
    credit_account_id: UUID
    total_points_earned: Decimal
    total_points_redeemed: Decimal
    total_points_reversed: Decimal
    net_points: Decimal

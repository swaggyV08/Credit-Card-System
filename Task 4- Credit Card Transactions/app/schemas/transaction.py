from typing import Optional, List
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.enums import CCMTransactionType, CCMTransactionStatus

class TransactionCreateRequest(BaseModel):
    card_id: UUID
    amount: Decimal = Field(..., gt=0)
    merchant_name: str
    transaction_type: CCMTransactionType = CCMTransactionType.PURCHASE
    idempotency_key: Optional[str] = None

class TransactionResponse(BaseModel):
    id: UUID
    card_id: UUID
    credit_account_id: UUID
    amount: Decimal
    currency: str
    merchant_name: str
    transaction_type: CCMTransactionType
    status: CCMTransactionStatus
    idempotency_key: Optional[str]
    settlement_date: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class TransactionHistoryFilter(BaseModel):
    card_id: Optional[UUID] = None
    status: Optional[CCMTransactionStatus] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = 20
    offset: int = 0

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.api.deps import get_async_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.engine_schemas import (
    AuthorizeTransactionReq,
    AuthorizeTransactionResp,
    PaginatedTransactionResp
)
from app.services.transaction_engine import TransactionEngine
from app.models.transactions.enums import TransactionType, TransactionStatus
from datetime import datetime, date

router = APIRouter(tags=["Transactions"])

@router.post(
    "/credit-cards/{card_id}/transactions",
    response_model=AuthorizeTransactionResp,
    status_code=201,
    summary="Authorize Transaction",
    description="""
FUNCTIONALITY:
Real-time authorization and hold placement for a credit card transaction. It implements a pessimistic lock (SELECT FOR UPDATE) on the Account and Card records using SERIALIZABLE isolation to prevent race conditions. The response confirms the allocation of funds against the user's available credit.

ROLES THAT CAN ACCESS THE ENDPOINT:
- USER (own card only)

MATH FORMULA:
foreign_fee = amount × 0.03 (if the merchant_country differs from the account home_country)
hold_amount = amount + foreign_fee
available_credit_after = available_credit_before - hold_amount

LOGIC AND NECESSITY OF THE ENDPOINT:
Required to instantly authorize purchases and lock credit securely. Includes in-memory velocity boundary checks (max 5 transactions or 10000 limit) and strict fraud rules to automatically block irregular behaviors. Returns perfectly standardized mapped error codes on failures.

Enums for 'category':
- PURCHASE
- BALANCE_TRANSFER
- CASH_WITHDRAWAL
"""
)
async def authorize_transaction(
    card_id: str,
    request: AuthorizeTransactionReq,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_async_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:initiate"))
):
    # Enforces the lock, logic, and idempotency as exactly specified
    result = await TransactionEngine.authorize(
        db=db,
        credit_card_id=card_id,
        user_id=principal.user_id,
        idempotency_key=idempotency_key,
        payload=request
    )
    return result


@router.get(
    "/credit-cards/{card_id}/transactions/{transaction_id}",
    response_model=PaginatedTransactionResp,
    status_code=200,
    summary="Query Transactions",
    description="""
FUNCTIONALITY:
Paginated, multi-filter, sortable endpoint to fetch historical settled or authorized transactions. It applies AND logic across all query parameters.

ROLES THAT CAN ACCESS THE ENDPOINT:
- USER (own card only)

MATH FORMULA:
Total Pages = ceil(total / limit)
Offset = (page - 1) * limit

LOGIC AND NECESSITY OF THE ENDPOINT:
Provides full transparency for users surveying their transactions securely. Prevents returning large payloads dynamically via limit boundaries and ensures strict RBAC mapping validating the card_id header bounds.
"""
)
async def list_or_get_transactions(
    card_id: str,
    transaction_id: Optional[UUID] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("timestamp"),
    order: str = Query("desc"),
    date_from: Optional[str] = Query(None, openapi_examples={"default": {"value": "YYYY-MM-DD"}}, description="Formatted date watermark: YYYY-MM-DD. Must be within current month."),
    date_to: Optional[str] = Query(None, openapi_examples={"default": {"value": "YYYY-MM-DD"}}, description="Formatted date watermark: YYYY-MM-DD. Max value is today."),
    amount_min: Optional[str] = Query(None),
    amount_max: Optional[str] = Query(None),
    merchant: Optional[str] = Query(None),
    category: Optional[TransactionType] = Query(None, description="Select from category dropdown"),
    status: Optional[TransactionStatus] = Query(None, description="Select from status dropdown"),
    db: AsyncSession = Depends(get_async_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:read"))
):
    # --- DATE VALIDATION ---
    now = datetime.now()
    today = now.date()
    first_of_month = today.replace(day=1)

    if date_from:
        try:
            df = datetime.strptime(date_from, "%Y-%m-%d").date()
            if df < first_of_month:
                raise AppError(code="INVALID_DATE_RANGE", message="date_from must be within the current month.", http_status=400)
        except ValueError:
             raise AppError(code="INVALID_FORMAT", message="date_from must be in YYYY-MM-DD format.", http_status=400)

    if date_to:
        try:
            dt = datetime.strptime(date_to, "%Y-%m-%d").date()
            if dt > today:
                raise AppError(code="INVALID_DATE_RANGE", message="date_to cannot be in the future.", http_status=400)
        except ValueError:
             raise AppError(code="INVALID_FORMAT", message="date_to must be in YYYY-MM-DD format.", http_status=400)

    query_params = {
        "page": page,
        "limit": limit,
        "sort_by": sort_by,
        "order": order,
        "date_from": date_from,
        "date_to": date_to,
        "amount_min": amount_min,
        "amount_max": amount_max,
        "merchant": merchant,
        "category": category,
        "status": status,
        "transaction_id": transaction_id
    }
    
    result = await TransactionEngine.query_transactions(
        db=db,
        credit_card_id=card_id,
        user_id=principal.user_id,
        params=query_params
    )
    return result

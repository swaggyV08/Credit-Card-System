"""
Payments Router — Week 5 Enhanced

Endpoints:
  POST  /cards/{card_id}/payments     — Make payment with RBI waterfall
  GET   /cards/{card_id}/payments     — List payments with status filter
  PATCH /payments/{payment_id}        — Confirm / reverse a payment
"""
import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success
from app.schemas.responses import PaymentCreateResponse as PaymentCreateEnvelope, PaymentListResponse

from app.models.billing import Payment
from app.models.transactions.enums import PaymentStatus
from app.schemas.billing import PaymentCreateRequest, PaymentResponse
from app.schemas.transactions.operations import PaymentSchema, PaymentCommandRequest
from app.services.payment_service import PaymentWaterfallService
from app.services.transactions.operations_service import PaymentService as LegacyPaymentService
from app.models.card_management import CCMCreditAccount, CCMCreditCard
from app.core.exceptions import PaymentExceedsBalanceError

router = APIRouter(tags=["Payments"])


@router.post("/cards/{card_id}/payments", status_code=201, response_model=PaymentCreateEnvelope)
def create_payment(
    card_id: uuid.UUID,
    request: PaymentCreateRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("payment:make")),
):
    """
    Cardholder payment with RBI-mandated waterfall allocation.

    **What it does:**
    Processes a payment against the card's outstanding balance using the
    RBI-mandated payment waterfall order:
    1. Fees & Charges  2. Interest  3. Cash Advance Principal  4. Purchase Principal

    Validates that the payment amount does not exceed the outstanding balance.

    **Request Body (`PaymentCreateRequest`):**
    - `amount`: Decimal > 0 (payment amount in INR)
    - `payment_source` enum: `BANK_ACCOUNT` | `BANK_TRANSFER` | `NEFT` | `RTGS` | `UPI` | `CHEQUE`
    - `reference_no`: External payment reference (3-64 chars)
    - `payment_date`: Optional date override

    **Payment Status enum:** `PENDING` | `POSTED` | `REVERSED` | `FAILED`

    **Roles:** `payment:make` (User / Admin)

    **Response:** `PaymentResponse` with `{ payment_id, amount, status, allocated_fees, allocated_interest, allocated_cash_advance, allocated_purchases }`
    """
    # Validation: Payment exceeds balance check
    account = db.query(CCMCreditAccount).join(CCMCreditCard, CCMCreditCard.credit_account_id == CCMCreditAccount.id).filter(CCMCreditCard.id == card_id).first()
    if account and request.amount > account.outstanding_amount:
        raise PaymentExceedsBalanceError(outstanding=account.outstanding_amount, payment=request.amount)

    payment = PaymentWaterfallService.process_payment(
        db=db,
        card_id=card_id,
        amount=request.amount,
        payment_source=request.payment_source,
        reference_no=request.reference_no,
        payment_date=request.payment_date,
        created_by=principal.user_id if hasattr(principal, "user_id") else None,
    )
    data = PaymentResponse.model_validate(payment).model_dump(mode="json")
    return envelope_success(data)


@router.get("/cards/{card_id}/payments", response_model=PaymentListResponse)
def list_payments(
    card_id: uuid.UUID,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("payment:read")),
):
    """
    Lists all payments on the card account with status and date filters.

    **What it does:**
    Returns a paginated history of all payments made against this card,
    ordered by most recent first. Supports filtering by payment status.

    **Query Parameters:**
    - `status`: Filter by `PENDING` | `POSTED` | `REVERSED` | `FAILED`
    - `page` / `page_size`: Pagination controls

    **Roles:** `payment:read` (User / Admin)

    **Response:** `{ data: [PaymentResponse], meta: { total, page, page_size } }`
    """
    query = db.query(Payment).filter(Payment.card_id == card_id)
    if status:
        query = query.filter(Payment.status == status)
    total = query.count()
    results = query.order_by(Payment.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    data = [PaymentResponse.model_validate(p).model_dump(mode="json") for p in results]

    return envelope_success({
        "data": data,
        "meta": {"total": total, "page": page, "page_size": page_size},
    })


# DELETE: PATCH /payments/{payment_id} removed as per directive.

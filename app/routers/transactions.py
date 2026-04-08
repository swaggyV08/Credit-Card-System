"""
Transactions Router — Week 5 Enhanced

Wires fraud checks and idempotency service into the transaction creation flow.

Endpoints:
  POST  /cards/{card_id}/transactions     — Create transaction (with fraud + idempotency)
  GET   /cards/{card_id}/transactions     — List transactions (paginated)
  GET   /transactions/{txn_id}            — Get transaction detail
  PATCH /transactions/{txn_id}            — State transitions (reverse, void, flag, unflag, capture)
"""
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from decimal import Decimal

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success
from app.schemas.responses import TransactionCreateResponse, TransactionListResponse

from app.models.transactions.transactions import Transaction
from app.schemas.transactions.transactions import (
    CreateTransactionRequest, TransactionSummarySchema, TransactionDetailSchema,
    TransactionCommandRequest
)
from app.services.transactions.transaction_service import TransactionService, HoldService
from app.services.idempotency_service import IdempotencyService
from app.core.exceptions import (
    MissingIdempotencyKeyError, InvalidIdempotencyKeyError,
)

router = APIRouter(tags=["Transactions"])


@router.post("/cards/{card_id}/transactions", status_code=201, response_model=TransactionCreateResponse)
def create_transaction(
    card_id: UUID,
    request: CreateTransactionRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:initiate")),
):
    """
    Initiates a transaction via authorization pipeline.

    **What it does:**
    Simulates a card swipe or online purchase. Runs the full authorization pipeline:
    idempotency dedup → card validation → velocity check → fraud scoring → authorization.
    Creates a credit hold against the card's available credit.

    **Headers:**
    - `Idempotency-Key` (required): UUID to prevent duplicate charges.

    **Request Body (`CreateTransactionRequest`):**
    - `transaction_type` enum: `PURCHASE` | `CASH_ADVANCE` | `BALANCE_TRANSFER` | `QUASI_CASH` | `REFUND` | `PRE_AUTH` | `FEE` | `INTEREST_CHARGE` | `PAYMENT` | `FEE_WAIVER`
    - `pos_entry_mode` enum (optional): `CHIP` | `SWIPE` | `NFC` | `MANUAL`
    - `amount`: Decimal > 0 (2 decimal places)
    - `merchant_category_code`: 4-digit MCC string
    - `merchant_country`: ISO 3166-1 alpha-2 code
    - `card_not_present`: Boolean (if true, `cvv2` is required)

    **Roles:** `transaction:initiate` (User / Admin)

    **Response:** `{ transaction_id, auth_code, status, amount, available_credit, hold_id, hold_expiry }`
    """
    # ── Step 0: Idempotency check ──
    if not idempotency_key:
        raise MissingIdempotencyKeyError()
    
    cached = IdempotencyService.check_idempotency(db, idempotency_key, str(card_id))
    if cached:
        # Return cached response with replay header
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content=cached["response_body"],
            status_code=cached["status_code"],
            headers={"X-Idempotency-Replay": "true"}
        )

    # ── Step 1: Legacy duplicate check ──
    duplicate = TransactionService.check_duplicate(
        db, card_id, request.merchant_id, request.amount, idempotency_key,
    )
    if duplicate:
        response = envelope_success({
            "transaction_id": str(duplicate.id),
            "auth_code": duplicate.auth_code,
            "status": duplicate.status,
            "message": "Duplicate transaction detected. Returning cached response.",
        })
        return response

    # ── Step 2: Card validation ──
    card = TransactionService.validate_card(db, card_id, user_id=principal.user_id)

    # ── Step 3: Velocity check (Now handles Redis counters) ──
    TransactionService.check_velocity(db, card_id, request.amount)

    # ── Step 5: Authorization ──
    result = TransactionService.authorize_transaction(
        db, card, request, idempotency_key, actor_id=principal.user_id,
    )

    # Must dump complex models for envelope
    result_dict = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    response = envelope_success(result_dict)

    # ── Step 6: Store idempotency result ──
    if idempotency_key:
        IdempotencyService.store_idempotency_result(
            db=db,
            key=idempotency_key,
            card_id=card_id,
            response_body=response,
            status_code=201,
        )
        db.commit()

    return response


@router.get("/cards/{card_id}/transactions", response_model=TransactionListResponse)
def list_transactions(
    card_id: UUID,
    status: str | None = None,
    transaction_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    merchant_name: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = "created_at",
    sort_order: str = "desc",
    include: str | None = Query(None, description="include=holds to see active holds"),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:read")),
):
    """
    Lists transactions for a card with filters and pagination.

    **What it does:**
    Returns a paginated, filterable list of all transactions on the card.
    Optionally includes active credit holds via `?include=holds`.

    **Query Parameters:**
    - `status`: Filter by transaction status (e.g., `AUTHORIZED`, `SETTLED`, `REVERSED`)
    - `transaction_type`: Filter by type (e.g., `PURCHASE`, `CASH_ADVANCE`)
    - `date_from` / `date_to`: Date range filter
    - `merchant_name`: Partial match filter
    - `include=holds`: Includes active `CreditHold` objects and aggregated hold totals
    - `sort_by` / `sort_order`: Sorting controls

    **Transaction Status enum:** `PENDING_AUTHORIZATION` | `AUTHORIZED` | `CLEARED` | `SETTLED` | `REVERSED` | `VOIDED` | `DECLINED` | `DISPUTED` | `CHARGED_BACK` | `FORCE_POST` | `BLOCKED`

    **Roles:** `transaction:read` (User / Admin)

    **Response:** `{ data: [TransactionSummary], total_hold_amount, available_credit, meta: { total, page, page_size } }`
    """
    query = db.query(Transaction).filter(
        Transaction.card_id == card_id, Transaction.is_deleted == False,
    )

    if status:
        query = query.filter(Transaction.status == status)
    if transaction_type:
        query = query.filter(Transaction.transaction_type == transaction_type)
    if date_from:
        query = query.filter(Transaction.created_at >= date_from)
    if date_to:
        query = query.filter(Transaction.created_at <= date_to)
    if merchant_name:
        query = query.filter(Transaction.merchant_name.ilike(f"%{merchant_name}%"))

    total = query.count()
    sort_col = getattr(Transaction, sort_by, Transaction.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    results = query.offset((page - 1) * page_size).limit(page_size).all()
    
    total_hold = Decimal("0")
    available_credit = Decimal("0") # Default if not requested
    
    if include == "holds":
        # Add holds logic
        from app.models.transactions.transactions import CreditHold
        from app.models.transactions.enums import HoldStatus
        for t in results:
            t.active_holds = [h for h in t.holds if h.status == HoldStatus.ACTIVE.value]
        
        # Calculate aggregates for the account
        _, total_hold, available_credit = HoldService.get_holds(db, card_id)

    data = [
        TransactionSummarySchema.model_validate(t).model_dump(mode="json")
        for t in results
    ]

    return envelope_success({
        "data": data,
        "total_hold_amount": total_hold,
        "available_credit": available_credit,
        "meta": {"total": total, "page": page, "page_size": page_size},
    })


@router.get("/transactions/{txn_id}")
def get_transaction(
    txn_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:read")),
):
    """
    Gets detailed transaction view including embedded holds and disputes.

    **What it does:**
    Returns the full transaction record with all merchant details, risk scoring,
    idempotency key, metadata, and any linked dispute summary.

    **Roles:** `transaction:read` (User / Admin)

    **Response:** `TransactionDetailSchema` with merchant details, risk tier, linked dispute, and holds.
    """
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    data = TransactionDetailSchema.model_validate(txn).model_dump(mode="json")
    return envelope_success(data)


@router.put("/transactions/{txn_id}")
def transition_transaction(
    txn_id: UUID,
    command: str = Query(..., description="reverse | void | flag | unflag | capture"),
    body: TransactionCommandRequest = None,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:state")),
):
    """
    State-transition functionality for a single transaction.

    **What it does:**
    Unified command dispatcher that moves a transaction through its lifecycle.
    Each command triggers different business logic (credit restoration, fraud flagging, etc.).

    **Query Parameter `command`:**
    - `reverse` — Reverses the transaction and restores credit. Requires `reason`.
    - `void` — Voids an authorized-but-unsettled transaction. Requires `reason`.
    - `flag` — Marks the transaction for internal fraud review. Requires `flag_reason`.
    - `unflag` — Clears a fraud flag. Requires `unflag_reason`.
    - `capture` — Captures a pre-auth transaction for the specified `amount`.
    - `release_hold` — Manually releases an active credit hold. Requires `reason`.

    **Request Body (`TransactionCommandRequest`):**
    - `amount`: Decimal (for `capture` command)
    - `reason` / `flag_reason` / `unflag_reason`: String explanations

    **Roles:** `transaction:state` (Admin / Super Admin only)

    **Response:** Updated `TransactionDetailSchema`.
    """
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    body = body or TransactionCommandRequest()

    if command == "reverse":
        reason = body.reason or "Admin reversal"
        result = TransactionService.reverse_transaction(
            db, txn, reason, actor_id=principal.user_id,
        )
    elif command == "void":
        reason = body.reason or "Voided"
        result = TransactionService.void_transaction(
            db, txn, reason, actor_id=principal.user_id,
        )
    elif command == "flag":
        if not body.flag_reason:
            raise HTTPException(
                status_code=422,
                detail="flag_reason is required for the 'flag' command",
            )
        result = TransactionService.flag_transaction(
            db, txn, body.flag_reason, actor_id=principal.user_id,
        )
    elif command == "unflag":
        if not body.unflag_reason:
            raise HTTPException(
                status_code=422,
                detail="unflag_reason is required for the 'unflag' command",
            )
        result = TransactionService.unflag_transaction(
            db, txn, body.unflag_reason, actor_id=principal.user_id,
        )
    elif command == "capture":
        result = TransactionService.capture_preauth(
            db, txn, body.amount, actor_id=principal.user_id,
        )
    elif command == "release_hold":
        if not body.reason:
            raise HTTPException(status_code=422, detail="reason is required for release_hold")
        # Find active hold for this txn
        from app.models.transactions.transactions import CreditHold
        from app.models.transactions.enums import HoldStatus
        hold = db.query(CreditHold).filter(
            CreditHold.transaction_id == txn.id,
            CreditHold.status == HoldStatus.ACTIVE.value
        ).first()
        if not hold:
            raise HTTPException(status_code=404, detail="No active hold found for this transaction")
        result_hold = HoldService.release_hold(db, hold.id, body.reason, actor_id=principal.user_id)
        return envelope_success(TransactionDetailSchema.model_validate(txn).model_dump(mode="json"))
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown command: '{command}'. Supported: reverse, void, flag, unflag, capture, release_hold",
        )

    data = TransactionDetailSchema.model_validate(result).model_dump(mode="json")
    return envelope_success(data)

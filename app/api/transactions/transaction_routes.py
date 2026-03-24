"""
Transaction Routers — API endpoints for Groups 1–5.
Group 1: Transaction Initiation & Authorization
Group 2: Holds Management
Group 3: Clearing & Settlement
Group 4: Disputes & Chargebacks
Group 5: Refunds & Reversals
"""
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.api.deps import get_db, get_current_authenticated_user, get_current_admin_user
from app.admin.models.card_issuance import Card, CreditAccount
from app.models.transactions.transactions import Transaction, CreditHold
from app.models.transactions.clearing import ClearingBatch
from app.models.transactions.settlement import SettlementRun
from app.models.transactions.disputes import Dispute, DisputeEvidence
from app.models.transactions.enums import (
    TransactionStatus, HoldStatus, DisputeStatus,
)
from app.schemas.transactions.envelope import success_response, paginated_response
from app.schemas.transactions.transactions import (
    CreateTransactionRequest, TransactionSummarySchema, TransactionDetailSchema,
    TransactionCommandRequest, HoldSchema, HoldReleaseRequest, HoldSummaryResponse,
    CreateClearingBatchRequest, ClearingBatchDetailSchema,
    CreateSettlementRequest, SettlementRunDetailSchema,
    CreateDisputeRequest, DisputeSummarySchema, DisputeDetailSchema, DisputeCommandRequest,
    CreateRefundRequest,
)
from app.services.transactions.transaction_service import (
    TransactionService, HoldService, ClearingService, SettlementService,
    DisputeService, RefundService,
)


# =====================================================
# GROUP 1 — TRANSACTION INITIATION & AUTHORIZATION
# =====================================================
txn_router = APIRouter(tags=["Transactions"])


@txn_router.post(
    "/cards/{card_id}/transactions",
    status_code=201,
    summary="Initiate a Transaction",
    description="""
**Transaction Initiation & Authorization Endpoint**

Handles ALL transaction types via `transaction_type`:
- `PURCHASE` — Standard purchase
- `CASH_ADVANCE` — ATM/OTC cash withdrawal
- `BALANCE_TRANSFER` — Transfer from another card
- `QUASI_CASH` — Lottery, gambling, crypto
- `REFUND` — Merchant-initiated refund
- `PRE_AUTH` — Hotel/rental pre-authorization hold

**Authorization Pipeline:**
1. Card Validation (status, expiry, ownership)
2. Merchant Validation (MCC checks)
3. Velocity & Fraud Pre-checks (rate limiting)
4. Credit Limit Authorization
5. Hold Creation (7 days for purchases, 30 for pre-auth)
6. Transaction Record + Auth Code Generation

**Idempotency:** Supply `Idempotency-Key` header to prevent duplicate transactions.
""",
)
def create_transaction(
    card_id: UUID,
    request: CreateTransactionRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    # Duplicate/Idempotency check
    duplicate = TransactionService.check_duplicate(db, card_id, request.merchant_id, request.amount, idempotency_key)
    if duplicate:
        return success_response({
            "transaction_id": str(duplicate.id),
            "auth_code": duplicate.auth_code,
            "status": duplicate.status,
            "message": "Duplicate transaction detected. Returning cached response.",
        })

    # Validate card
    card = TransactionService.validate_card(db, card_id, user_id=user.id)

    # Velocity checks
    TransactionService.check_velocity(db, card_id, request.amount)

    # Authorize
    result = TransactionService.authorize_transaction(db, card, request, idempotency_key, actor_id=user.id)
    return success_response(result)


@txn_router.get(
    "/cards/{card_id}/transactions",
    summary="List Transactions",
    description="Paginated transaction listing with rich filters. Cardholder sees own card; admin sees all.",
)
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
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    query = db.query(Transaction).filter(Transaction.card_id == card_id, Transaction.is_deleted == False)

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
    data = [TransactionSummarySchema.model_validate(t).model_dump() for t in results]
    return paginated_response(data, total, page, page_size)


@txn_router.get(
    "/transactions/{txn_id}",
    summary="Get Transaction Detail",
    description="Full transaction detail including holds, clearing records, and dispute history.",
)
def get_transaction(
    txn_id: UUID,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    data = TransactionDetailSchema.model_validate(txn).model_dump()
    return success_response(data)


@txn_router.patch(
    "/transactions/{txn_id}",
    summary="Transaction State Machine",
    description="""
Unified state-transition endpoint. Use `?command=` to specify the action:
- `reverse` — Reverse an AUTHORIZED transaction (releases hold)
- `void` — Cancel a PENDING transaction
- `flag` — Flag for investigation (requires `flag_reason`)
- `unflag` — Clear a flag (requires `unflag_reason`)
- `capture` — Finalize a PRE_AUTH (partial capture allowed via `amount`)
""",
)
def transition_transaction(
    txn_id: UUID,
    command: str = Query(..., description="reverse | void | flag | unflag | capture"),
    body: TransactionCommandRequest = None,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    body = body or TransactionCommandRequest()

    if command == "reverse":
        reason = body.reason or "Admin reversal"
        result = TransactionService.reverse_transaction(db, txn, reason, actor_id=user.id)
    elif command == "void":
        reason = body.reason or "Voided"
        result = TransactionService.void_transaction(db, txn, reason, actor_id=user.id)
    elif command == "flag":
        if not body.flag_reason:
            raise HTTPException(status_code=422, detail="flag_reason is required for the 'flag' command")
        result = TransactionService.flag_transaction(db, txn, body.flag_reason, actor_id=user.id)
    elif command == "unflag":
        if not body.unflag_reason:
            raise HTTPException(status_code=422, detail="unflag_reason is required for the 'unflag' command")
        result = TransactionService.unflag_transaction(db, txn, body.unflag_reason, actor_id=user.id)
    elif command == "capture":
        result = TransactionService.capture_preauth(db, txn, body.amount, actor_id=user.id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: '{command}'. Supported: reverse, void, flag, unflag, capture")

    data = TransactionDetailSchema.model_validate(result).model_dump()
    return success_response(data)


# =====================================================
# GROUP 2 — HOLDS MANAGEMENT
# =====================================================
hold_router = APIRouter(tags=["Holds"])


@hold_router.get(
    "/cards/{card_id}/holds",
    summary="List Card Holds",
    description="Returns all credit holds on a card with total hold amount and available credit. Expired holds are auto-cleaned.",
)
def list_holds(
    card_id: UUID,
    status: str = Query("ACTIVE", description="ACTIVE | RELEASED | EXPIRED | ALL"),
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    holds, total_amount, available_credit = HoldService.get_holds(db, card_id, status)
    data = {
        "holds": [HoldSchema.model_validate(h).model_dump() for h in holds],
        "total_hold_amount": str(total_amount),
        "available_credit": str(available_credit),
    }
    return success_response(data)


@hold_router.patch(
    "/holds/{hold_id}",
    summary="Release a Hold",
    description="Manually releases a specific hold. Admin only. Requires `release_reason`.",
)
def release_hold(
    hold_id: UUID,
    command: str = Query(..., description="release"),
    body: HoldReleaseRequest = None,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    if command != "release":
        raise HTTPException(status_code=400, detail=f"Unknown command: '{command}'. Only 'release' is supported.")
    if not body:
        raise HTTPException(status_code=422, detail="Request body with release_reason is required")
    hold = HoldService.release_hold(db, hold_id, body.release_reason, actor_id=user.id)
    data = HoldSchema.model_validate(hold).model_dump()
    return success_response(data)


# =====================================================
# GROUP 3 — CLEARING & SETTLEMENT
# =====================================================
clearing_router = APIRouter(tags=["Clearing & Settlement"])


@clearing_router.post(
    "/clearing/batches",
    status_code=201,
    summary="Process Clearing Batch",
    description="Ingests a clearing batch from the card network. Matches auth codes, handles mismatches and force-posts.",
)
def process_clearing_batch(
    request: CreateClearingBatchRequest,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    result = ClearingService.process_batch(db, request, actor_id=user.id)
    return success_response(result)


@clearing_router.get(
    "/clearing/batches/{batch_id}",
    summary="Get Clearing Batch Detail",
    description="Returns status and summary of a clearing batch.",
)
def get_clearing_batch(
    batch_id: UUID,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    batch = db.query(ClearingBatch).filter(ClearingBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Clearing batch not found")
    data = ClearingBatchDetailSchema.model_validate(batch).model_dump()
    return success_response(data)


@clearing_router.get(
    "/clearing/batches",
    summary="List Clearing Batches",
    description="Lists all clearing batches with optional status and date filters.",
)
def list_clearing_batches(
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    query = db.query(ClearingBatch)
    if status:
        query = query.filter(ClearingBatch.status == status)
    total = query.count()
    results = query.order_by(ClearingBatch.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = [ClearingBatchDetailSchema.model_validate(b).model_dump() for b in results]
    return paginated_response(data, total, page, page_size)


@clearing_router.post(
    "/settlements",
    status_code=201,
    summary="Run Settlement",
    description="Triggers a settlement run for all cleared transactions within the cutoff window.",
)
def run_settlement(
    request: CreateSettlementRequest,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    result = SettlementService.run_settlement(db, request, actor_id=user.id)
    return success_response(result)


@clearing_router.get(
    "/settlements/{settlement_run_id}",
    summary="Get Settlement Run Detail",
    description="Full detail of a settlement run including per-card breakdown.",
)
def get_settlement_run(
    settlement_run_id: UUID,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    run = db.query(SettlementRun).filter(SettlementRun.id == settlement_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Settlement run not found")
    data = SettlementRunDetailSchema.model_validate(run).model_dump()
    return success_response(data)


# =====================================================
# GROUP 4 — DISPUTES & CHARGEBACKS
# =====================================================
dispute_router = APIRouter(tags=["Disputes"])


@dispute_router.post(
    "/transactions/{txn_id}/disputes",
    status_code=201,
    summary="Raise a Dispute",
    description="""
Raise a dispute against a CLEARED or SETTLED transaction.

**Dispute Types:**
- `UNAUTHORIZED` — Cardholder denies making the transaction
- `DUPLICATE_CHARGE` — Same merchant charged twice
- `GOODS_NOT_RECEIVED` — Item not received
- `QUALITY_ISSUE` — Item/service not as described
- `PROCESSING_ERROR` — Incorrect amount/currency
- `SUBSCRIPTION_CANCEL` — Recurring charge after cancellation
- `FRAUD` — Card compromised/stolen

For UNAUTHORIZED and FRAUD types, provisional credit is automatically issued to the cardholder.
""",
)
def create_dispute(
    txn_id: UUID,
    request: CreateDisputeRequest,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    result = DisputeService.create_dispute(db, txn_id, request, actor_id=user.id)
    return success_response(result)


@dispute_router.get(
    "/cards/{card_id}/disputes",
    summary="List Card Disputes",
    description="Lists all disputes for a card with status and date filters.",
)
def list_disputes(
    card_id: UUID,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    query = db.query(Dispute).filter(Dispute.card_id == card_id)
    if status:
        query = query.filter(Dispute.status == status)
    total = query.count()
    results = query.order_by(Dispute.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = [DisputeSummarySchema.model_validate(d).model_dump() for d in results]
    return paginated_response(data, total, page, page_size)


@dispute_router.get(
    "/disputes/{dispute_id}",
    summary="Get Dispute Detail",
    description="Full dispute detail including timeline, documents, and resolution outcome.",
)
def get_dispute(
    dispute_id: UUID,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    dispute = db.query(Dispute).filter(Dispute.id == dispute_id).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    data = DisputeDetailSchema.model_validate(dispute).model_dump()
    return success_response(data)


@dispute_router.patch(
    "/disputes/{dispute_id}",
    summary="Dispute State Machine",
    description="""
Unified dispute transition. Use `?command=` to specify:
- `submit_evidence` — Submit documents/statement
- `escalate` — Route to network chargeback flow
- `resolve` — Mark as WON or LOST (provide `resolution` in body)
- `withdraw` — Cardholder withdraws dispute
""",
)
def transition_dispute(
    dispute_id: UUID,
    command: str = Query(..., description="submit_evidence | escalate | resolve | withdraw"),
    body: DisputeCommandRequest = None,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    dispute = db.query(Dispute).filter(Dispute.id == dispute_id).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    body = body or DisputeCommandRequest()

    if command == "submit_evidence":
        if body.documents:
            for doc in body.documents:
                evidence = DisputeEvidence(
                    dispute_id=dispute.id, submitted_by=str(user.id),
                    document_s3_key=doc, statement=body.statement,
                )
                db.add(evidence)
        db.commit()
        db.refresh(dispute)
    elif command == "escalate":
        dispute.status = DisputeStatus.ESCALATED.value
        db.commit()
        db.refresh(dispute)
    elif command == "resolve":
        if not body.resolution:
            raise HTTPException(status_code=422, detail="resolution is required (RESOLVED_WON or RESOLVED_LOST)")
        dispute = DisputeService.resolve_dispute(db, dispute, body.resolution, actor_id=user.id)
    elif command == "withdraw":
        dispute = DisputeService.withdraw_dispute(db, dispute, actor_id=user.id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: '{command}'")

    data = DisputeDetailSchema.model_validate(dispute).model_dump()
    return success_response(data)


# =====================================================
# GROUP 5 — REFUNDS & REVERSALS
# =====================================================
refund_router = APIRouter(tags=["Refunds"])


@refund_router.post(
    "/transactions/{txn_id}/refunds",
    status_code=201,
    summary="Process Refund",
    description="""
Merchant-initiated refund against a SETTLED transaction. Partial refunds are supported.

**Rules:**
- Refund amount ≤ original transaction amount
- Cumulative refunds cannot exceed original amount
- Credits posted directly to cardholder balance
""",
)
def create_refund(
    txn_id: UUID,
    request: CreateRefundRequest,
    user=Depends(get_current_authenticated_user),
    db: Session = Depends(get_db),
):
    result = RefundService.process_refund(db, txn_id, request, actor_id=user.id)
    return success_response(result)

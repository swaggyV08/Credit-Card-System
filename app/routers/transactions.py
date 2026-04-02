from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.models.transactions.transactions import Transaction
from app.schemas.transactions.transactions import (
    CreateTransactionRequest, TransactionSummarySchema, TransactionDetailSchema,
    TransactionCommandRequest
)
from app.services.transactions.transaction_service import TransactionService

router = APIRouter(tags=["Transactions"])

@router.post("/cards/{card_id}/transactions", status_code=201)
def create_transaction(
    card_id: UUID,
    request: CreateTransactionRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:initiate"))
):
    """Initiates a transaction via authorization pipeline."""
    duplicate = TransactionService.check_duplicate(db, card_id, request.merchant_id, request.amount, idempotency_key)
    if duplicate:
        return envelope_success({
            "transaction_id": str(duplicate.id),
            "auth_code": duplicate.auth_code,
            "status": duplicate.status,
            "message": "Duplicate transaction detected. Returning cached response.",
        })

    card = TransactionService.validate_card(db, card_id, user_id=principal.user_id)
    TransactionService.check_velocity(db, card_id, request.amount)
    
    result = TransactionService.authorize_transaction(db, card, request, idempotency_key, actor_id=principal.user_id)
    
    # Must dump complex models for envelope
    result_dict = result.model_dump(mode='json') if hasattr(result, 'model_dump') else result
    return envelope_success(result_dict)

@router.get("/cards/{card_id}/transactions")
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
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:read"))
):
    """Lists transactions for a card with filters."""
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
    data = [TransactionSummarySchema.model_validate(t).model_dump(mode='json') for t in results]
    
    return envelope_success({
        "data": data,
        "meta": {"total": total, "page": page, "page_size": page_size} # Matching pagination logic inside envelope
    })

@router.get("/transactions/{txn_id}")
def get_transaction(
    txn_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:read"))
):
    """Gets detailed transaction view (including embedded holds and disputes)."""
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    data = TransactionDetailSchema.model_validate(txn).model_dump(mode='json')
    return envelope_success(data)

@router.patch("/transactions/{txn_id}")
def transition_transaction(
    txn_id: UUID,
    command: str = Query(..., description="reverse | void | flag | unflag | capture"),
    body: TransactionCommandRequest = None,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:state"))
):
    """State-transition functionality for single transaction."""
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    body = body or TransactionCommandRequest()

    if command == "reverse":
        reason = body.reason or "Admin reversal"
        result = TransactionService.reverse_transaction(db, txn, reason, actor_id=principal.user_id)
    elif command == "void":
        reason = body.reason or "Voided"
        result = TransactionService.void_transaction(db, txn, reason, actor_id=principal.user_id)
    elif command == "flag":
        if not body.flag_reason:
            raise HTTPException(status_code=422, detail="flag_reason is required for the 'flag' command")
        result = TransactionService.flag_transaction(db, txn, body.flag_reason, actor_id=principal.user_id)
    elif command == "unflag":
        if not body.unflag_reason:
            raise HTTPException(status_code=422, detail="unflag_reason is required for the 'unflag' command")
        result = TransactionService.unflag_transaction(db, txn, body.unflag_reason, actor_id=principal.user_id)
    elif command == "capture":
        result = TransactionService.capture_preauth(db, txn, body.amount, actor_id=principal.user_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: '{command}'. Supported: reverse, void, flag, unflag, capture")

    data = TransactionDetailSchema.model_validate(result).model_dump(mode='json')
    return envelope_success(data)

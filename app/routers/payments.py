import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.models.transactions.payments import Payment
from app.schemas.transactions.operations import CreatePaymentRequest, PaymentSchema, PaymentCommandRequest
from app.services.transactions.operations_service import PaymentService

router = APIRouter(tags=["Payments"])

@router.post("/cards/{card_id}/payments", status_code=201)
def create_payment(
    card_id: uuid.UUID,
    request: CreatePaymentRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("payment:make"))
):
    """Cardholder payment towards credit card outstanding balance."""
    result = PaymentService.create_payment(db, card_id, request, actor_id=principal.user_id)
    return envelope_success(result.model_dump(mode='json') if hasattr(result, 'model_dump') else result)

@router.get("/cards/{card_id}/payments")
def list_payments(
    card_id: uuid.UUID,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("payment:read"))
):
    """Lists all payments on the card account with status and date filters."""
    query = db.query(Payment).filter(Payment.card_id == card_id)
    if status:
        query = query.filter(Payment.status == status)
    total = query.count()
    results = query.order_by(Payment.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = [PaymentSchema.model_validate(p).model_dump(mode='json') for p in results]
    
    return envelope_success({
        "data": data,
        "meta": {"total": total, "page": page, "page_size": page_size}
    })

@router.patch("/payments/{payment_id}")
def transition_payment(
    payment_id: uuid.UUID,
    command: str = Query(..., description="confirm | reverse"),
    body: PaymentCommandRequest = None,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("payment:make"))
):
    """Payment state machine transitions (confirm | reverse)."""
    body = body or PaymentCommandRequest()
    if command == "confirm":
        payment = PaymentService.confirm_payment(db, payment_id, actor_id=principal.user_id)
    elif command == "reverse":
        reason = body.reason or "Payment reversal"
        payment = PaymentService.reverse_payment(db, payment_id, reason, actor_id=principal.user_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: '{command}'. Supported: confirm, reverse")
        
    data = PaymentSchema.model_validate(payment).model_dump(mode='json')
    return envelope_success(data)

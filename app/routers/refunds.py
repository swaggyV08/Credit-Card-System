from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.schemas.transactions.transactions import CreateRefundRequest
from app.services.transactions.transaction_service import RefundService

router = APIRouter(tags=["Refunds"])

@router.post("/transactions/{txn_id}/refunds", status_code=201)
def create_refund(
    txn_id: UUID,
    request: CreateRefundRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("refund:process"))
):
    """Merchant-initiated refund against a SETTLED transaction. Partial refunds are supported."""
    result = RefundService.process_refund(db, txn_id, request, actor_id=principal.user_id)
    return envelope_success(result.model_dump(mode='json') if hasattr(result, 'model_dump') else result)

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.models.transactions.clearing import ClearingBatch
from app.schemas.transactions.transactions import CreateClearingBatchRequest, ClearingBatchDetailSchema
from app.services.transactions.transaction_service import ClearingService

router = APIRouter(tags=["Clearing"])

@router.post("/clearing/batches", status_code=201)
def process_clearing_batch(
    request: CreateClearingBatchRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("settlement:run"))
):
    """Ingests a clearing batch from the card network."""
    result = ClearingService.process_batch(db, request, actor_id=principal.user_id)
    return envelope_success(result.model_dump(mode='json') if hasattr(result, 'model_dump') else result)

@router.get("/clearing/batches")
def list_clearing_batches(
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("settlement:run"))
):
    """Lists all clearing batches."""
    query = db.query(ClearingBatch)
    if status:
        query = query.filter(ClearingBatch.status == status)
    total = query.count()
    results = query.order_by(ClearingBatch.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = [ClearingBatchDetailSchema.model_validate(b).model_dump(mode='json') for b in results]
    
    return envelope_success({
        "data": data,
        "meta": {"total": total, "page": page, "page_size": page_size}
    })

@router.get("/clearing/batches/{batch_id}")
def get_clearing_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("settlement:run"))
):
    """Returns status and summary of a clearing batch."""
    batch = db.query(ClearingBatch).filter(ClearingBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Clearing batch not found")
    data = ClearingBatchDetailSchema.model_validate(batch).model_dump(mode='json')
    return envelope_success(data)

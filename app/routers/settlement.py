from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.models.transactions.settlement import SettlementRun
from app.schemas.transactions.transactions import CreateSettlementRequest, SettlementRunDetailSchema
from app.services.transactions.transaction_service import SettlementService

router = APIRouter(tags=["Settlement"])

@router.post("/settlements", status_code=201)
def run_settlement(
    request: CreateSettlementRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("settlement:run"))
):
    """Triggers a settlement run for all cleared transactions within the cutoff window."""
    result = SettlementService.run_settlement(db, request, actor_id=principal.user_id)
    return envelope_success(result.model_dump(mode='json') if hasattr(result, 'model_dump') else result)

@router.get("/settlements/{settlement_run_id}")
def get_settlement_run(
    settlement_run_id: UUID,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("settlement:run"))
):
    """Full detail of a settlement run including per-card breakdown."""
    run = db.query(SettlementRun).filter(SettlementRun.id == settlement_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Settlement run not found")
    data = SettlementRunDetailSchema.model_validate(run).model_dump(mode='json')
    return envelope_success(data)

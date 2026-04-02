from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.schemas.transactions.transactions import HoldSchema, HoldReleaseRequest
from app.services.transactions.transaction_service import HoldService

router = APIRouter(tags=["Holds"])



@router.patch("/holds/{hold_id}")
def release_hold(
    hold_id: UUID,
    command: str = Query(..., description="release"),
    body: HoldReleaseRequest = None,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("transaction:state"))
):
    """Release a specific hold manually."""
    if command != "release":
        raise HTTPException(status_code=400, detail=f"Unknown command: '{command}'. Only 'release' is supported.")
    if not body:
        raise HTTPException(status_code=422, detail="Request body with release_reason is required")
    hold = HoldService.release_hold(db, hold_id, body.release_reason, actor_id=principal.user_id)
    data = HoldSchema.model_validate(hold).model_dump(mode='json')
    return envelope_success(data)

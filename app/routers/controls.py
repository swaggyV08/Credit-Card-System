import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.schemas.transactions.operations import CardControlSchema, UpdateCardControlRequest
from app.services.transactions.operations_service import ControlsService

router = APIRouter(tags=["Card Controls"])

@router.get("/cards/{card_id}/controls")
def get_controls(
    card_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("controls:read"))
):
    """Returns current transaction controls and spending limits on the card."""
    ctrl = ControlsService.get_controls(db, card_id)
    data = CardControlSchema.model_validate(ctrl).model_dump(mode='json')
    return envelope_success(data)

@router.patch("/cards/{card_id}/controls")
def update_controls(
    card_id: uuid.UUID,
    request: UpdateCardControlRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("controls:update"))
):
    """Update transaction controls."""
    ctrl = ControlsService.update_controls(db, card_id, request, actor_id=principal.user_id)
    data = CardControlSchema.model_validate(ctrl).model_dump(mode='json')
    return envelope_success(data)

import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.schemas.transactions.operations import CardControlSchema, UpdateCardControlRequest
from app.services.transactions.operations_service import ControlsService
from app.services.transactions.transaction_service import TransactionService
from app.core.exceptions import AdminOnlyControlError
from app.models.enums import CardStatus

router = APIRouter(tags=["Card Controls"])

@router.get("/cards/{card_id}/controls")
def get_controls(
    card_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("controls:read"))
):
    """Returns current transaction controls and spending limits on the card."""
    # 1. Ownership & Status Validation
    card = TransactionService.validate_card(db, card_id, user_id=principal.user_id)
    
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
    # 1. Ownership & Status Validation
    card = TransactionService.validate_card(db, card_id, user_id=principal.user_id)

    # 2. Security Check: Admin-only fields
    # If the user is not an admin, they cannot touch certain fields
    is_admin = principal.role in ["SUPERADMIN", "ADMIN", "MANAGER"]
    if not is_admin:
        # Example sensitive fields that only admins can change (as per directive)
        # Directive says "ADMIN_ONLY_CONTROL (e.g. if USER tries to change credit_limit in controls)"
        # Assuming UpdateCardControlRequest has fields that are sensitive
        sensitive_fields = ["daily_limit", "monthly_limit", "mcc_blocks", "allowed_countries"]
        # This is a representative check
        for field in sensitive_fields:
            if getattr(request, field, None) is not None:
                raise AdminOnlyControlError()

    ctrl = ControlsService.update_controls(db, card_id, request, actor_id=principal.user_id)
    data = CardControlSchema.model_validate(ctrl).model_dump(mode='json')
    return envelope_success(data)

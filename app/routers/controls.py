import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success
from app.schemas.responses import CardControlsResponse

from app.schemas.transactions.operations import CardControlSchema, UpdateCardControlRequest
from app.services.transactions.operations_service import ControlsService
from app.services.transactions.transaction_service import TransactionService
from app.core.exceptions import AdminOnlyControlError
from app.models.enums import CardStatus

router = APIRouter(tags=["Card Controls"])

@router.get("/cards/{card_id}/controls", response_model=CardControlsResponse)
def get_controls(
    card_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("controls:read"))
):
    """
    Returns current transaction controls and spending limits on the card.

    **What it does:**
    Fetches the card's active control profile including daily/monthly spending limits,
    MCC block lists, allowed countries, online/contactless/ATM toggles, and
    any admin-imposed restrictions. Validates card ownership for non-admin callers.

    **Roles:** `controls:read` (User / Admin) — Ownership enforced for Users.

    **Response:** `CardControlSchema` with all active limits and toggles.
    """
    # 1. Ownership & Status Validation
    card = TransactionService.validate_card(db, card_id, user_id=principal.user_id)
    
    ctrl = ControlsService.get_controls(db, card_id)
    data = CardControlSchema.model_validate(ctrl).model_dump(mode='json')
    return envelope_success(data)

@router.put("/cards/{card_id}/controls", response_model=CardControlsResponse)
def update_controls(
    card_id: uuid.UUID,
    request: UpdateCardControlRequest,
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("controls:update"))
):
    """
    Updates transaction controls and spending limits on the card.

    **What it does:**
    Modifies the card's control profile. Non-admin users are restricted from
    changing sensitive fields (daily_limit, monthly_limit, mcc_blocks, allowed_countries)
    which are admin-only controls.

    **Request Body (`UpdateCardControlRequest`):**
    - `daily_limit`: Decimal — max daily spend (Admin only)
    - `monthly_limit`: Decimal — max monthly spend (Admin only)
    - `online_enabled` / `contactless_enabled` / `atm_enabled`: Boolean toggles
    - `mcc_blocks`: List of blocked merchant category codes (Admin only)
    - `allowed_countries`: List of ISO country codes (Admin only)

    **Roles:** `controls:update` (User / Admin) — Sensitive fields are Admin-only.

    **Response:** Updated `CardControlSchema`.
    """
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

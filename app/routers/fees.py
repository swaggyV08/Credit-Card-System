import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.schemas.transactions.operations import FeeSchema, CreateFeeRequest, FeeWaiveRequest, InterestPostRequest
from app.services.transactions.operations_service import FeeService
from app.core.exceptions import (
    FeeNotFoundError, FeeAlreadyWaivedError,
)

router = APIRouter(tags=["Fees & Interest"])

# DELETE: GET /cards/{card_id}/fees removed as per directive.

@router.post("/cards/{card_id}/fees", status_code=201)
def manage_fee(
    card_id: uuid.UUID,
    command: str = Query(..., description="apply | waive"),
    apply_request: CreateFeeRequest = None,
    waive_request: FeeWaiveRequest = None,
    fee_id: uuid.UUID = Query(None, description="Required only when command=waive"),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("fee:apply"))
):
    """
    Apply or waive a fee — unified endpoint.

    **What it does:**
    A single POST endpoint that handles both fee application and fee waiver via
    the `command` query parameter. Applying a fee creates a new fee transaction
    on the card. Waiving a fee marks an existing fee as waived with a reason.

    **Query Parameter `command`:**
    - `apply` — Charges a new fee to the card. Uses `apply_request` body.
    - `waive` — Waives an existing fee. Uses `waive_request` body + `fee_id` query param.

    **Fee Type enum (in `CreateFeeRequest`):**
    `ANNUAL_FEE` | `LATE_PAYMENT_FEE` | `OVER_LIMIT_FEE` | `CASH_ADVANCE_FEE` |
    `FOREIGN_TRANSACTION_FEE` | `RETURNED_PAYMENT_FEE` | `CARD_REPLACEMENT_FEE` |
    `INTEREST_CHARGE` | `OVERLIMIT_FEE`

    **Roles:** `fee:apply` (Admin / Super Admin only)

    **Response:** `FeeSchema` with fee details, status, and timestamps.
    """
    if command == "apply":
        if not apply_request:
            raise HTTPException(status_code=422, detail="apply_request body is required for 'apply' command")
        fee = FeeService.apply_fee(db, card_id, apply_request, actor_id=principal.user_id)
        data = FeeSchema.model_validate(fee).model_dump(mode='json')
        return envelope_success(data)
        
    elif command == "waive":
        if not fee_id:
            raise HTTPException(status_code=422, detail="fee_id query param is required for 'waive' command")
        if not waive_request:
            raise HTTPException(status_code=422, detail="waive_request body is required for 'waive' command")
        
        # Validation: min 10 chars for waiver_reason
        if len(waive_request.waiver_reason) < 10:
            raise HTTPException(status_code=422, detail="waiver_reason must be at least 10 characters")

        fee = FeeService.waive_fee(db, fee_id, waive_request.waiver_reason, actor_id=principal.user_id)
        if not fee:
            raise FeeNotFoundError()
        data = FeeSchema.model_validate(fee).model_dump(mode='json')
        return envelope_success(data)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: '{command}'")

# DELETE: POST /interest logic absorbed or removed as per directive.
